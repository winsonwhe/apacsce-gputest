"""Stress checks: native output, failures, build plans and monitoring without GPUs."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from threading import Event

import pytest

from gputest import checks, parsers
from gputest.core import (
    RunContext,
    RunResult,
    load_config,
    run,
    run_checks,
    run_sampled,
)

FIXTURES = Path(__file__).resolve().parent.parent / 'fixtures'


def fixture(name):
    return (FIXTURES / name).read_text()


@pytest.fixture
def ctx(tmp_path):
    config = load_config(FIXTURES.parent / 'config.yaml')
    for key in ('nvbandwidth', 'babelstream'):
        config[key]['build_if_missing'] = False
    return RunContext(config, 'gb300', [], mock=True, results_dir=tmp_path)


def success(stdout=''):
    return RunResult(stdout, '', 0, 0)


def test_babelstream_native_units():
    parsed = parsers.parse_babelstream(fixture('babelstream_native.txt'))
    assert parsed['benchmarks']['copy'] == pytest.approx([950.12])
    assert len(parsed['benchmarks']) == 5


def test_named_nvbandwidth_sum():
    text = fixture('nvbandwidth_native.txt')
    assert parsers.parse_nvbandwidth(text, 'device_to_device_memcpy_read_sm')['sum_gbs'] == 123.45
    assert parsers.parse_nvbandwidth(text, 'missing')['sum_gbs'] is None
    assert parsers.parse_nvbandwidth('Running first.\nRunning second.\nSUM 12 GB/s',
                                     'first')['sum_gbs'] is None


def test_native_dcgm():
    result = parsers.parse_dcgmi_json(fixture('dcgmi_native.json'))
    assert result['status'] == 'FAIL'
    assert [t['result'] for t in result['tests']] == ['PASS', 'WARN', 'FAIL']
    assert result['tests'][1]['results'][0]['warnings']


@pytest.mark.parametrize('text', ['', 'not json', '{}', '[]', 'null',
                                  '{"DCGM Diagnostic":{"runtime_error":"failed"}}'])
def test_invalid_dcgm_cannot_pass(text):
    assert parsers.parse_dcgmi_json(text)['status'] == 'FAIL'


@pytest.mark.parametrize(('value', 'status'), [('Pass', 'PASS'), ('Warn', 'WARN'),
                                               ('Skip', 'SKIP'), ('unknown', 'WARN')])
def test_dcgm_summary_status(value, status):
    text = json.loads(fixture('dcgmi_native.json'))
    tests = text['DCGM Diagnostic']['test_categories'][0]['tests']
    tests[:] = [{'name': 'test', 'results': [{'status': value}]}]
    assert parsers.parse_dcgmi_json(json.dumps(text))['status'] == status


def test_samples_keep_peak_and_ignore_na():
    peaks = parsers.parse_gpu_samples(fixture('gpu_samples.txt') + '\n0, N/A, nan\n1, N/A, inf')
    assert peaks['0'] == {'temp_c': 65, 'power_w': 1150.75}
    assert peaks['1']['power_w'] == 1140


def test_fryer_is_explicit_test_name(ctx):
    result = run_checks(['gpu_fryer'], ctx)[0]
    assert result.name == 'gpu_fryer'
    assert result.status == 'PASS'
    assert result.metrics['backend'] == 'gpu-fryer'


@pytest.mark.parametrize('name', ['nvbandwidth', 'babelstream', 'dcgmi'])
def test_missing_tools_skip(ctx, monkeypatch, name):
    monkeypatch.setattr(ctx, 'run', lambda *a, **kw: RunResult('', 'command not found', 127, 0))
    assert run_checks([name], ctx)[0].status == 'SKIP'


def test_babelstream_each_gpu_and_threshold(ctx, monkeypatch):
    seen = []

    def execute(cmd, **kwargs):
        seen.append(cmd)
        text = fixture('babelstream_native.txt')
        if cmd[-1] == '3':
            text = text.replace('950120', '850120')
        return success(text)

    monkeypatch.setattr(ctx, 'run', execute)
    result = checks.babelstream(ctx)
    assert result.status == 'FAIL'  # one slow GPU must not be hidden by a mean
    assert [cmd[-1] for cmd in seen] == ['0', '1', '2', '3']
    assert result.metrics['copy_spread_gbs'] == pytest.approx(100)
    assert result.metrics['gpu_count'] == 4


def test_babelstream_incomplete_output_fails(ctx, monkeypatch):
    monkeypatch.setattr(ctx, 'run', lambda *a, **kw: success(''))
    assert checks.babelstream(ctx).status == 'FAIL'


def test_babelstream_incompatible_cuda_binary(ctx, monkeypatch):
    ctx.sku = 'a10'
    output = 'Error: no kernel image is available for execution on the device'
    monkeypatch.setattr(ctx, 'run', lambda *a, **kw: RunResult('', output, 1, 0))
    result = checks.babelstream(ctx)
    assert result.status == 'FAIL'
    assert 'sm_86' in result.message
    assert output in result._raw


def test_nvbandwidth_threshold_and_missing_sum(ctx, monkeypatch):
    ctx.sku = 'a10'
    monkeypatch.setattr(ctx, 'run', lambda *a, **kw: success(fixture('nvbandwidth_a10.txt')))
    assert checks.nvbandwidth(ctx).status == 'PASS'
    cfg = ctx.config['nvbandwidth']['tests']['a10']
    cfg['thresholds'][cfg['test_names'][0]] = 100
    assert checks.nvbandwidth(ctx).status == 'FAIL'
    monkeypatch.setattr(ctx, 'run', lambda *a, **kw: success(''))
    assert checks.nvbandwidth(ctx).status == 'FAIL'


def test_nvbandwidth_waived_p2p_is_skipped(ctx, monkeypatch):
    ctx.sku = 'a10'
    def execute(cmd, **kwargs):
        test_name = cmd[-1]
        return success(
            f'Waived {test_name}: no accessible peer GPU pairs '
            '(P2P not supported between any devices)\n'
        )
    monkeypatch.setattr(ctx, 'run', execute)
    result = checks.nvbandwidth(ctx)
    assert result.status == 'SKIP'
    assert 'waived' in result.message
    assert 'P2P not supported' in result.metrics[
        'device_to_device_bidirectional_memcpy_read_ce_waived_reason']


@pytest.mark.parametrize(('level', 'diag_level'), [('basic', 1), ('standard', 2), ('extended', 3)])
def test_dcgm_level(ctx, monkeypatch, level, diag_level):
    ctx.config['_level'] = level
    seen = []

    def execute(cmd, **kwargs):
        seen.append((cmd, kwargs))
        return success(fixture('dcgmi_native.json'))

    monkeypatch.setattr(ctx, 'run', execute)
    result = checks.dcgmi(ctx)
    assert seen[0][0][-3:] == ['-r', str(diag_level), '-j']
    assert seen[0][1]['timeout'] == 3600
    assert result.status == 'FAIL'
    assert result.metrics['test_count'] == 3
    assert result.metrics['warn'] == 1


def test_dcgm_failure_exit_retains_tests(ctx, monkeypatch):
    monkeypatch.setattr(ctx, 'run', lambda *a, **kw: RunResult(fixture('dcgmi_native.json'), '', 1, 0))
    result = checks.dcgmi(ctx)
    assert result.status == 'FAIL' and result.metrics['test_count'] == 3


def test_build_dry_run(ctx, capsys):
    ctx.dry_run, ctx.mock = True, False
    for section in ('babelstream', 'nvbandwidth'):
        ctx.config[section]['build_if_missing'] = True
    ctx.config['cuda']['path'] = '/test/cuda'
    results = run_checks(['babelstream', 'nvbandwidth'], ctx)
    assert all(r.status == 'SKIP' for r in results)
    output = capsys.readouterr().out
    assert '-DCUDA_ARCH=sm_103' in output
    assert '-DCMAKE_CUDA_COMPILER=/test/cuda/bin/nvcc' in output
    assert '-DCMAKE_CUDA_ARCHITECTURES=103' in output
    assert 'git clone' in output


def test_multinode_dry_run(ctx, capsys):
    ctx.dry_run, ctx.nodes = True, ['host1', 'host2']
    cfg = ctx.config['nvbandwidth']
    cfg['multinode'] = True
    cfg['tests']['gb300']['test_names'] = ['multinode_device_to_device_memcpy_read_sm']
    assert checks.nvbandwidth(ctx).status == 'SKIP'
    output = capsys.readouterr().out
    assert '--host host1,host2 --map-by ppr:4:node -np 8' in output


def test_sampling_overlaps_workload(ctx, monkeypatch):
    ctx.mock = False
    started, sampled = Event(), Event()

    def execute(cmd, **kwargs):
        if '--query-gpu=index,temperature.gpu,power.draw' in cmd:
            assert started.wait(2)
            sampled.set()
            return success('0, 60, 500')
        started.set()
        assert sampled.wait(2)
        return success('done')

    monkeypatch.setattr(ctx, 'run', execute)
    rr, samples, error = run_sampled(ctx, ['workload'], timeout=5, fixture='unused')
    assert rr.stdout == 'done' and '0, 60, 500' in samples and not error


def test_timeout_retains_partial_output(tmp_path, monkeypatch):
    def execute(*a, **kw):
        raise subprocess.TimeoutExpired(['test'], 1, output=b'partial', stderr=b'problem')

    monkeypatch.setattr(subprocess, 'run', execute)
    result = run([sys.executable], timeout=1, results_dir=tmp_path)
    assert result.returncode == -1 and result.stdout == 'partial'
    raw = next(tmp_path.iterdir()).read_text()
    assert 'partial' in raw and 'problem' in raw and 'timeout' in raw


def test_cli_level_reaches_check(ctx, monkeypatch, tmp_path):
    from gputest import cli

    args = cli.build_parser().parse_args([
        'run', '--sku', 'gb300', '--level', 'basic', '--tests', 'dcgmi', '--mock',
        '--network-mode', 'single_plane',
    ])
    ctx.config['network']['mode'] = 'single_plane'
    monkeypatch.chdir(tmp_path)
    cli.cmd_run(args, ctx.config)
    report = next(tmp_path.glob('results/*/results.json'))
    assert json.loads(report.read_text())['checks'][0]['metrics']['level'] == 1
    assert json.loads(report.read_text())['checks'][0]['status'] == 'PASS'


def test_extended_dcgm_level_four_override(ctx, monkeypatch):
    ctx.config['_level'] = 'extended'
    ctx.config['dcgmi']['diag_levels']['extended'] = 4
    result = checks.dcgmi(ctx)
    assert result.status == 'PASS' and result.metrics['level'] == 4


def test_clock_event_legacy_fallback(ctx, monkeypatch):
    calls = []

    def execute(cmd, **kwargs):
        calls.append(cmd[1])
        if 'clocks_event_reasons' in cmd[1]:
            return RunResult('', 'unknown field', 1, 0)
        return success('0, 0x0000000000000000')

    monkeypatch.setattr(ctx, 'run', execute)
    assert checks.clocks_throttle(ctx).status == 'PASS'
    assert 'clocks_throttle_reasons.active' in calls[1]


def test_clock_event_unavailable_warns(ctx, monkeypatch):
    monkeypatch.setattr(ctx, 'run', lambda *a, **kw: RunResult('', 'unsupported', 1, 0))
    assert checks.clocks_throttle(ctx).status == 'WARN'
