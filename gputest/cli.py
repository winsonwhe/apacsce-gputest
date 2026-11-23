"""CLI entry point: list / run / report."""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

# Ensure the repo root is on the path so gputest is importable when running
# as `python -m gputest.cli` or via the `gputest` wrapper.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gputest.checks  # noqa: F401 — registers all checks as side-effect
from gputest.core import (
    Result,
    RunContext,
    get_registry,
    load_config,
    print_summary,
    run,
    run_checks,
    write_json,
    write_markdown,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _node_selection(args, *, required=False):
    """Read SSH targets from repeated options and a plain-text host file."""
    entries = []
    for value in getattr(args, 'nodes', None) or []:
        entries.extend(re.split(r'[,\s]+', value.strip()))
    hostfile = getattr(args, 'hostfile', None)
    if hostfile:
        try:
            for line in Path(hostfile).read_text().splitlines():
                entries.extend(re.split(r'[,\s]+', line.split('#', 1)[0].strip()))
        except OSError as exc:
            raise ValueError(f'cannot read hostfile {hostfile}: {exc}') from exc
    nodes, users = [], {}
    default_user = getattr(args, 'user', None)
    if default_user and not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', default_user):
        raise ValueError('invalid SSH user')
    for entry in filter(None, entries):
        user, sep, host = entry.partition('@')
        if not sep:
            host, user = user, default_user
        elif not user:
            raise ValueError(f'invalid SSH target: {entry}')
        if (not host or host.startswith('-') or '@' in host
                or not re.fullmatch(r'[A-Za-z0-9_.:%-]+', host)
                or (user and not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', user))):
            raise ValueError(f'invalid SSH target: {entry}')
        if host in nodes:
            raise ValueError(f'duplicate host: {host}')
        nodes.append(host)
        if user:
            users[host] = user
    if required and not nodes:
        raise ValueError('provide at least one host with --nodes, --node, or --hostfile')
    if (hostfile or getattr(args, 'nodes', None)) and not nodes:
        raise ValueError('host selection is empty')
    return nodes, users


def _add_host_options(parser):
    parser.add_argument('--nodes', '--node', action='append', metavar='HOST[,HOST...]',
                        help='SSH targets; repeat or separate with commas or spaces. Optional user@host.')
    parser.add_argument('--hostfile', help='Text file of SSH targets, one or more per line; # starts a comment.')
    parser.add_argument('--user', help='Default SSH user; user@host overrides it.')


def _detect_network_mode(config: dict, ctx: RunContext | None = None) -> str:
    """Detect on target hosts through run(), respecting dry-run and mock mode."""
    cfg = config['network']
    if cfg.get('mode', 'auto') != 'auto':
        return cfg['mode']
    ctx = ctx or RunContext(config, 'gb300', [])
    command = [config['tools']['curl'], '-fsSL', '--max-time', str(cfg['imds_timeout_s']),
               '-H', 'Authorization: Bearer Oracle', cfg['imds_url']]
    results = ctx.run_parallel([{'cmd': command, 'node': node, 'timeout': cfg['imds_timeout_s'] + 5,
                                    'mock_fixture': 'imds_host.json'} for node in (ctx.nodes or [None])])
    modes = set()
    for rr in results:
        if rr.skipped:
            print('[dry-run] IMDS unavailable without execution; using network.fallback_mode. '
                  'Pass --network-mode to preview a specific mode.')
        try:
            data = json.loads(rr.stdout) if rr.returncode == 0 and not rr.skipped else None
            planes = data.get('rdmaFabricData', {}).get('planes') if data else None
            if data is not None and planes not in (None, 1, 4):
                raise ValueError(f'unsupported IMDS plane count: {planes}')
            modes.add(('multiplanar' if planes == 4 else 'single_plane') if data is not None
                      else cfg['fallback_mode'])
        except json.JSONDecodeError:
            modes.add(cfg['fallback_mode'])
    if len(modes) != 1:
        raise ValueError('mixed network modes across target hosts')
    return modes.pop()


def _resolve_checks(level: str, tests_override: str | None, config: dict) -> list[str]:
    """Return the ordered list of check names to run."""
    if tests_override:
        return list(dict.fromkeys(t.strip() for t in tests_override.split(",") if t.strip()))
    levels = config.get("levels", {})
    if level not in levels:
        print(f"Unknown level {level!r}. Available: {', '.join(levels)}", file=sys.stderr)
        sys.exit(1)
    return levels[level]


# ---------------------------------------------------------------------------
# sub-commands
# ---------------------------------------------------------------------------

def cmd_list(_args, config: dict) -> None:
    registry = get_registry()
    if not registry:
        print("No checks registered.")
        return
    w_name = max(len(c["name"]) for c in registry)
    w_cat = max(len(c["category"]) for c in registry)
    print(f"{'NAME':<{w_name}}  {'CATEGORY':<{w_cat}}  SKUs              MULTI-HOST")
    print("-" * (w_name + w_cat + 30))
    for c in registry:
        skus = ",".join(c["skus"]) if c["skus"] else "all"
        mh = "yes" if c["multi_host"] else "no"
        print(f"{c['name']:<{w_name}}  {c['category']:<{w_cat}}  {skus:<16}  {mh}")


def cmd_run(args, config: dict) -> None:
    if not args.sku:
        print("--sku is required", file=sys.stderr)
        sys.exit(1)

    known_skus = set(config.get("skus", {}).keys())
    if args.sku not in known_skus:
        print(f"Unknown SKU {args.sku!r}. Known: {', '.join(sorted(known_skus))}", file=sys.stderr)
        sys.exit(1)

    # --gpu-count overrides the SKU default (for partial A10 hosts: 1, 2, 3, or 4 GPUs)
    if getattr(args, "gpu_count", None) is not None:
        config.setdefault("skus", {})[args.sku]["gpu_count"] = args.gpu_count

    config["_level"] = args.level
    checks = _resolve_checks(args.level, getattr(args, "tests", None), config)

    run_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    results_dir = Path(getattr(args, "output_dir", None) or (Path("results") / f"run-{run_id}"))

    nodes, users = _node_selection(args)

    ctx = RunContext(
        config=config,
        sku=args.sku,
        nodes=nodes,
        ssh_users=users,
        dry_run=getattr(args, "dry_run", False),
        mock=getattr(args, "mock", False),
        network_mode=config["network"]["fallback_mode"],
        baseline=getattr(args, "baseline", None),
        baseline_file=Path(getattr(args, "baseline_file", "baseline.json")),
        node_count=getattr(args, "node_count", None),
        results_dir=results_dir,
    )

    detection_error = None
    try:
        ctx.network_mode = _detect_network_mode(config, ctx)
    except (ValueError, AttributeError, TypeError) as exc:
        detection_error = str(exc)
    network_mode = ctx.network_mode

    print(f"gputest run  sku={args.sku}  level={args.level}  "
          f"network={network_mode}  nodes={nodes or ['localhost']}")
    print()

    if detection_error:
        from gputest.reporting import annotate
        result = Result('network_mode', 'FAIL', detection_error)
        annotate(result, ctx)
        results = [result]
    else:
        results = run_checks(checks, ctx)

    print_summary(results)

    run_meta = {
        "run_id": run_id,
        "sku": args.sku,
        "level": args.level,
        "network_mode": network_mode,
        "nodes": nodes or ["localhost"],
        "burn_duration_s": ctx.burn_duration_s(),
        "dry_run": ctx.dry_run,
        "mock": ctx.mock,
        "config_file": str(Path(getattr(args, "config", "config.yaml")).resolve()),
    }
    jpath = write_json(results, run_meta, results_dir)
    mpath = write_markdown(results, run_meta, results_dir)
    print(f"\nJSON (machine-readable): {jpath}")
    print(f"Markdown (human-readable): {mpath}")
    if ctx.dry_run:
        print("Raw output: not saved in dry-run mode")
    else:
        print(f"Raw results: {results_dir}")
    return int(any(r.status == "FAIL" for r in results))


def cmd_setup_ssh(args, config: dict) -> None:
    """Install one shared SSH identity and peer trust on every selected node."""
    nodes, users = _node_selection(args, required=True)
    dry_run = args.dry_run
    tools = config['tools']
    ssh_dir = Path.home() / '.ssh'
    key = Path(args.private_key).expanduser() if args.private_key else ssh_dir / 'id_ed25519'
    public_key = Path(str(key) + '.pub')
    targets = [f'{users[n]}@{n}' if n in users else n for n in nodes]
    failed = []

    def execute(cmd):
        return run(cmd, dry_run=dry_run, timeout=config['executor']['setup_timeout_s'],
                   results_dir=None if dry_run else Path('results/ssh-setup'))

    if not key.exists() and args.private_key and not dry_run:
        print(f'Private key does not exist: {key}', file=sys.stderr)
        return 1
    if not key.exists():
        if not dry_run:
            ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        rr = execute([tools['ssh_keygen'], '-t', 'ed25519', '-N', '', '-f', str(key)])
        if rr.returncode:
            print(rr.stderr)
            return 1
    if not public_key.exists() and not dry_run:
        rr = execute([tools['ssh_keygen'], '-y', '-f', str(key)])
        if rr.returncode or not rr.stdout.strip():
            print(rr.stderr or f'cannot derive public key from {key}', file=sys.stderr)
            return 1
        public_key.write_text(rr.stdout.strip() + '\n')
        public_key.chmod(0o644)

    ssh_opts = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                '-o', 'StrictHostKeyChecking=accept-new', '-i', str(key)]
    peer_hosts = ' '.join(n.split('@')[-1] for n in targets)
    for target in targets:
        # The bootstrap identity must already be accepted by the image.  The
        # private key is then copied to each node so launcher-to-peer SSH uses
        # the same identity everywhere.
        prepare_dir = execute([tools['ssh'], *ssh_opts, '--', target,
                               'umask 077; mkdir -p ~/.ssh; chmod 700 ~/.ssh'])
        copy_key = execute([tools['scp'], *ssh_opts, str(key), f'{target}:.ssh/id_ed25519'])
        copy_pub = execute([tools['scp'], *ssh_opts, str(public_key), f'{target}:.ssh/id_ed25519.pub'])
        prepare = execute([tools['ssh'], *ssh_opts, '--', target,
                           ("umask 077; mkdir -p ~/.ssh; chmod 700 ~/.ssh; "
                            "cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys; "
                            "sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys; "
                            "chmod 600 ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub ~/.ssh/authorized_keys")])
        scan = execute([tools['ssh_keyscan'], '-H', target.split('@')[-1]])
        trust = execute([tools['ssh'], *ssh_opts, '--', target,
                         (f'ssh-keyscan -H {peer_hosts} >> ~/.ssh/known_hosts; '
                          'sort -u ~/.ssh/known_hosts -o ~/.ssh/known_hosts; '
                          'chmod 600 ~/.ssh/known_hosts')])
        if any(rr.returncode for rr in (prepare_dir, copy_key, copy_pub, prepare, scan, trust)):
            failed.append(target)
        if not dry_run and scan.returncode == 0 and scan.stdout.strip():
            ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = ssh_dir / 'known_hosts'
            existing = path.read_text().splitlines() if path.exists() else []
            extra = [line for line in scan.stdout.splitlines() if line and line not in existing]
            if extra:
                with path.open('a') as stream:
                    stream.write('\n'.join(extra) + '\n')
                path.chmod(0o600)
    print('Dry-run only: no keys changed.' if dry_run else f'SSH setup failures: {sorted(set(failed))}')
    print('All selected nodes receive the same private/public key pair and peer host keys.')
    return int(bool(failed))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def cmd_report(args, _config: dict) -> None:
    result_dir = Path(args.result_dir)
    json_path = result_dir / "results.json"
    if not json_path.exists():
        print(f"No results.json in {result_dir}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(json_path.read_text())
    results = [
        Result(
            name=c["name"],
            status=c["status"],
            message=c.get("message", ""),
            metrics=c.get("metrics", {}),
            raw_output_file=c.get("raw_output_file"),
            thresholds=c.get("thresholds", []),
            hints=c.get("hints", []),
        )
        for c in data.get("checks", [])
    ]
    write_markdown(results, {k: v for k, v in data.items() if k != "checks"}, result_dir)
    print_summary(results)


def _positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gputest",
        description="GPU validation toolkit for OCI NVIDIA GPU hosts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    sub.add_parser("list", help="List all registered checks.")

    # run
    run_p = sub.add_parser("run", help="Run checks.")
    # SKU/level names come from the selected YAML file, so argparse must not
    # freeze them to the repository defaults (custom deployments may add one).
    run_p.add_argument("--sku", required=True,
                       help="Hardware SKU; see the skus keys in --config "
                            "(default config: a10, a100, h100, h200, l40s, b200, gb200, gb300, b300).")
    run_p.add_argument("--level", default="standard",
                       help="Level from the levels keys in --config (default: standard; "
                            "default config also includes basic, extended and SKU-prefixed aliases).")
    run_p.add_argument("--gpu-count", type=_positive_int, default=None,
                       help="Override expected GPU count (useful for partial A10 hosts).")
    run_p.add_argument("--tests", metavar="CHECK,CHECK,...",
                       help="Override level with comma-separated check names; "
                            "use 'python3 -m gputest.cli list' to see names.")
    _add_host_options(run_p)
    run_p.add_argument("--node-count", type=_positive_int,
                       help="Select this many NCCL nodes from --nodes using GMF placement.")
    run_p.add_argument("--output-dir", help="Directory for JSON, Markdown and raw output "
                       "(default: results/run-<timestamp>).")
    run_p.add_argument("--baseline", choices=["save", "compare"],
                       help="save: record a known-good baseline; compare: compare results against it.")
    run_p.add_argument("--baseline-file", default="baseline.json",
                       help="Baseline JSON path (default: baseline.json).")
    run_p.add_argument("--dry-run", action="store_true",
                       help="Print commands without executing them.")
    run_p.add_argument("--mock", action="store_true",
                       help="Read outputs from fixtures/ instead of running commands.")
    run_p.add_argument("--network-mode", choices=["auto", "single_plane", "multiplanar"],
                       default=None,
                       help="Override config: auto detects via IMDS and uses fallback_mode on failure; "
                            "single_plane or multiplanar selects that mode explicitly.")
    run_p.add_argument("--config", default="config.yaml",
                       help="Path to config.yaml (default: config.yaml).")

    # report
    rep_p = sub.add_parser("report", help="Re-render a saved result directory.")
    rep_p.add_argument("result_dir", help="Path to a results/run-<timestamp>/ directory.")

    # setup-ssh
    ssh_p = sub.add_parser(
        "setup-ssh",
        help="Configure passwordless SSH between this host and --nodes (required for NCCL).",
    )
    _add_host_options(ssh_p)
    ssh_p.add_argument("--dry-run", action="store_true",
                       help="Print commands without executing them.")
    ssh_p.add_argument("--private-key", metavar="PATH",
                       help="Private key to install on every node (default: ~/.ssh/id_ed25519); "
                            "its public key must already allow bootstrap SSH.")
    ssh_p.add_argument("--config", default="config.yaml",
                       help="Path to config.yaml (default: config.yaml).")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    config_path = getattr(args, "config", "config.yaml")
    config = load_config(config_path)

    # CLI override for network mode
    if getattr(args, "network_mode", None):
        config.setdefault("network", {})["mode"] = args.network_mode

    dispatch = {
        "list": cmd_list,
        "run": cmd_run,
        "report": cmd_report,
        "setup-ssh": cmd_setup_ssh,
    }
    try:
        status = dispatch[args.command](args, config)
    except ValueError as exc:
        parser.error(str(exc))
    if status:
        sys.exit(status)


if __name__ == "__main__":
    main()
