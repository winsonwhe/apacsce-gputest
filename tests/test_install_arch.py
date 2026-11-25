import os
import shlex
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(('output', 'expected', 'ok'), [
    ('8.6\n8.6\n', 'sm_86', True),
    ('10.3\n', 'sm_103', True),
    ('8.6\n9.0\n', 'Mixed GPU', False),
    ('N/A\n', 'Invalid GPU', False),
    ('', 'Cannot detect', False),
])
def test_install_detect_cuda_arch(tmp_path, output, expected, ok):
    script = (Path(__file__).resolve().parents[1] / 'install.sh').read_text()
    function = script[script.index('detect_cuda_arch() {'):script.index('\ninstall_gpu_tools() {')]
    smi = tmp_path / 'nvidia-smi'
    smi.write_text('#!/bin/sh\nprintf %s ' + shlex.quote(output) + '\n')
    smi.chmod(0o755)
    env = {**os.environ, 'PATH': str(tmp_path) + os.pathsep + os.environ['PATH']}
    env.pop('CUDA_ARCH', None)
    result = subprocess.run(['bash', '-c', function + '\ndetect_cuda_arch'],
                            env=env, text=True, capture_output=True, check=False)
    assert (result.returncode == 0) == ok
    assert expected in result.stdout + result.stderr


def test_control_plane_skips_local_gpu_build_and_targets_inventory(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'install.sh'
    (tmp_path / 'install.sh').write_text(script.read_text())
    (tmp_path / 'requirements.txt').touch()
    (tmp_path / 'gputest').mkdir()
    (tmp_path / 'all_gpu_nodes.txt').write_text('gpu-node\n')
    ssh = tmp_path / 'ssh'
    ssh.write_text('#!/bin/sh\ncat >/dev/null\nprintf "ssh target: %s\\n" "$3"\n')
    ssh.chmod(0o755)
    env = {**os.environ, 'PATH': str(tmp_path) + os.pathsep + os.environ['PATH']}
    env.pop('GPUTEST_GPU_TOOLS_WORKER', None)
    result = subprocess.run(
        ['bash', str(tmp_path / 'install.sh'), '--control-plane', '--gpu-tools'],
        env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert 'skipping local GPU tool builds' in result.stdout
    assert 'Building GPU tools on ubuntu@gpu-node' in result.stdout
    assert 'ssh target: ubuntu@gpu-node' in result.stdout


def test_gpu_less_host_auto_skips_local_gpu_build(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'install.sh'
    (tmp_path / 'install.sh').write_text(script.read_text())
    (tmp_path / 'requirements.txt').touch()
    (tmp_path / 'gputest').mkdir()
    (tmp_path / 'all_gpu_nodes.txt').write_text('gpu-node\n')
    ssh = tmp_path / 'ssh'
    ssh.write_text('#!/bin/sh\ncat >/dev/null\nprintf "ssh target: %s\\n" "$3"\n')
    ssh.chmod(0o755)
    env = {**os.environ, 'PATH': str(tmp_path) + os.pathsep + os.environ['PATH']}
    env.pop('GPUTEST_GPU_TOOLS_WORKER', None)
    result = subprocess.run(
        ['bash', str(tmp_path / 'install.sh'), '--gpu-tools'],
        env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert 'No local NVIDIA GPU detected' in result.stdout
    assert 'skipping local GPU tool builds' in result.stdout
    assert 'Building GPU tools on ubuntu@gpu-node' in result.stdout


def test_gpu_less_host_skips_local_python_checks(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'install.sh'
    (tmp_path / 'install.sh').write_text(script.read_text())
    (tmp_path / 'requirements.txt').touch()
    (tmp_path / 'gputest').mkdir()
    (tmp_path / '.venv' / 'bin').mkdir(parents=True)
    (tmp_path / '.venv' / 'bin' / 'activate').write_text('')
    log = tmp_path / 'python.log'
    fake_python = tmp_path / 'python3'
    fake_python.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> {shlex.quote(str(log))}\n')
    fake_python.chmod(0o755)
    env = {**os.environ, 'PATH': str(tmp_path) + os.pathsep + os.environ['PATH']}
    env.pop('GPUTEST_GPU_TOOLS_WORKER', None)
    result = subprocess.run(
        ['bash', str(tmp_path / 'install.sh'), '--control-plane', '--python'],
        env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert 'skipping local pytest and Ruff checks' in result.stdout
    python_calls = log.read_text()
    assert '-m pytest' not in python_calls
    assert '-m ruff' not in python_calls
