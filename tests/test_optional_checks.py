"""Exercise opt-in checks without requiring network or storage hardware."""
from pathlib import Path

import gputest.checks  # noqa: F401
from gputest import parsers
from gputest.core import RunContext, RunResult, load_config, run_checks

ROOT = Path(__file__).resolve().parents[1]


def context(tmp_path, **kwargs):
    return RunContext(load_config(ROOT / 'config.yaml'), 'gb300', [], mock=True,
                      results_dir=tmp_path, **kwargs)


def test_optional_checks_disabled_by_default(tmp_path):
    names = ['nic_inventory', 'network_ping', 'tcp_bandwidth', 'lustre_client',
             'filesystem_perf', 'object_storage', 'object_upload']
    assert all(r.status == 'SKIP' for r in run_checks(names, context(tmp_path)))


def test_network_probes_and_thresholds(tmp_path):
    ctx = context(tmp_path)
    ctx.config['nic_inventory'].update(enabled=True, interfaces=[
        {'name': 'eth0', 'min_speed_mbps': 200000, 'peer_chassis': 'switch1', 'peer_port': 'Ethernet1'}])
    ctx.config['network_ping'].update(enabled=True, paths=[
        {'source': '2001:db8::1', 'target': '2001:db8::2', 'family': 'ipv6', 'vrf': 'vrf_r0'}])
    ctx.config['tcp_bandwidth'].update(enabled=True, paths=[
        {'source': '10.0.0.1', 'target': '10.0.0.2', 'port': 5201, 'min_gbps': 180}])
    results = run_checks(['nic_inventory', 'network_ping', 'tcp_bandwidth'], ctx)
    assert [r.status for r in results] == ['PASS', 'PASS', 'PASS']
    assert results[2].metrics['tests'][0]['gbps'] == 190
    ctx.config['nic_inventory']['interfaces'][0]['peer_port'] = 'wrong'
    ctx.config['tcp_bandwidth']['paths'][0]['min_gbps'] = 200
    assert [r.status for r in run_checks(['nic_inventory', 'tcp_bandwidth'], ctx)] == ['FAIL', 'FAIL']


def test_ping_partial_loss_and_seeded_sampling(tmp_path, monkeypatch):
    ctx = context(tmp_path)
    paths = [{'source': '10.0.0.1', 'target': f'10.0.0.{n}', 'family': 'ipv4'} for n in (2, 3, 4)]
    ctx.config['network_ping'].update(enabled=True, paths=paths, sample_count=1, seed=5)
    monkeypatch.setattr(ctx, 'run', lambda *a, **k: RunResult('5 packets transmitted, 4 received, 20% packet loss', '', 0, 1))
    a = run_checks(['network_ping'], ctx)[0]
    b = run_checks(['network_ping'], ctx)[0]
    assert a.status == 'FAIL' and a.metrics['tests'] == b.metrics['tests']
    assert len(a.metrics['tests']) == 1


def test_lustre_and_fio_safety_and_thresholds(tmp_path, capsys):
    ctx = context(tmp_path)
    ctx.config['lustre_client'].update(enabled=True, path='/lustre')
    ctx.config['filesystem_perf'].update(enabled=True, jobs=[
        {'rw': 'read', 'file': '/mnt/test', 'block_size': '1M', 'iodepth': 1, 'min_mib_s': 900},
        {'rw': 'write', 'directory': '/mnt/testdir', 'size': '1G', 'block_size': '1M', 'iodepth': 1, 'min_iops': 900}])
    assert [r.status for r in run_checks(['lustre_client', 'filesystem_perf'], ctx)] == ['PASS', 'PASS']
    ctx.dry_run = True
    assert run_checks(['filesystem_perf'], ctx)[0].status == 'SKIP'
    output = capsys.readouterr().out
    assert '--readonly' in output and '--allow_file_create=0' in output and '--unlink=1' in output
    assert '/mnt/testdir/gputest-' in output


def test_object_tests_use_unique_paths_and_cleanup(tmp_path, capsys):
    ctx = context(tmp_path, dry_run=True)
    ctx.config['object_storage'].update(enabled=True, bucket='bucket', object='existing', scratch_dir='/tmp')
    ctx.config['object_upload'].update(enabled=True, bucket='bucket', source_file='/tmp/source', prefix='tests')
    assert all(r.status == 'SKIP' for r in run_checks(['object_storage', 'object_upload'], ctx))
    output = capsys.readouterr().out
    assert 'object get' in output and 'object put' in output and 'object delete' in output
    assert '--if-none-match' in output and 'rm -f -- /tmp/gputest-object-' in output
    ctx.dry_run = False
    assert all(r.status == 'WARN' for r in run_checks(['object_storage', 'object_upload'], ctx))


def test_parser_rejects_failed_tools_and_bad_metrics():
    import pytest

    assert parsers.parse_ping_loss('5 packets transmitted, 4 received, 20% packet loss')['loss_pct'] == 20
    with pytest.raises(ValueError):
        parsers.parse_iperf3('{"error":"connection failed"}')
    with pytest.raises(ValueError):
        parsers.parse_fio('{"jobs":[{"error":5}]}', False)


def test_object_download_failure_still_removes_temporary_file(tmp_path, monkeypatch):
    ctx = context(tmp_path)
    ctx.config['object_storage'].update(enabled=True, bucket='bucket', object='existing', scratch_dir='/tmp')
    commands = []

    def execute(cmd, **kwargs):
        commands.append(cmd)
        return RunResult('', 'download failed', 1, 1) if cmd[0] == 'oci' else RunResult('0', '', 0, 1)

    monkeypatch.setattr(ctx, 'run', execute)
    assert run_checks(['object_storage'], ctx)[0].status == 'FAIL'
    assert commands[-1][:3] == ['rm', '-f', '--']
    assert commands[-1][-1].startswith('/tmp/gputest-object-')


def test_object_upload_does_not_delete_on_failed_create(tmp_path, monkeypatch):
    ctx = context(tmp_path)
    ctx.config['object_upload'].update(enabled=True, bucket='bucket', source_file='/tmp/source', prefix='tests')
    commands = []

    def execute(cmd, **kwargs):
        commands.append(cmd)
        return RunResult('1024 file', '', 0, 1) if cmd[0] == 'wc' else RunResult('', 'failed', 1, 1)

    monkeypatch.setattr(ctx, 'run', execute)
    result = run_checks(['object_upload'], ctx)[0]
    assert result.status == 'FAIL' and 'possible incomplete object' in result.message
    assert not any('delete' in cmd for cmd in commands)
