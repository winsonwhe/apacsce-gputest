# gputest control center

Start the controller from the repository root:

```bash
python3 -m gputest.api_server --port 8080
```

The service listens only on `127.0.0.1` by default. For a direct bastion preview on its public address, bind all interfaces explicitly:

```bash
python3 -m gputest.api_server --host 0.0.0.0 --port 8080
```

Then open `http://<bastion-public-ip>:8080` after allowing TCP/8080 in the cloud security list and the host firewall. This is plain HTTP and has no account system, so restrict the source IPs to your office/VPN whenever possible. For production, put it behind HTTPS and an IP allowlist or VPN. The controller provides powerful SSH execution and private-key upload; it must not be exposed to the whole Internet.

Use **GPU nodes** to save SSH targets and optionally upload a dedicated unencrypted private key. The key is saved in `results/controller/controller_key` with mode `0600`; back up and protect the controller state directory accordingly. Alternatively use the controller process's SSH agent. The controller must already trust each node's host key; establish trust out of band. Each run uses a private SSH configuration and the saved port, user and identity for controller-to-node connections. Multi-node checks may additionally require peer-to-peer SSH configured on the GPU hosts; the UI does not set it up.

Use **New test run** to select the SKU, configured level, individual checks, targets and execution mode. Start with a dry run, or use fixture-backed mock mode. Jobs, logs, configuration snapshots and reports are retained under `results/controller/`; pass `--state-dir` to change that location. A browser can reopen an existing run while the controller is running. If the controller exits during a run, the job is reported as interrupted after restart; the child process may continue and must be checked separately.

Hardware discovery, connection testing, remote installation/update, run cancellation and a live Markdown renderer are not yet implemented. Reports are available as plain Markdown and raw command output. The current `install.sh` is interactive and manages SSH and multiple nodes itself; it must be adapted before it can safely run as a web job.
