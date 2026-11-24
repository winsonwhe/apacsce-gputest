# Running tests

List checks:

```bash
python3 -m gputest.cli list
```

Run a profile, preview commands, or use fixtures:

```bash
python3 -m gputest.cli run --sku gb300 --level basic
python3 -m gputest.cli run --sku gb300 --level standard --dry-run
python3 -m gputest.cli run --sku a10 --level basic --mock
```

Select checks explicitly with `--tests name1,name2`. Supply `--nodes host1,host2` for multi-host checks, `--user USER` or `user@host` for SSH identity, and `--hostfile FILE` for a host list. Use `--gpu-count` for a partial GPU host. `--network-mode` overrides automatic IMDS detection.

Each run writes JSON/Markdown summaries and raw command output below `results/`. Use `report` to render an existing result directory. See `doc/advanced-guide.md` for baselines, NCCL launcher options and troubleshooting.
