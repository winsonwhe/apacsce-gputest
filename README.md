# GPUTEST: GPU validation toolkit

[中文文档](README_CN.md) · [Detailed guide](doc/advanced-guide.md)

Validate NVIDIA GPU hosts with preflight, stress, bandwidth, DCGM, RDMA and NCCL checks. Python 3.10+ and PyYAML are required. Mock mode runs without a GPU.

## Project architecture

```text
config.yaml       # SKU profiles, levels, thresholds and tool paths
gputest/          # CLI, runner, checks, parsers and reporting
tests/            # CPU-only pytest coverage
fixtures/         # Mock command output
doc/              # Detailed English and Chinese guides
results/          # Reports and raw command output
```

The CLI loads a level, runs registered checks through the shared command runner, and writes `PASS`, `WARN`, `FAIL` or `SKIP` results with raw output.

## Install

```bash
git clone https://github.com/winsonwhe/apacsce-gputest.git
cd apacsce-gputest
./install.sh
```

Use modules when needed: `./install.sh --python`, `--system-deps`, `--gpu-tools`, or `--ssh`. From a GPU-less jump host, use `./install.sh --control-plane --system-deps --python --ssh --gpu-tools` so GPU tools are built on the remote inventory nodes. Hardware runs also need the NVIDIA driver/CUDA, DCGM, `numactl`, `iproute2`, perftest, MPI/UCX and nccl-tests as applicable. See [installation details](doc/installation.md).

## Quick start

```bash
# List registered checks and supported categories
python3 -m gputest.cli list

# Run fixture-backed validation without GPU hardware
python3 -m gputest.cli run --sku a10 --level basic --mock

# Preview commands without executing workloads or SSH
python3 -m gputest.cli run --sku gb300 --level standard --dry-run

# Run local hardware validation
python3 -m gputest.cli run --sku gb300 --level standard

# Run a two-host validation
python3 -m gputest.cli run --sku gb300 --level extended --nodes host1,host2
```

Use `--tests check1,check2` to select checks explicitly. Use `--network-mode single_plane|multiplanar` when automatic IMDS detection is unavailable. Reports and raw command output are written under `results/`. See [running tests](doc/running-tests.md).


## Levels

| Level | Purpose |
|---|---|
| `basic` | Host-local health checks and a short GPU burn; no RDMA or multi-host requirement. |
| `standard` | Basic plus bandwidth, BabelStream, DCGM and RDMA checks on profiles that support RDMA. |
| `extended` | Standard plus local NCCL, placement/IMEX where supported, and multi-host NCCL. |

A10 uses dedicated profiles: `a10_basic`, `a10_standard`, and `a10_extended`. They omit RDMA and multi-host NCCL because the supported A10 deployment has no RDMA fabric. Storage and object-store checks are opt-in because they require site-specific paths or credentials. See [level details](doc/levels.md).


## Test catalog

| Area | Checks |
|---|---|
| Preflight | `network_mode`, `nvidia_smi`, `ssh_connectivity`, `fabricmanager`, `numa_topology`, `rdma_iface`, `rdma_link`, `gpu_topology`, `numa_affinity`, `kernel_xid`, `ecc_remap`, `pcie_link`, `nvlink`, `clocks_throttle`, `software_versions`, `oca_version`, `placement`, `imex` |
| Burn | `gpu_burn`, `gpu_fryer` |
| Bandwidth | `nvbandwidth`, `babelstream` |
| RDMA | `gpudirect_rdma`, `rdma_perf`, `rdma_bw`, `rdma_lat`, `rdma_read`, `rdma_send`, `gdr_perf` |
| NCCL | `nccl_local_allreduce`, `nccl_local_alltoall`, `nccl_allreduce`, `nccl_alltoall` |
| Diagnostics | `dcgmi`, `storage`, `nic_inventory`, `network_ping`, `tcp_bandwidth`, `lustre_client`, `filesystem_perf`, `object_storage`, `object_upload` |

Use `python3 -m gputest.cli list` for the registry and [the full catalog](doc/test-catalog.md) for commands and prerequisites.

