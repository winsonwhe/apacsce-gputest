"""Oracle Cloud Agent version checks without an OCI host."""
from pathlib import Path

import gputest.checks  # noqa: F401
from gputest import parsers
from gputest.core import RunContext, RunResult, load_config, run_checks

ROOT = Path(__file__).resolve().parents[1]


def context(tmp_path, **kwargs):
    return RunContext(load_config(ROOT / 'config'), 'gb300', [],
                      results_dir=tmp_path, **kwargs)


def test_parsers_for_systems_and_installed_packages():
    assert parsers.parse_os_release('ID=ubuntu\nID_LIKE="debian linux"\n')['id_like'] == 'debian linux'
    assert parsers.parse_oca_package('1.50.0-1.el9\n', 'rpm')['version'] == '1.50.0-1.el9'
    assert parsers.parse_oca_package('ii 1.50.0-1\n', 'dpkg')['version'] == '1.50.0-1'
    assert parsers.parse_oca_package('rc 1.50.0-1\n', 'dpkg')['version'] is None
    snap = ('Name Version Rev Tracking Publisher Notes\n'
            'oracle-cloud-agent 1.1 1 latest/stable oracle disabled\n'
            'oracle-cloud-agent 1.2 2 latest/stable oracle -\n')
    assert parsers.parse_oca_package(snap, 'snap')['version'] == '1.2'
    assert parsers.parse_oca_package(snap.replace('oracle -', 'oracle disabled'), 'snap')['version'] is None
    assert parsers.parse_oca_version_core('1.2.3~rc1')['components'] is None


def test_version_threshold_and_mock(tmp_path):
    ctx = context(tmp_path, mock=True)
    result = run_checks(['oca_version'], ctx)[0]
    assert ctx.config['oca_version']['min_version'] == '1.64.0'
    assert result.status == 'FAIL' and result.metrics['versions']['rpm'] == '1.50.0-1'
    ctx.config['oca_version']['min_version'] = '1.49'
    assert run_checks(['oca_version'], ctx)[0].status == 'PASS'
    ctx.config['oca_version']['min_version'] = '1.51'
    assert run_checks(['oca_version'], ctx)[0].status == 'FAIL'
    ctx.config['oca_version']['min_version'] = '1.50.0~rc1'
    assert run_checks(['oca_version'], ctx)[0].status == 'FAIL'


def test_os_preference_fallback_and_missing_package(tmp_path, monkeypatch):
    ctx = context(tmp_path)
    ctx.config['oca_version']['min_version'] = '1.2.0'
    commands = []

    def execute(cmd, **kwargs):
        commands.append(cmd[0])
        if cmd[0] == 'cat':
            return RunResult('ID=ubuntu\nID_LIKE=debian\n', '', 0, 0)
        if cmd[0] == 'snap':
            return RunResult('Name Version Rev Tracking Publisher Notes\noracle-cloud-agent 1.3.0 4 stable oracle -\n', '', 0, 0)
        return RunResult('', 'not installed', 1, 0)

    monkeypatch.setattr(ctx, 'run', execute)
    result = run_checks(['oca_version'], ctx)[0]
    assert commands == ['cat', 'dpkg-query', 'snap', 'rpm']
    assert result.status == 'PASS' and result.metrics['versions'] == {'snap': '1.3.0'}
    monkeypatch.setattr(ctx, 'run', lambda *a, **k: RunResult('', 'unavailable', 127, 0))
    result = run_checks(['oca_version'], ctx)[0]
    assert result.status == 'WARN' and not result.metrics['versions']


def test_dry_run_previews_all_managers(tmp_path, capsys):
    ctx = context(tmp_path, dry_run=True)
    assert run_checks(['oca_version'], ctx)[0].status == 'SKIP'
    output = capsys.readouterr().out
    assert all(tool in output for tool in ('/etc/os-release', 'rpm', 'dpkg-query', 'snap'))


def test_prerelease_is_not_compared_as_final(tmp_path, monkeypatch):
    ctx = context(tmp_path)
    ctx.config['oca_version']['min_version'] = '1.2'

    def execute(cmd, **kwargs):
        if cmd[0] == 'cat':
            return RunResult('ID=ubuntu\n', '', 0, 0)
        if cmd[0] == 'dpkg-query':
            return RunResult('ii 1.3.0~rc1\n', '', 0, 0)
        return RunResult('', '', 1, 0)

    monkeypatch.setattr(ctx, 'run', execute)
    result = run_checks(['oca_version'], ctx)[0]
    assert result.status == 'WARN' and 'cannot safely compare' in result.message


def test_multi_host_uses_each_hosts_os_and_reports_each_version(tmp_path, monkeypatch):
    ctx = context(tmp_path)
    ctx.nodes = ['ol-host', 'ubuntu-host']
    ctx.config['oca_version']['min_version'] = '1.2'

    def execute(self, cmd, **kwargs):
        if cmd[0] == 'cat':
            os_id = 'ol' if self.target_node == 'ol-host' else 'ubuntu'
            return RunResult(f'ID={os_id}\n', '', 0, 0)
        if self.target_node == 'ol-host' and cmd[0] == 'rpm':
            return RunResult('1.3.0-1\n', '', 0, 0)
        if self.target_node == 'ubuntu-host' and cmd[0] == 'snap':
            return RunResult('oracle-cloud-agent 1.1.0 1 stable oracle -\n', '', 0, 0)
        return RunResult('', '', 1, 0)

    monkeypatch.setattr(RunContext, 'run', execute)
    result = run_checks(['oca_version'], ctx)[0]
    assert result.status == 'FAIL'
    assert result.metrics['hosts']['ol-host']['versions'] == {'rpm': '1.3.0-1'}
    assert result.metrics['hosts']['ubuntu-host']['versions'] == {'snap': '1.1.0'}
