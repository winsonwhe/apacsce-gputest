import pytest

from gputest.cli import _node_selection, build_parser
from gputest.core import RunContext


def test_host_selection_combines_options_and_file(tmp_path):
    hosts = tmp_path / 'hosts.txt'
    hosts.write_text('# rack\nbob@192.0.2.2\n192.0.2.3, 192.0.2.4 # comment\n')
    args = build_parser().parse_args(['run', '--sku', 'a10', '--node', '192.0.2.1',
                                      '--hostfile', str(hosts), '--user', 'opc'])
    nodes, users = _node_selection(args)
    assert nodes == ['192.0.2.1', '192.0.2.2', '192.0.2.3', '192.0.2.4']
    assert users == {'192.0.2.1': 'opc', '192.0.2.2': 'bob',
                     '192.0.2.3': 'opc', '192.0.2.4': 'opc'}
    ctx = RunContext({}, 'a10', nodes, ssh_users=users)
    assert ctx.ssh_target(nodes[1]) == 'bob@192.0.2.2'


@pytest.mark.parametrize('targets', ['', 'host,host', '@host', '-bad', 'a@b@c'])
def test_reject_invalid_or_empty_targets(targets):
    args = build_parser().parse_args(['run', '--sku', 'a10', '--nodes=' + targets])
    with pytest.raises(ValueError):
        _node_selection(args)


def test_setup_ssh_uses_per_host_user(tmp_path, monkeypatch, capsys):
    from gputest import cli
    hosts = tmp_path / 'hosts'
    hosts.write_text('alice@host1\nhost2\n')
    monkeypatch.setattr(cli.Path, 'home', classmethod(lambda cls: tmp_path))
    args = build_parser().parse_args(['setup-ssh', '--hostfile', str(hosts), '--user', 'opc', '--dry-run'])
    cli.cmd_setup_ssh(args, cli.load_config('config.yaml'))
    output = capsys.readouterr().out
    assert 'alice@host1' in output
    assert 'opc@host2' in output


def test_setup_ssh_accepts_shared_private_key(tmp_path, monkeypatch, capsys):
    from gputest import cli
    key = tmp_path / 'shared_ed25519'
    monkeypatch.setattr(cli.Path, 'home', classmethod(lambda cls: tmp_path))
    args = build_parser().parse_args([
        'setup-ssh', '--nodes', 'host1,host2', '--private-key', str(key), '--dry-run'
    ])
    cli.cmd_setup_ssh(args, cli.load_config('config.yaml'))
    output = capsys.readouterr().out
    assert f'-i {key}' in output
    assert 'scp' in output
