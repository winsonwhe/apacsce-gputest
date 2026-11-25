"""Local-only HTTP controller for the gputest UI.

Use a trusted reverse proxy for remote access. Jobs call the existing CLI and
keep their configuration, output and reports under the controller state folder.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import yaml

import gputest.checks  # noqa: F401
from gputest.core import get_registry, load_config

ROOT = Path(__file__).resolve().parent.parent
UI_ROOT = ROOT / 'ui'
HOST_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.:%-]*$')
USER_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.-]*$')
ID_RE = re.compile(r'^[0-9a-f]{32}$')
MAX_BODY = 128 * 1024


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


class Controller:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.Lock()
        self.active = set()

    def nodes(self):
        return read_json(self.root / 'nodes.json', [])

    def save_nodes(self, entries):
        if not isinstance(entries, list) or len(entries) > 256:
            raise ValueError('nodes must be a list of at most 256 entries')
        clean, hosts = [], set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise TypeError('invalid node')
            host = str(entry.get('host', '')).strip()
            user = str(entry.get('user', '')).strip()
            port = entry.get('port', 22)
            if not HOST_RE.fullmatch(host) or host in hosts:
                raise ValueError(f'invalid or duplicate host: {host}')
            if user and not USER_RE.fullmatch(user):
                raise ValueError(f'invalid SSH user: {user}')
            if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
                raise ValueError('port must be between 1 and 65535')
            hosts.add(host)
            clean.append({'host': host, 'user': user, 'port': port})
        self.write_json(self.root / 'nodes.json', clean)
        return clean

    @staticmethod
    def write_json(path, value):
        temp = path.with_name(path.name + '.tmp')
        temp.write_text(json.dumps(value, indent=2) + '\n')
        os.replace(temp, path)

    def catalog(self):
        # The catalog only needs names; SKU-specific details are loaded when a job starts.
        sku_files = sorted((ROOT / 'config' / 'skus').glob('*.yaml'))
        config = load_config(ROOT / 'config', sku=sku_files[0].stem) if sku_files else load_config(ROOT / 'config')
        return {'levels': config['levels'], 'skus': [p.stem for p in sku_files],
                'checks': [{k: c[k] for k in ('name', 'category', 'skus', 'multi_host')}
                           for c in get_registry()]}

    def job_dir(self, job_id):
        if not ID_RE.fullmatch(job_id):
            raise ValueError('invalid run ID')
        return self.root / job_id

    def jobs(self):
        result = []
        for path in self.root.glob('*/job.json'):
            job = read_json(path, None)
            if isinstance(job, dict):
                if job.get('status') in ('created', 'running') and job.get('id') not in self.active:
                    job['status'] = 'interrupted'
                result.append(job)
        return sorted(result, key=lambda j: j['created_at'], reverse=True)

    def job(self, job_id):
        job = read_json(self.job_dir(job_id) / 'job.json', None)
        if job and job['status'] in ('created', 'running') and job_id not in self.active:
            job['status'] = 'interrupted'
        return job

    def start_run(self, data):
        catalog = self.catalog()
        sku, level = data.get('sku'), data.get('level')
        if sku not in catalog['skus'] or level not in catalog['levels']:
            raise ValueError('unknown SKU or level')
        tests = data.get('tests')
        known = {c['name'] for c in catalog['checks']}
        if not isinstance(tests, list) or not tests or any(not isinstance(t, str) or t not in known for t in tests):
            raise ValueError('select at least one registered check')
        hosts = data.get('nodes')
        if not isinstance(hosts, list) or not hosts or any(not isinstance(h, str) for h in hosts):
            raise ValueError('select at least one configured node')
        selected = [n for n in self.nodes() if n['host'] in hosts]
        if len(hosts) != len(set(hosts)) or len(selected) != len(hosts):
            raise ValueError('unknown or duplicate node')
        network = data.get('network_mode', 'auto')
        if network not in ('auto', 'single_plane', 'multiplanar'):
            raise ValueError('invalid network mode')
        for flag in ('dry_run', 'mock'):
            if not isinstance(data.get(flag, False), bool):
                raise TypeError(f'{flag} must be boolean')
        job_id = uuid.uuid4().hex
        directory = self.job_dir(job_id)
        directory.mkdir(mode=0o700)
        # A job-specific SSH configuration carries the controller's key and port
        # without changing global SSH settings or bypassing host-key validation.
        key = self.root / 'controller_key'
        config_lines = []
        for node in selected:
            config_lines.extend([f"Host {node['host']}", f"  HostName {node['host']}",
                                 f"  Port {node['port']}"])
            if node['user']:
                config_lines.append(f"  User {node['user']}")
        if key.exists():
            config_lines.extend(['Host *', f'  IdentityFile "{key}"', '  IdentitiesOnly yes'])
        ssh_config = directory / 'ssh_config'
        ssh_config.write_text('\n'.join(config_lines) + '\n')
        ssh_wrapper = directory / 'ssh'
        ssh_wrapper.write_text('#!/bin/sh\nexec ssh -F ' + shlex.quote(str(ssh_config)) + ' "$@"\n')
        ssh_wrapper.chmod(0o700)
        config = load_config(ROOT / 'config', sku=sku)
        config['tools']['ssh'] = str(ssh_wrapper)
        # The CLI accepts modular directories only. Store a job-local snapshot
        # with the merged base and selected SKU fragment.
        config_path = directory / 'config'
        (config_path / 'skus').mkdir(parents=True)
        base_config = dict(config)
        sku_config = base_config.pop('skus')[sku]
        for key in ('_config_source', '_environment', '_sku'):
            base_config.pop(key, None)
        (config_path / 'base.yaml').write_text(yaml.safe_dump(base_config))
        (config_path / 'skus' / f'{sku}.yaml').write_text(
            yaml.safe_dump({'skus': {sku: sku_config}}))
        (config_path / 'manifest.yaml').write_text('default_environment: default\ndefault_tools: default\n')
        (config_path / 'environments').mkdir()
        (config_path / 'tools').mkdir()
        (config_path / 'environments' / 'default.yaml').write_text('{}\n')
        (config_path / 'tools' / 'default.yaml').write_text('{}\n')
        cmd = [sys.executable, '-u', '-m', 'gputest.cli', 'run', '--config', str(config_path),
               '--sku', sku, '--level', level, '--tests', ','.join(tests), '--nodes', ','.join(hosts),
               '--network-mode', network, '--output-dir', str(directory / 'output')]
        for flag in ('dry_run', 'mock'):
            if data.get(flag, False):
                cmd.append('--' + flag.replace('_', '-'))
        job = {'id': job_id, 'status': 'created', 'created_at': time.time(), 'sku': sku,
               'level': level, 'nodes': hosts, 'tests': tests, 'dry_run': data.get('dry_run', False),
               'mock': data.get('mock', False)}
        self.write_json(directory / 'job.json', job)
        with self.lock:
            self.active.add(job_id)
        threading.Thread(target=self._execute, args=(directory, job, cmd), daemon=True).start()
        return job

    def _execute(self, directory, job, cmd):
        job['status'] = 'running'
        self.write_json(directory / 'job.json', job)
        try:
            with (directory / 'run.log').open('w') as log:
                result = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, check=False)
            job['returncode'] = result.returncode
            job['status'] = 'completed' if result.returncode == 0 else 'failed'
        except OSError as exc:
            job['status'] = 'failed'
            job['error'] = str(exc)
        job['finished_at'] = time.time()
        self.write_json(directory / 'job.json', job)
        with self.lock:
            self.active.discard(job['id'])

    def save_key(self, key):
        if not isinstance(key, str) or not key.startswith(('-----BEGIN OPENSSH PRIVATE KEY-----',
                                                            '-----BEGIN RSA PRIVATE KEY-----',
                                                            '-----BEGIN EC PRIVATE KEY-----',
                                                            '-----BEGIN PRIVATE KEY-----')):
            raise ValueError('expected an OpenSSH or PEM private key')
        path = self.root / 'controller_key'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(key)


def make_handler(controller):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send_data(self, data, content_type='application/json; charset=utf-8', status=200):
            if not isinstance(data, bytes):
                data = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == '/api/health':
                    self.send_data({'status': 'ok'})
                elif path == '/api/nodes':
                    self.send_data({'nodes': controller.nodes()})
                elif path == '/api/checks':
                    self.send_data(controller.catalog())
                elif path == '/api/runs':
                    self.send_data({'runs': controller.jobs()})
                elif path.startswith('/api/runs/'):
                    parts = path.split('/')
                    directory = controller.job_dir(parts[3])
                    job = controller.job(parts[3])
                    if not job:
                        self.send_data({'error': 'run not found'}, status=404)
                    elif len(parts) == 4:
                        self.send_data({'job': job, 'result': read_json(directory / 'output' / 'results.json', None),
                                        'log': (directory / 'run.log').read_text(errors='replace') if (directory / 'run.log').exists() else ''})
                    elif len(parts) == 5 and parts[4] == 'markdown':
                        report = directory / 'output' / 'results.md'
                        self.send_data(report.read_bytes(), 'text/plain; charset=utf-8') if report.exists() else self.send_data({'error': 'report not available'}, status=404)
                    elif len(parts) == 5 and parts[4] == 'raw':
                        from urllib.parse import parse_qs
                        raw = parse_qs(urlsplit(self.path).query).get('file', [''])[0]
                        output = (directory / 'output').resolve()
                        candidate = (output / raw).resolve()
                        if raw and candidate.is_relative_to(output) and candidate.is_file():
                            self.send_data(candidate.read_bytes(), 'text/plain; charset=utf-8')
                        else:
                            self.send_data({'error': 'raw output not found'}, status=404)
                    else:
                        self.send_data({'error': 'not found'}, status=404)
                elif path in ('/', '/index.html', '/styles.css', '/app.js'):
                    file = UI_ROOT / ('index.html' if path == '/' else path[1:])
                    kind = 'text/html' if file.suffix == '.html' else 'text/css' if file.suffix == '.css' else 'text/javascript'
                    self.send_data(file.read_bytes(), kind + '; charset=utf-8')
                else:
                    self.send_data({'error': 'not found'}, status=404)
            except (ValueError, OSError) as exc:
                self.send_data({'error': str(exc)}, status=400)

        def do_POST(self):
            try:
                origin = self.headers.get('Origin')
                if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                    self.send_data({'error': 'cross-origin request rejected'}, status=403)
                    return
                if self.headers.get_content_type() != 'application/json':
                    raise ValueError('Content-Type must be application/json')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BODY:
                    raise ValueError('invalid request size')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise TypeError('expected a JSON object')
                path = urlsplit(self.path).path
                if path == '/api/nodes':
                    self.send_data({'nodes': controller.save_nodes(payload.get('nodes'))})
                elif path == '/api/ssh-key':
                    controller.save_key(payload.get('private_key'))
                    self.send_data({'status': 'stored'})
                elif path == '/api/runs':
                    self.send_data({'job': controller.start_run(payload)}, status=202)
                else:
                    self.send_data({'error': 'not found'}, status=404)
            except (ValueError, TypeError, OSError) as exc:
                self.send_data({'error': str(exc)}, status=400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description='Serve the gputest control center on localhost')
    parser.add_argument('--host', default='127.0.0.1',
                        help='Listen address; use 0.0.0.0 only behind a firewall or trusted network')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--state-dir', default=str(ROOT / 'results' / 'controller'))
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    server = ThreadingHTTPServer((args.host, args.port), make_handler(Controller(args.state_dir)))
    display_host = '127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host
    print(f'gputest controller listening on http://{display_host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
