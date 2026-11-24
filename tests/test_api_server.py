"""Controller validation and CLI integration without GPU hardware."""
import time

import pytest

from gputest.api_server import Controller


def test_nodes_reject_invalid_or_duplicate_hosts(tmp_path):
    controller = Controller(tmp_path)
    for nodes in ([{'host': '-bad'}], [{'host': 'node', 'user': '-bad'}],
                  [{'host': 'node', 'port': 0}], [{'host': 'node'}, {'host': 'node'}]):
        with pytest.raises(ValueError):
            controller.save_nodes(nodes)
    assert controller.save_nodes([{'host': 'gpu-1', 'user': 'opc', 'port': 2222}]) == [
        {'host': 'gpu-1', 'user': 'opc', 'port': 2222}]


def test_private_key_permissions_and_validation(tmp_path):
    controller = Controller(tmp_path)
    with pytest.raises(ValueError):
        controller.save_key('not a key')
    controller.save_key('-----BEGIN OPENSSH PRIVATE KEY-----\nexample\n-----END OPENSSH PRIVATE KEY-----\n')
    assert (tmp_path / 'controller_key').stat().st_mode & 0o777 == 0o600


def test_dry_run_creates_persistent_reports_and_uses_configured_ssh(tmp_path):
    controller = Controller(tmp_path)
    controller.save_nodes([{'host': 'gpu-1', 'user': 'opc', 'port': 2222}])
    job = controller.start_run({'sku': 'gb300', 'level': 'basic', 'nodes': ['gpu-1'],
                                'tests': ['nvidia_smi'], 'dry_run': True})
    deadline = time.monotonic() + 20
    while job['id'] in controller.active and time.monotonic() < deadline:
        time.sleep(0.05)
    saved = controller.job(job['id'])
    assert saved['status'] == 'completed'
    directory = tmp_path / job['id']
    assert 'Port 2222' in (directory / 'ssh_config').read_text()
    assert 'User opc' in (directory / 'ssh_config').read_text()
    assert '[dry-run]' in (directory / 'run.log').read_text()
    assert (directory / 'output' / 'results.json').exists()
    assert (directory / 'output' / 'results.md').exists()
    assert Controller(tmp_path).jobs()[0]['id'] == job['id']


def test_run_requires_registered_checks_and_configured_nodes(tmp_path):
    controller = Controller(tmp_path)
    controller.save_nodes([{'host': 'gpu-1'}])
    data = {'sku': 'gb300', 'level': 'basic', 'nodes': ['gpu-1'], 'tests': ['nvidia_smi']}
    with pytest.raises(ValueError):
        controller.start_run({**data, 'tests': ['not_a_check']})
    with pytest.raises(ValueError):
        controller.start_run({**data, 'nodes': []})
    with pytest.raises(ValueError):
        controller.start_run({**data, 'nodes': ['gpu-2']})
    with pytest.raises(ValueError):
        controller.start_run({**data, 'nodes': ['gpu-1', 'gpu-1']})
    with pytest.raises(ValueError):
        controller.job_dir('../nodes.json')
