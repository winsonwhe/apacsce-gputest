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
