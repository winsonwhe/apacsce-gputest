# gputest: GPU validation toolkit

[中文版](README_CN.md)

Validate OCI NVIDIA A10, A100, H100, H200, L40S, B200, GB200, B300 and GB300
hosts with preflight checks, sustained GPU load, memory bandwidth, DCGM, two-host
RDMA and multi-host NCCL. Python 3.10+,
standard library plus PyYAML; no plugin framework or GPU dependency for mock runs.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
# oracle linux
sudo dnf install -y python3-pip

# ubuntu
sudo apt install -y python3-pip

python3 -m pip install -r requirements.txt
python3 -m pip install pytest ruff
python3 -m pytest -q
python3 -m ruff check .
```

On GPU hosts, provision the NVIDIA driver/CUDA, Fabric Manager where applicable,
DCGM, numactl, iproute2 (`ip`, `rdma`, `ss`), perftest, GNU `timeout`, and MPI/UCX
with SSH support. Build nccl-tests (`all_reduce_perf` and `alltoall_perf`) and configure
executable paths under `tools` in `config.yaml`. Required versions depend on the
SKU/deployment; configured minima and performance floors need hardware validation.

### Dependency tools

The project uses a small set of Python and system tools. The links below point to
their documentation or upstream projects:

| Tool | Purpose | Documentation |
|---|---|---|
| [Python](https://docs.python.org/3/) | Runs the CLI and validation checks; Python 3.10 or newer is required. | [Python documentation](https://docs.python.org/3/) |
| [PyYAML](https://pyyaml.org/wiki/PyYAMLDocumentation) | Loads thresholds, profiles, tool paths and NCCL settings from `config.yaml`. | [PyYAML documentation](https://pyyaml.org/wiki/PyYAMLDocumentation) |
| [pytest](https://docs.pytest.org/) | Runs the unit and orchestration tests, including CPU-only fixture tests. | [pytest documentation](https://docs.pytest.org/) |
| [Ruff](https://docs.astral.sh/ruff/) | Checks Python code for lint errors and common style or correctness issues. | [Ruff documentation](https://docs.astral.sh/ruff/) |
| [NVIDIA Driver](https://docs.nvidia.com/datacenter/tesla/), [CUDA Toolkit](https://docs.nvidia.com/cuda/) | Provides GPU access and CUDA tooling for hardware validation and CUDA-based workloads. | [NVIDIA documentation](https://docs.nvidia.com/) |
| [NVIDIA Fabric Manager](https://docs.nvidia.com/datacenter/tesla/fabric-manager-user-guide/) | Manages the GPU fabric on supported GB300/B300 systems. | [Fabric Manager guide](https://docs.nvidia.com/datacenter/tesla/fabric-manager-user-guide/) |
| [DCGM](https://docs.nvidia.com/datacenter/dcgm/latest/) | Runs NVIDIA GPU diagnostics and health checks. | [DCGM documentation](https://docs.nvidia.com/datacenter/dcgm/latest/) |
| [numactl](https://github.com/numactl/numactl) | Selects NUMA nodes and reports CPU/memory topology for locality checks. | [numactl project](https://github.com/numactl/numactl) |
| [iproute2](https://www.kernel.org/pub/linux/utils/net/iproute2/) | Provides `ip`, `rdma` and `ss` for interface, VRF and RDMA checks. | [iproute2 releases](https://www.kernel.org/pub/linux/utils/net/iproute2/) |
| [perftest](https://github.com/linux-rdma/perftest) | Provides `ib_write_bw`, `ib_read_bw`, `ib_send_bw` and `ib_write_lat` for RDMA checks. | [perftest project](https://github.com/linux-rdma/perftest) |
| [Open MPI](https://www.open-mpi.org/), [UCX](https://openucx.readthedocs.io/) | Launches and transports multi-host NCCL jobs. | [Open MPI](https://www.open-mpi.org/), [UCX documentation](https://openucx.readthedocs.io/) |
| [nccl-tests](https://github.com/NVIDIA/nccl-tests) | Provides `all_reduce_perf` and `alltoall_perf` for NCCL validation. | [nccl-tests project](https://github.com/NVIDIA/nccl-tests) |
| [GNU coreutils `timeout`](https://www.gnu.org/software/coreutils/manual/html_node/timeout-invocation.html) | Bounds every external command so failed or hung workloads finish predictably. | [timeout manual](https://www.gnu.org/software/coreutils/manual/html_node/timeout-invocation.html) |

The mock profile only needs Python, PyYAML and the project test tools. GPU-host
dependencies are required when running hardware checks for real. `git`, `make`,
CMake and `nvcc` are also needed when configured benchmark sources must be built.

Local gpu-burn, nvbandwidth and BabelStream can clone/build missing sources when
`build_if_missing: true`. Git, make/CMake and nvcc must already exist; system
packages are never installed. For SSH targets, provision binaries beforehand at
identical absolute paths on every host. gpu-burn needs `compare.ptx` beside its
binary. B300/GB300 compute capability is 10.3 (`COMPUTE=103`, `sm_103`), per
[NVIDIA's GPU table](https://developer.nvidia.com/cuda-gpus).

## Quick start

Run from the repository root:

```bash
python3 -m gputest.cli list
# No GPU required; fixtures complete immediately:
python3 -m gputest.cli run --sku gb300 --profile quick --mock
# Inspect all commands without SSH, builds or workloads:
python3 -m gputest.cli run --sku gb300 --profile standard --nodes n1,n2 \
  --network-mode multiplanar --dry-run
# Real local validation, with preinstalled tools:
python3 -m gputest.cli run --sku gb300 --profile quick
# Real two-host standard validation:
python3 -m gputest.cli run --sku gb300 --profile standard --nodes n1,n2
```

`--nodes` lists SSH hosts. Per-host preflights, burn, nvbandwidth, BabelStream and
DCGM run on all supplied hosts in bounded parallel workers. RDMA uses the first
two hosts; NCCL selects from the supplied candidates. Without `--nodes`, per-host
checks run locally and multi-host checks SKIP. `--tests CHECK,CHECK` overrides the
profile's check list; its burn duration and DCGM level still follow `--profile`.
`--gpu-count` overrides the configured GPU count. Use exclusive/idle GPU hosts.

Provision trusted SSH keys/known_hosts between the controller, launcher and
peers. `setup-ssh --nodes n1,n2 --dry-run` previews optional key provisioning;
it does not establish a full peer mesh. Verify site SSH policy and keys using
`--tests ssh_connectivity`. Every external command uses the same helper, with a
timeout, raw log and mock/dry-run support. Remote commands receive a second GNU
timeout on the target, so SSH disconnection leaves a bounded workload.

## Test catalog

All means the configured SKUs: A10, A100, H100, H200, L40S, B200, GB200,
B300 and GB300. The commands below show the main underlying commands; paths,
arguments and thresholds come from `config.yaml`, and discovery or telemetry can
run additional commands. A configured SKU is not a guarantee that its tools,
hardware capabilities or calibrated thresholds are available.

Run an individual check with `python3 -m gputest.cli run --sku <sku> --tests
<check>`; add `--nodes n1,n2` for checks marked multi-host and `--dry-run` to
preview commands. Use `python3 -m gputest.cli list` for the current registry.

The tables group checks by purpose and roughly progress from inventory and
health checks to performance and multi-host workloads within each group. This
is a reading guide; profiles and explicit `--tests` order determine execution.
The Category column retains the CLI registry category.

### System Validation

| Category | Check | Test content | Main command(s) | Target SKUs / conditions |
|---|---|---|---|---|
| preflight | `software_versions` | Driver, firmware and installed software versions | `nvidia-smi --query-gpu=driver_version,vbios_version --format=csv,noheader`; `nvcc --version`; `ofed_info -s`; `dcgmi --version`; `ibv_devinfo --version`; `nvidia-fabricmanager --version` | All |
| preflight | `oca_version` | Oracle Cloud Agent package version on each host; optional minimum version | `cat /etc/os-release`; `rpm -q`, `dpkg-query`, and `snap list` for `oracle-cloud-agent` | All; Linux package installations; missing or uncomparable versions WARN |
| preflight | `numa_topology` | CPU and memory NUMA topology | `numactl --hardware` | All |
| preflight | `ssh_connectivity` | SSH access and launcher-to-peer connectivity | `hostname` over SSH; `ssh -o BatchMode=yes -o ConnectTimeout=10 -- <peer> hostname` from launcher | All; multi-host |

### GPU Validation

| Category | Check | Test content | Main command(s) | Target SKUs / conditions |
|---|---|---|---|---|
| preflight | `nvidia_smi` | GPU inventory, driver, memory and ECC mode | `nvidia-smi --query-gpu=index,name,driver_version,memory.total,ecc.mode.current --format=csv,noheader,nounits`; `nvidia-smi --query-gpu=compute_cap --format=csv,noheader` | All |
| preflight | `gpu_topology` | GPU and NIC topology inventory | `nvidia-smi topo -m` | All |
| preflight | `numa_affinity` | GPU CPU/NUMA affinity reported by the driver | `nvidia-smi topo -m` CPU/NUMA affinity columns | All; warns when the driver does not expose affinity |
| preflight | `pcie_link` | GPU PCIe link status and negotiated characteristics | `nvidia-smi -q -d PCI` | All |
| preflight | `nvlink` | GPU NVLink status | `nvidia-smi nvlink -s` | A100, H100, H200, B200, GB200 and GB300 with current `nvlink` flags; others SKIP |
| preflight | `fabricmanager` | Fabric Manager service state | `systemctl is-active nvidia-fabricmanager` | A100, H100, H200, B200, GB200, B300, GB300; others SKIP |
| preflight | `kernel_xid` | NVIDIA Xid events in the current boot log | `journalctl -k --no-pager -b` | All |
| preflight | `ecc_remap` | ECC errors, retired pages and row remapping | `nvidia-smi -q -d ECC,REMAP,RETIRED_PAGES` | All |
| preflight | `clocks_throttle` | GPU hardware slowdown, thermal and power-brake events | `nvidia-smi --query-gpu=index,clocks_event_reasons.active --format=csv,noheader` (legacy query on failure) | All |
| diagnostics | `dcgmi` | DCGM diagnostic suite | `dcgmi diag -r <level> -j` | All |
| bandwidth | `babelstream` | GPU memory bandwidth workloads | `cuda-stream --device <gpu>` | All |
| bandwidth | `nvbandwidth` | Configured GPU memory and interconnect bandwidth workloads | `nvbandwidth -t <configured-test>`; optional `mpirun` for multi-node | All have test names; multi-node is GB300 only and requires at least two hosts. See build caveat below. |
| burn | `gpu_burn` | Sustained GPU compute stress and health monitoring | `gpu_burn -m <percent>% [-tc] [-d] <seconds>` or `gpu-fryer [options] <seconds>` | All |

### Network Validation

| Category | Check | Test content | Main command(s) | Target SKUs / conditions |
|---|---|---|---|---|
| preflight | `network_mode` | Detect or confirm the OCI RDMA network mode | `curl -fsSL --max-time <seconds> -H 'Authorization: Bearer Oracle' <IMDS-host-URL>` | All |
| diagnostics | `nic_inventory` | NIC carrier, negotiated speed and optional expected LLDP peer | `ethtool <interface>`; optional `lldpcli` | All; enable and configure interfaces; LLDP requires a host agent and switch advertisements |
| preflight | `rdma_iface` | Active RDMA devices, netdevs and multiplanar VRF bindings | `rdma link`; `ip -j -d link show` in multiplanar mode | All; requires suitable RDMA devices |
| preflight | `rdma_link` | Active RDMA devices and VRF bindings | Same as `rdma_iface` (compatibility alias) | All; requires suitable RDMA devices |
| diagnostics | `network_ping` | Configured local or cross-host IP paths and packet loss, optionally sampled | `ping` with configured source, family and optional VRF | All; enable and configure paths; ICMP and routing must be allowed |
| rdma | `gpudirect_rdma` | GPUDirect RDMA prerequisites | `lsmod`; `ib_write_bw --help` | All; requires GPUDirect RDMA prerequisites |
| diagnostics | `tcp_bandwidth` | Frontend or backend TCP throughput | `iperf3` client with source binding and optional VRF | All; enable and configure paths and running target servers |
| rdma | `rdma_bw` | Per-rail RDMA write bandwidth | `ib_write_bw [options] -d <device> [server-address]` | All; multi-host, suitable RDMA devices required |
| rdma | `rdma_lat` | Per-rail RDMA write latency | `ib_write_lat [options] -d <device> [server-address]` | All; multi-host, suitable RDMA devices required |
| rdma | `rdma_perf` | Per-rail RDMA write bandwidth and latency | `ib_write_bw [options] -d <device> [server-address]`; `ib_write_lat [options] -d <device> [server-address]` | All; multi-host, suitable RDMA devices required |
| rdma | `rdma_read` | Per-rail RDMA read bandwidth | `ib_read_bw [options] -d <device> [server-address]` | All; multi-host, suitable RDMA devices required |
| rdma | `rdma_send` | Per-rail RDMA send bandwidth | `ib_send_bw [options] -d <device> [server-address]` | All; multi-host, suitable RDMA devices required |
| rdma | `gdr_perf` | Per-rail RDMA write bandwidth using GPU memory | `ib_write_bw [options] --use_cuda -d <device> [server-address]` | All; multi-host, CUDA-enabled perftest and GPUDirect RDMA required |

### Storage Validation

| Category | Check | Test content | Main command(s) | Target SKUs / conditions |
|---|---|---|---|---|
| diagnostics | `storage` | Filesystem capacity and striping; optional read-only I/O | `df -hT <path>`; `xfs_info <path>`; `lfs df -h <path>`; `lfs getstripe <path>`; optional read-only `fio` | All; disabled until configured |
| diagnostics | `lustre_client` | Lustre mount, capacity and stripe configuration | `findmnt`; `lfs df`; `lfs getstripe` | All; enable and configure a mounted Lustre path |
| diagnostics | `filesystem_perf` | Local NVMe, shared filesystem or Lustre read/write throughput and IOPS | `fio` on configured files or dedicated test directories | All; enable and configure jobs, paths and workload; write jobs need free space |
| diagnostics | `object_storage` | OCI Object Storage download throughput | `oci os object get`; `wc`; temporary-file cleanup | All; enable and configure bucket, existing object, scratch directory and read access |
| diagnostics | `object_upload` | OCI Object Storage upload throughput and temporary object cleanup | `oci os object put`; `oci os object delete` | All; enable and configure source file, bucket, dedicated prefix, create/delete access and supported OCI CLI |

### Distributed GPU Validation

| Category | Check | Test content | Main command(s) | Target SKUs / conditions |
|---|---|---|---|---|
| nccl | `nccl_local_alltoall` | Single-host NCCL all-to-all bandwidth | `alltoall_perf -b 8 -e 8G -f 2 -g <gpu-count>` | All; local host |
| nccl | `nccl_local_allreduce` | Single-host NCCL all-reduce bandwidth | `all_reduce_perf -b 8 -e 8G -f 2 -g <gpu-count>` | All; local host |
| preflight | `placement` | GPU memory fabric and deployment-group placement | IMDS `curl` as in `network_mode`; select hosts from returned or configured inventory | All; multi-host |
| preflight | `imex` | IMEX service and configured multi-host membership | `cat /etc/nvidia-imex/nodes_config.cfg`; `systemctl is-active nvidia-imex`; IMDS `curl` | GB200, GB300; multi-host |
| nccl | `nccl_allreduce` | Multi-host NCCL all-reduce bandwidth | `mpirun [host, rank and environment options] all_reduce_perf -b 1G -e 16G -f 2 -g 1 -n 50` | All; multi-host |
| nccl | `nccl_alltoall` | Multi-host NCCL all-to-all bandwidth | `mpirun [host, rank and environment options] alltoall_perf -b 1G -e 16G -f 2 -g 1 -n 50` | All; multi-host |

`nvbandwidth.cuda_arch` currently lists only A10, B300 and GB300; the other
SKUs need an architecture entry in `config.yaml` before this check can run,
even with a preinstalled binary. GB300 has `nvlink: true` configured and is
checked with `nvidia-smi nvlink -s`; B300 remains skipped until its deployment
specific NVLink behavior is verified.
For multiplanar RDMA, the perftest commands are prefixed with configured
`ip vrf exec <vrf> numactl -N <node>` and use the configured IPv6/GID options.

`oca_version` checks Oracle Cloud Agent on each selected host. It reads that
host's `/etc/os-release`, prefers `dpkg-query` and snap on Debian/Ubuntu and
`rpm` on Oracle Linux/RHEL-family systems, and also probes the other package
managers to cover alternative installations. It records all detected package
versions and the raw output. It is enabled in all profiles; set
`oca_version.enabled: false` to disable it. Configure a quoted numeric
`oca_version.min_version` only when the deployment has an approved minimum.
Without one, or if no package is detected, the check reports WARN. Comparison
uses the numeric version core and accepts an optional numeric package release;
epochs, prereleases and other suffixes are reported as uncomparable (WARN), not
assumed compliant. This checks package versions, not agent service or plugin
health. TODO(verify): confirm package names and query output on the OCI images in
use; custom or non-package installations may need additional detection.

## Profiles

| Profile | Burn per host | Checks | Expected time |
|---|---:|---|---|
| `quick` | 120 s | Network mode, GPUs, GPU/NIC topology, Fabric Manager, NUMA, RDMA devices/VRFs, short burn | About 5 min with installed tools |
| `standard` | 1,200 s | Quick preflights, SSH, burn, nvbandwidth, BabelStream, DCGM r2, RDMA bandwidth and latency | 20 min burn plus diagnostics/bandwidth overhead |
| `full` | 3,600 s | Standard checks, GMF placement, IMEX, DCGM r3, multi-host all-reduce and all-to-all | 1 h+ |

Per-SKU profiles such as `a100_standard` and `h100_full` are aliases of the base
profiles. Fabric Manager, NVLink and IMEX are selected from each SKU's capability
flags; unsupported checks SKIP. Change `profile_settings.<profile>.burn_duration_s` for a
10–30 minute standard burn or a longer full burn. Set
`dcgmi.profile_levels.full: 4` for r4 (also change `a10_full` if using that alias).
Builds, timeout failures, many GPUs and diagnostic levels can extend these budgets.
Quick omits DCGM by default; selecting it explicitly uses r1.

## Network, placement and checks

The OCI shape name never selects the network mode. In auto mode, target IMDS
`rdmaFabricData.planes` determines it: 4 means multiplanar; absent/1 means
single-plane. Unreachable IMDS uses `network.fallback_mode` and reports WARN.
`--network-mode` or `network.mode` overrides detection, while the `network_mode`
preflight checks reachable IMDS for conflicts. A failed mode preflight blocks
workloads. Dry-run prints discovery placeholders and uses the explicit mode or
fallback; pass `--network-mode` to preview the desired commands.

- `rdma_iface` (`rdma_link` compatibility alias): discover ACTIVE + LINK_UP
  devices/netdevs. Single-plane counts and optional pins are configured per SKU;
  no fixed interface, VRF or IPv6 assumption is made. Multiplanar validates the
  four VF devices, `vrf_r0..3` and each netdev's VRF master. Unused DOWN links are
  ignored. `gpu_topology` checks GPU/NIC presence in `nvidia-smi topo -m`.
- `gpu_burn`: verify error counters, GPU count and per-GPU throughput deviation;
  sample temperature/power throughout the workload. Unavailable telemetry is
  WARN. `gpu-fryer` is optional and **does not check numerical correctness**.
  Sampling can miss transients; absolute thermal/power limits are not enforced.
- `nvbandwidth`: compare each configured aggregate SUM in GB/s with its floor.
  Optional GB300 multi-node mode requires a MULTINODE build, one GMF and IMEX;
  see [NVIDIA's instructions](https://github.com/NVIDIA/nvbandwidth#multi-node-support).
- `babelstream`: run each GPU, normalize MB/s to GB/s, compare every
  Copy/Mul/Add/Triad/Dot measurement and report means/spread.
- `dcgmi`: request JSON for the profile's diagnostic level; preserve individual
  test/entity outcomes and warnings, even after a failed command.
- `rdma_perf`: run `ib_write_bw` and `ib_write_lat` per rail/device. `rdma_bw` and
  `rdma_lat` select one workload. `rdma_read` and `rdma_send` run the corresponding
  perftest bandwidth workloads. `gdr_perf` repeats write bandwidth with
  `--use_cuda`, so the transfer buffer is GPU memory. Read server/client netdev
  addresses automatically;
  probe server readiness before starting the client. Multiplanar uses configured
  `ip vrf exec`, NUMA, IPv6 and GID flags. Single-plane prefers IPv4 and enables
  IPv6 only when discovered/pinned with `rdma_perf.single_plane.ip_family`.
  Report each rail and `(max - min) / mean` spread.
- `numa_affinity`: validate that `nvidia-smi topo -m` reports CPU and NUMA affinity
  for every GPU. This checks driver topology reporting; RDMA commands additionally
  apply the configured per-rail NUMA binding in multiplanar mode.
- `nccl_allreduce` / `nccl_alltoall`: one rank per GPU with
  `-b 1G -e 16G -f 2 -g 1 -n 50`. All environment and launcher settings are in
  mode-specific config blocks. Multiplanar tuning switches above 32 hosts;
  single-plane HCA names are discovered and must match across selected hosts.
  Both in-place and out-of-place busbw at the requested largest size must meet
  the floor. Command errors, missing output and validation errors fail.
- `nccl_local_allreduce` / `nccl_local_alltoall`: run single-host collectives
  separately from the multi-host network test. Their independent thresholds are
  intentionally unset until per-SKU, per-GPU-count baselines are collected.
- `storage`: optionally collect `df`, XFS/Lustre capacity and striping, and run
  a read-only `fio` check against an existing file. It is disabled unless a
  dedicated `storage.path` is configured, so GPU acceptance remains non-invasive.

### Optional network and storage acceptance checks

The `full` profile includes the following checks, each disabled until its own
configuration is enabled and its required paths or interfaces are supplied. They
can also be selected with `--tests`. Configure tool paths under `tools` in
`config.yaml`; `ethtool`, `lldpcli`, Linux `ping`, `iperf3`, `findmnt`, `lfs`,
`fio`, and the OCI CLI are needed only for the checks that use them. Run with
`--dry-run` to preview commands on all selected hosts before running workloads.
All performance thresholds are deployment-specific; an absent threshold reports
WARN rather than claiming that a measured rate meets an acceptance target.

- `nic_inventory`: check carrier and negotiated speed with `ethtool` for each
  configured front-end or back-end netdev. Optionally compare LLDP chassis and
  port identifiers with the configured expected peer. LLDP requires advertisements
  from the switch and a running host LLDP agent; a missing peer is WARN. Configure
  interfaces visible to `ethtool` on every selected host. Virtual functions may
  not expose physical link speed. Matching LLDP and connectivity can detect some
  wiring mistakes but cannot prove all cabling is correct. Verify the deployed
  `lldpcli` keyvalue fields and the expected switch-port inventory.
- `network_ping`: test explicitly configured source/target paths with IPv4 or
  IPv6 and an optional source VRF. Set each path's `node` to a name in `--nodes`,
  or omit it for local execution. List only paths that are intended to communicate
  in the selected single-plane or multiplanar deployment. `sample_count: 0`
  checks all paths; a positive count reproducibly samples per source host using
  `seed`. Packet loss above `max_loss_pct` fails. ICMP, routing, addresses and
  VRF access must be permitted. Same-host ping may be delivered locally without
  traversing the NIC or switch; it is not proof of physical connectivity.
- `tcp_bandwidth`: measure TCP throughput with `iperf3` from configured source
  addresses, optionally inside a VRF. Start an `iperf3` server separately at each
  target, allow its configured port, and ensure sufficient CPU and bandwidth.
  `reverse: true` measures the reverse direction. Paths use the same `node`
  convention as ping. This tests TCP/IP; it does not prove RDMA operation or
  implement a TCP-over-RDMA protocol. Existing `rdma_perf` and related checks
  separately exercise RDMA verbs, using the first two selected hosts.
- `lustre_client`: verify that the configured path is on a Lustre filesystem and
  run `lfs df` and `lfs getstripe`. Install the client and mount the filesystem on
  each selected host. Use `filesystem_perf` for actual Lustre I/O measurements.
- `filesystem_perf`: run configured `fio` sequential or random read/write jobs
  against local NVMe, shared filesystems, or Lustre. Verify the target mount and
  backing device independently. Reads require an existing test file and use
  read-only mode. Writes create uniquely named files in a dedicated directory and
  request fio to unlink them; allow enough space and check for leftovers after a
  timeout, interruption or fio failure. Each selected host runs its configured jobs
  in parallel; results are per host, not a synchronized aggregate benchmark.
  Specify workload, block size, queue depth, file size and thresholds that match
  the acceptance plan; account for caching, stripe layout and shared load.
- `object_storage` downloads an existing object to a unique file in the configured
  scratch directory, measures end-to-end throughput including CLI startup, and
  removes the file. `object_upload` uploads an existing source file to a unique
  name under a dedicated prefix using a conditional create, measures throughput,
  and deletes that new object. Configure OCI CLI authentication, region/profile
  options and bucket permissions for every selected host. Upload requires create
  and delete permissions; download requires read permission and scratch space.
  Requests and storage may incur charges. A timeout, interruption or failed cleanup
  can leave a temporary file or object; inspect the recorded path/name and clean it
  up. TODO(verify): validate conditional upload options and multipart behavior with
  the deployed OCI CLI. These checks do not benchmark metadata request rates.

For example, after populating the corresponding sections in `config.yaml`:

```bash
python3 -m gputest.cli run --sku gb300 --nodes n1,n2 \
  --tests nic_inventory,network_ping,tcp_bandwidth,lustre_client,filesystem_perf,object_storage,object_upload --dry-run
```

These data-plane probes do not audit all VCN route tables, security lists, network
security groups or physical switch ports. Front-end RDMA over CFAB and a specific
TCP-over-RDMA protocol remain unimplemented until the deployment's meaning,
supported hardware and software stack are confirmed. Negotiated line speed is not
the same as measured application throughput; configure 200/400 Gb/s targets only
after establishing a suitable known-good baseline.

NCCL/placement group nodes by `customerGpuMemoryFabric` (GMF). Jobs of up to
18 hosts must fit one GMF; larger jobs prefer matching `customerLocalBlock`.
Different or unknown blocks across racks produce WARN. `--node-count N` selects
N candidates for NCCL; per-host checks still cover all `--nodes`. Non-OCI
inventory or additional rack members can be configured explicitly:

```yaml
placement:
  rack_max_nodes: 18
  inventory:
    n1: {gmf: rack1, local_block: block1}
    n2: {gmf: rack1, local_block: block1}
```

IMEX is GB300-only, checked before NCCL with MNNVL enabled. Existing node files
must contain the selected same-GMF peers and no cross-rack members; additional
members need inventory entries. Use exact hostnames/IPs from the IMEX files.
The service must be active. gputest validates membership and state; it does not
install, restart or configure IMEX, or prove transport health. IMEX domains are
per GMF, never one domain spanning multiple racks.

## Reports and thresholds

Each run writes `results.json`, `results.md` and complete raw command logs under
`results/run-<timestamp>/` (override with `--output-dir`). Markdown contains an
overview table, per-check measurements, threshold rules/values/sources, raw
excerpts and troubleshooting hints for every WARN/FAIL. JSON exposes the same
`metrics`, `thresholds` and `hints` fields. The terminal shows a short summary;
exit status is 1 when any check fails, 0 otherwise (WARN/SKIP remain visible).
Re-render saved Markdown and print the summary with:

```bash
python3 -m gputest.cli report results/run-YYYYMMDD-HHMMSS
```

Threshold sources are explicit: **config default**, **PDF example**, or
**baseline**, with their config path or baseline file/key. Edited config values
retain the “config default” label to distinguish them from example/baseline
references; the report records the config file used. When replacing a PDF-derived
limit manually, also set its `threshold_source: config default`. Intrinsic command/parser
errors and reported numerical failures do not require performance thresholds.

The supplied multiplanar RDMA examples (~459 Gb/s, 3.8–4.0 us) use wide limits
(321.3 Gb/s minimum, 6 us maximum). They are **example data, not guarantees**.
Single-plane RDMA and NCCL limits default to unset (WARN until calibrated).
Optional `nccl.<mode>.example_reference_gbs.<collective>` accepts exact scale keys
such as 2/16/32/64/80, using 80% by default. Tables remain empty because verified
PDF scale measurements are unavailable. Existing nvbandwidth/BabelStream config
floors also require calibration. Troubleshooting guidance lives in config.yaml;
it follows supplied manual excerpts and the
[OCI README](https://github.com/oracle-quickstart/oci-gpu-quickstarts/blob/main/nvidia/GB300/README-GB300.md).

## Known-good baselines

```bash
python3 -m gputest.cli run --sku gb300 --profile standard --nodes n1,n2 \
  --baseline save --baseline-file baselines/site.json
python3 -m gputest.cli run --sku gb300 --profile standard --nodes n1,n2 \
  --baseline compare --baseline-file baselines/site.json
```

A save commits one snapshot only after the selected checks complete without
failures, missing tools or operational warnings. The exception is a benchmark
WARN caused solely by unset thresholds, which allows initial calibration. No
existing snapshot is overwritten by a failed run or dry-run. Confirm the hardware
and load are known-good before saving; software cannot certify that independently.

Comparison covers per-GPU burn throughput, every nvbandwidth SUM, every GPU's
BabelStream measurements, every RDMA rail's bandwidth/latency, and both NCCL
largest-size placements. It retains configured limits and adds baseline limits;
regressions fail. Health/status regressions and missing/incompatible observations
also fail. Tolerances are in `baseline`: 20% generally, 10% for burn and 20% for
NCCL (80% of recorded bandwidth). Latency may increase by the configured tolerance.

Records distinguish SKU, mode, GPU count, scale, profile, workload options and
mock vs real execution. Changed duration, precision, message sizes or tuning
requires a new baseline. Checks are keyed independently, so saving another
profile/check adds records at its scope. The same check/scale record is replaced
by a later successful save. Host positions pair equivalent hosts across runs;
rail/device and GPU metric names must match. Versioned baseline files from older
gputest revisions must be regenerated. Mock baselines are only orchestration tests.

## Run multi-host NCCL with mpirun

NCCL uses `mpirun` on the first selected host. Set `tools.mpirun` to the
Open MPI/HPC-X executable; mode-specific MPI options are in
`nccl.<mode>.mpi_args`. All selected hosts need matching nccl-tests binaries,
CUDA/NCCL/MPI libraries and trusted passwordless SSH from the controller and
launch host. Use absolute paths shared across hosts.

```bash
# Preview both collectives and every remote command:
python3 -m gputest.cli run --sku gb300 --nodes n1,n2 \
  --network-mode multiplanar --tests nccl_allreduce,nccl_alltoall --dry-run
# Run both collectives directly through mpirun:
python3 -m gputest.cli run --sku gb300 --nodes n1,n2 \
  --network-mode multiplanar --tests nccl_allreduce,nccl_alltoall
```

The generated MPI command specifies the selected hosts and slots, total rank
count, one rank per GPU, and configured environment variables using `-x`.
GMF/local-block selection and per-GMF IMEX validation run before the collective.
Provision exclusive/idle hosts through your normal cluster process before testing.

## Add a check

Add a pure parser in `gputest/parsers.py`, one decorated function in
`gputest/checks.py`, a fixture, a unit test and an optional profile entry. Use
`ctx.run` for every external command; configurable expectations belong in YAML.
Here is a complete persistence-mode check example:

```python
# gputest/parsers.py
def parse_persistence(text: str) -> dict:
    return {'modes': [line.strip() for line in text.splitlines() if line.strip()]}

# gputest/checks.py (uses existing Result, RunContext, check and parsers imports)
@check('persistence', category='preflight')
def persistence(ctx: RunContext) -> Result:
    cfg = ctx.config['persistence']
    rr = ctx.run([ctx.config['tools']['nvidia_smi'],
                  '--query-gpu=persistence_mode', '--format=csv,noheader'],
                 timeout=cfg['timeout_s'], mock_fixture='persistence.txt')
    if rr.skipped:
        return Result('persistence', 'SKIP', 'dry-run')
    parsed = parsers.parse_persistence(rr.stdout)
    modes = parsed['modes']
    ok = (rr.returncode == 0 and len(modes) == ctx.sku_config()['gpu_count']
          and all(mode == cfg['expected'] for mode in modes))
    result = Result('persistence', 'PASS' if ok else 'FAIL',
                    'persistence modes checked', parsed, _raw=rr.stdout + rr.stderr)
    result.thresholds = [{'metric': 'persistence_mode', 'rule': '==',
                          'value': cfg['expected'], 'source': 'config default',
                          'reference': 'persistence.expected'}]
    return result
```

```yaml
# config.yaml (also add persistence to a profile if desired)
persistence: {expected: Enabled, timeout_s: 10}
# Add under the existing troubleshooting dictionary:
# persistence: ['Check persistence mode with nvidia-smi; apply site policy before retesting.']
```

```text
# fixtures/persistence.txt: file contains only these four lines, no header
Enabled
Enabled
Enabled
Enabled
```

```python
# tests/test_persistence.py
from pathlib import Path
from gputest import parsers
from gputest.core import RunContext, load_config, run_checks
import gputest.checks  # registers checks

ROOT = Path(__file__).resolve().parents[1]

def test_persistence_parser_and_check(tmp_path):
    text = (ROOT / 'fixtures/persistence.txt').read_text()
    assert parsers.parse_persistence(text)['modes'] == ['Enabled'] * 4
    assert parsers.parse_persistence('')['modes'] == []
    config = load_config(ROOT / 'config.yaml')
    ctx = RunContext(config, 'gb300', [], mock=True, results_dir=tmp_path)
    assert run_checks(['persistence'], ctx)[0].status == 'PASS'
```

Run with `python3 -m gputest.cli run --sku gb300 --tests persistence --mock`.
Replace illustrative fixtures with real output and record provenance before
relying on hardware-specific parsing.

## Hardware validation still required

See [docs/hardware-validation.md](docs/hardware-validation.md) for the complete
check-by-check list. No GPU hardware or SSH/MPI cluster was used
for CPU-only verification. The reference PDFs are absent from this checkout;
PDF-derived NUMA mapping, options and performance examples retain `TODO(verify)`.
Fixture provenance is recorded in [fixtures/README.md](fixtures/README.md).
