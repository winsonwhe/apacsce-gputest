"""Opt-in host networking and storage checks."""

import random
import re
import uuid

from gputest import parsers
from gputest.core import Result, check


@check('oca_version', category='preflight')
def oca_version(ctx):
    """Inventory Oracle Cloud Agent packages using each host's package managers."""
    cfg = ctx.config.get('oca_version', {})
    if not cfg.get('enabled', True):
        return Result('oca_version', 'SKIP', 'OCA version check disabled')
    tools = ctx.config['tools']
    timeout = cfg.get('timeout_s', 30)
    raw = []
    os_result = _run(ctx, [tools['cat'], cfg.get('os_release_path', '/etc/os-release')],
                     raw, 'oca_os_release.txt', timeout)
    os_info = parsers.parse_os_release(os_result.stdout) if not os_result.returncode else {}
    identifiers = set((os_info.get('id', '') + ' ' + os_info.get('id_like', '')).lower().split())
    # TODO(verify): verify package names and command output on supported OCI images.
    queries = {
        'rpm': ([tools['rpm'], '-q', '--qf', '%{VERSION}-%{RELEASE}\n', 'oracle-cloud-agent'], 'oca_rpm.txt'),
        'dpkg': ([tools['dpkg_query'], '-W', '-f=${db:Status-Abbrev}\t${Version}\n', 'oracle-cloud-agent'], 'oca_dpkg.txt'),
        'snap': ([tools['snap'], 'list', 'oracle-cloud-agent'], 'oca_snap.txt'),
    }
    if identifiers & {'ubuntu', 'debian'}:
        order = ('dpkg', 'snap', 'rpm')
    elif identifiers & {'ol', 'rhel', 'centos', 'fedora', 'sles', 'suse'}:
        order = ('rpm', 'snap', 'dpkg')
    else:
        order = ('rpm', 'dpkg', 'snap')
    found, warnings, issues = {}, [], []
    for manager in order:
        cmd, fixture = queries[manager]
        rr = _run(ctx, cmd, raw, fixture, timeout)
        if rr.skipped or rr.returncode:
            continue
        version = parsers.parse_oca_package(rr.stdout, manager)['version']
        if version:
            found[manager] = version
        else:
            warnings.append(f'{manager}: unrecognized or inactive OCA package output')
    if ctx.dry_run:
        return Result('oca_version', 'SKIP', 'dry-run: previewed package queries', _raw='\n'.join(raw))
    if not os_info:
        warnings.append('OS identification unavailable')
    if not found:
        warnings.append('Oracle Cloud Agent package version unavailable')
    minimum = cfg.get('min_version')
    if minimum is not None:
        if not isinstance(minimum, str) or not re.fullmatch(r'\d+(?:\.\d+)*', minimum):
            raise ValueError('oca_version.min_version must be a numeric dotted version string')
        expected = tuple(map(int, minimum.split('.')))
        for manager, version in found.items():
            actual = parsers.parse_oca_version_core(version)['components']
            if actual is None:
                warnings.append(f'{manager}: cannot safely compare version {version}')
                continue
            length = max(len(actual), len(expected))
            if actual + (0,) * (length - len(actual)) < expected + (0,) * (length - len(expected)):
                issues.append(f'{manager}: OCA {version} is below {minimum}')
    elif found:
        warnings.append('OCA minimum version not configured')
    metrics = {'os': os_info, 'versions': found, 'min_version': minimum}
    return Result('oca_version', 'FAIL' if issues else ('WARN' if warnings else 'PASS'),
                  '; '.join(issues + warnings) or 'Oracle Cloud Agent version meets configured minimum',
                  metrics, _raw='\n'.join(raw))


def _result(name, ctx, records, raw, issues, warnings):
    status = 'SKIP' if ctx.dry_run else ('FAIL' if issues else ('WARN' if warnings else 'PASS'))
    return Result(name, status, '; '.join(issues + warnings) or f'{len(records)} configured tests completed',
                  {'tests': records}, _raw='\n'.join(raw))


def _run(ctx, cmd, raw, fixture, timeout):
    rr = ctx.run(cmd, timeout=timeout, mock_fixture=fixture)
    raw.append(f'$ {" ".join(cmd)}\n{rr.stdout}{rr.stderr}')
    return rr


@check('nic_inventory', category='diagnostics')
def nic_inventory(ctx):
    """Check configured host interfaces and optionally compare LLDP peer identifiers."""
    cfg = ctx.config.get('nic_inventory', {})
    interfaces = cfg.get('interfaces', [])
    if not cfg.get('enabled') or not interfaces:
        return Result('nic_inventory', 'SKIP', 'configure nic_inventory interfaces')
    records, raw, issues, warnings = [], [], [], []
    for item in interfaces:
        dev = item['name']
        rr = _run(ctx, [ctx.config['tools']['ethtool'], dev], raw, 'ethtool.txt', cfg['timeout_s'])
        if ctx.dry_run:
            if item.get('peer_chassis') or item.get('peer_port'):
                _run(ctx, [ctx.config['tools']['lldpcli'], '-f', 'keyvalue', 'show',
                           'neighbors', 'ports', dev, 'details'], raw, 'lldp.txt', cfg['timeout_s'])
            continue
        if rr.returncode:
            issues.append(f'{dev}: ethtool failed')
            continue
        rec = {'interface': dev, **parsers.parse_ethtool_link(rr.stdout)}
        records.append(rec)
        if not rec['link']:
            warnings.append(f'{dev}: link state unavailable')
        elif rec['link'] != 'yes':
            issues.append(f'{dev}: link is down')
        if item.get('min_speed_mbps') is not None:
            if rec['speed_mbps'] is None:
                warnings.append(f'{dev}: link speed unavailable')
            elif rec['speed_mbps'] < item['min_speed_mbps']:
                issues.append(f'{dev}: link speed below configured minimum')
        if item.get('peer_chassis') or item.get('peer_port'):
            # lldpcli keyvalue fields must be checked against the deployed version.
            peer = _run(ctx, [ctx.config['tools']['lldpcli'], '-f', 'keyvalue', 'show',
                              'neighbors', 'ports', dev, 'details'], raw, 'lldp.txt', cfg['timeout_s'])
            if peer.returncode:
                warnings.append(f'{dev}: LLDP peer unavailable')
                continue
            fields = parsers.parse_lldp_peer(peer.stdout)
            for option in ('peer_chassis', 'peer_port'):
                expected = item.get(option)
                if expected:
                    values = fields[option]
                    if not values:
                        warnings.append(f'{dev}: LLDP {option} unavailable')
                    elif expected not in values:
                        issues.append(f'{dev}: LLDP {option} differs from configured peer')
    return _result('nic_inventory', ctx, records, raw, issues, warnings)


@check('network_ping', category='diagnostics')
def network_ping(ctx):
    """Probe explicitly configured source/target paths from each selected host."""
    cfg = ctx.config.get('network_ping', {})
    paths = cfg.get('paths', [])
    if not cfg.get('enabled') or not paths:
        return Result('network_ping', 'SKIP', 'configure network_ping paths')
    paths = [p for p in paths if p.get('node') == ctx.target_node or
             (not ctx.target_node and not p.get('node'))]
    if not paths:
        return Result('network_ping', 'SKIP', 'no ping paths configured for this host')
    limit = cfg.get('sample_count', 0)
    if limit and limit < len(paths):
        paths = random.Random(cfg['seed']).sample(paths, limit)
    records, raw, issues, warnings = [], [], [], []
    for path in paths:
        if path.get('family') not in ('ipv4', 'ipv6'):
            raise ValueError('ping family must be ipv4 or ipv6')
        cmd = []
        if path.get('vrf'):
            cmd = [ctx.config['tools']['ip'], 'vrf', 'exec', path['vrf']]
        cmd += [ctx.config['tools']['ping'], '-6' if path['family'] == 'ipv6' else '-4',
                '-I', path['source'], '-c', str(cfg['count']), '-W', str(cfg['wait_s']), path['target']]
        rr = _run(ctx, cmd, raw, 'ping.txt', cfg['timeout_s'])
        if not ctx.dry_run:
            loss = parsers.parse_ping_loss(rr.stdout)['loss_pct']
            records.append({'source': path['source'], 'target': path['target'], 'loss_pct': loss})
            if rr.returncode:
                issues.append(f'{path["source"]} -> {path["target"]}: ping failed')
            elif loss is None:
                warnings.append(f'{path["source"]} -> {path["target"]}: packet loss unavailable')
            elif loss > cfg['max_loss_pct']:
                issues.append(f'{path["source"]} -> {path["target"]}: packet loss {loss}%')
    return _result('network_ping', ctx, records, raw, issues, warnings)


@check('tcp_bandwidth', category='diagnostics')
def tcp_bandwidth(ctx):
    """Connect to pre-existing iperf3 servers using configured source paths."""
    cfg = ctx.config.get('tcp_bandwidth', {})
    paths = [p for p in cfg.get('paths', []) if p.get('node') == ctx.target_node or
             (not ctx.target_node and not p.get('node'))]
    if not cfg.get('enabled') or not paths:
        return Result('tcp_bandwidth', 'SKIP', 'no TCP bandwidth paths configured for this host')
    records, raw, issues, warnings = [], [], [], []
    for path in paths:
        cmd = [ctx.config['tools']['ip'], 'vrf', 'exec', path['vrf']] if path.get('vrf') else []
        cmd += [ctx.config['tools']['iperf3'], '-c', path['target'], '-B', path['source'],
                '-p', str(path['port']), '-t', str(cfg['duration_s']), '-P', str(cfg['parallel_streams']), '-J']
        if path.get('reverse'):
            cmd.append('-R')
        rr = _run(ctx, cmd, raw, 'iperf3.json', cfg['timeout_s'])
        if ctx.dry_run:
            continue
        try:
            if rr.returncode:
                raise ValueError('iperf3 reported failure')
            gbps = parsers.parse_iperf3(rr.stdout)['gbps']
        except (ValueError, KeyError, TypeError):
            issues.append(f'{path["target"]}: iperf3 failed or output incomplete')
            continue
        records.append({'source': path['source'], 'target': path['target'], 'gbps': gbps})
        if path.get('min_gbps') is None:
            warnings.append(f'{path["target"]}: throughput threshold unset')
        elif gbps < path['min_gbps']:
            issues.append(f'{path["target"]}: {gbps:.2f} Gb/s below threshold')
    return _result('tcp_bandwidth', ctx, records, raw, issues, warnings)


@check('filesystem_perf', category='diagnostics')
def filesystem_perf(ctx):
    """Benchmark explicitly configured files using fio; never overwrite an existing file."""
    cfg = ctx.config.get('filesystem_perf', {})
    jobs = cfg.get('jobs', [])
    if not cfg.get('enabled') or not jobs:
        return Result('filesystem_perf', 'SKIP', 'configure filesystem_perf jobs')
    records, raw, issues, warnings = [], [], [], []
    for job in jobs:
        mode = job['rw']
        if mode not in ('read', 'randread', 'write', 'randwrite'):
            raise ValueError('fio rw must be read, randread, write or randwrite')
        writing = mode in ('write', 'randwrite')
        if writing:
            if not job.get('directory') or not job.get('size'):
                raise ValueError('write job requires directory and size')
            filename = job['directory'].rstrip('/') + '/gputest-' + uuid.uuid4().hex
        else:
            if not job.get('file'):
                raise ValueError('read job requires an existing file')
            filename = job['file']
        cmd = [ctx.config['tools']['fio'], '--name=gputest', '--filename=' + filename,
               '--rw=' + mode, '--direct=1', '--output-format=json', '--group_reporting',
               '--bs=' + str(job['block_size']), '--iodepth=' + str(job['iodepth']),
               '--numjobs=1']
        if writing:
            cmd += ['--size=' + str(job['size']), '--unlink=1']
        else:
            cmd += ['--readonly', '--allow_file_create=0']
        rr = _run(ctx, cmd, raw, 'fio.json', cfg['timeout_s'])
        if ctx.dry_run:
            continue
        try:
            if rr.returncode:
                raise ValueError('fio reported failure')
            values = parsers.parse_fio(rr.stdout, writing)
            mib, iops = values['mib_s'], values['iops']
        except (ValueError, KeyError, TypeError):
            issues.append(f'{filename}: fio failed or output incomplete')
            continue
        records.append({'path': filename, 'rw': mode, 'mib_s': mib, 'iops': iops})
        for key, value in [('min_mib_s', mib), ('min_iops', iops)]:
            if job.get(key) is not None and value < job[key]:
                issues.append(f'{filename}: {key} not met')
        if job.get('min_mib_s') is None and job.get('min_iops') is None:
            warnings.append(f'{filename}: performance thresholds unset')
    return _result('filesystem_perf', ctx, records, raw, issues, warnings)


@check('lustre_client', category='diagnostics')
def lustre_client(ctx):
    """Verify a configured Lustre mount and query its capacity and striping."""
    cfg = ctx.config.get('lustre_client', {})
    if not cfg.get('enabled') or not cfg.get('path'):
        return Result('lustre_client', 'SKIP', 'configure lustre_client path')
    path = cfg['path']
    commands = [([ctx.config['tools']['findmnt'], '-n', '-o', 'FSTYPE', '--target', path], 'mount'),
                ([ctx.config['tools']['lfs'], 'df', '-h', path], 'capacity'),
                ([ctx.config['tools']['lfs'], 'getstripe', path], 'stripe')]
    records, raw, issues = [], [], []
    for cmd, label in commands:
        rr = _run(ctx, cmd, raw, f'lustre_{label}.txt', cfg['timeout_s'])
        if not ctx.dry_run:
            if rr.returncode:
                issues.append(f'Lustre {label} command failed')
            elif label == 'mount' and rr.stdout.strip() != 'lustre':
                issues.append(f'{path}: filesystem is not Lustre')
            records.append({'check': label, 'returncode': rr.returncode})
    return _result('lustre_client', ctx, records, raw, issues, [])


@check('object_storage', category='diagnostics')
def object_storage(ctx):
    """Download a configured OCI object to a unique temporary file."""
    cfg = ctx.config.get('object_storage', {})
    if not cfg.get('enabled') or not all(cfg.get(k) for k in ('bucket', 'object', 'scratch_dir')):
        return Result('object_storage', 'SKIP', 'configure bucket, object and scratch_dir')
    filename = cfg['scratch_dir'].rstrip('/') + '/gputest-object-' + uuid.uuid4().hex
    cmd = [ctx.config['tools']['oci'], 'os', 'object', 'get', '--bucket-name', cfg['bucket'],
           '--name', cfg['object'], '--file', filename]
    if cfg.get('namespace'):
        cmd += ['--namespace-name', cfg['namespace']]
    cmd += cfg.get('extra_args', [])
    raw, records, issues, warnings = [], [], [], []
    rr = _run(ctx, cmd, raw, 'oci_object.txt', cfg['timeout_s'])
    size = _run(ctx, [ctx.config['tools']['wc'], '-c', filename], raw, 'object_size.txt', cfg['timeout_s'])
    cleanup = _run(ctx, [ctx.config['tools']['rm'], '-f', '--', filename], raw, 'empty.txt', cfg['timeout_s'])
    if not ctx.dry_run:
        if rr.returncode or size.returncode:
            issues.append('object download or size measurement failed')
        elif ctx.mock:
            warnings.append('mock mode cannot measure download throughput')
        else:
            try:
                size_bytes = int(size.stdout.split()[0])
                if rr.elapsed_s <= 0:
                    raise ValueError('elapsed time unavailable')
                mib = size_bytes / (1024 * 1024) / rr.elapsed_s
                records.append({'bytes': size_bytes, 'elapsed_s': rr.elapsed_s, 'mib_s': mib})
                if cfg.get('min_mib_s') is None:
                    warnings.append('download throughput threshold unset')
                elif mib < cfg['min_mib_s']:
                    issues.append('object download throughput below threshold')
            except (ValueError, IndexError):
                issues.append('object size or elapsed time unavailable')
        if cleanup.returncode:
            warnings.append(f'could not remove temporary file {filename}')
    return _result('object_storage', ctx, records, raw, issues, warnings)


@check('object_upload', category='diagnostics')
def object_upload(ctx):
    """Upload an existing file under a unique name and remove only that object."""
    cfg = ctx.config.get('object_upload', {})
    if not cfg.get('enabled') or not all(cfg.get(k) for k in ('bucket', 'source_file', 'prefix')):
        return Result('object_upload', 'SKIP', 'configure bucket, source_file and prefix')
    name = cfg['prefix'].rstrip('/') + '/gputest-' + uuid.uuid4().hex
    common = ['--bucket-name', cfg['bucket'], '--name', name]
    if cfg.get('namespace'):
        common += ['--namespace-name', cfg['namespace']]
    common += cfg.get('extra_args', [])
    raw, records, issues, warnings = [], [], [], []
    size = _run(ctx, [ctx.config['tools']['wc'], '-c', cfg['source_file']], raw,
                'object_size.txt', cfg['timeout_s'])
    if size.returncode and not ctx.dry_run:
        return _result('object_upload', ctx, records, raw, ['source file size unavailable'], warnings)
    # TODO(verify): confirm the deployed OCI CLI supports this conditional upload option.
    rr = _run(ctx, [ctx.config['tools']['oci'], 'os', 'object', 'put'] + common +
              ['--file', cfg['source_file'], '--if-none-match', '*'], raw, 'oci_object.txt', cfg['timeout_s'])
    if rr.returncode and not ctx.dry_run:
        return _result('object_upload', ctx, records, raw,
                       [f'upload failed; inspect bucket for possible incomplete object {name}'], warnings)
    cleanup = _run(ctx, [ctx.config['tools']['oci'], 'os', 'object', 'delete'] + common + ['--force'],
                   raw, 'oci_object.txt', cfg['timeout_s'])
    if not ctx.dry_run:
        if cleanup.returncode:
            issues.append(f'could not delete temporary object {name}')
        if ctx.mock:
            warnings.append('mock mode cannot measure upload throughput')
            return _result('object_upload', ctx, records, raw, issues, warnings)
        try:
            size_bytes = int(size.stdout.split()[0])
            if rr.elapsed_s <= 0:
                raise ValueError('elapsed time unavailable')
            mib = size_bytes / (1024 * 1024) / rr.elapsed_s
            records.append({'bytes': size_bytes, 'elapsed_s': rr.elapsed_s, 'mib_s': mib, 'object': name})
            if cfg.get('min_mib_s') is None:
                warnings.append('upload throughput threshold unset')
            elif mib < cfg['min_mib_s']:
                issues.append('object upload throughput below threshold')
        except (ValueError, IndexError):
            issues.append('object size or elapsed time unavailable')
    return _result('object_upload', ctx, records, raw, issues, warnings)
