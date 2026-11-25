# Hardware validation still required

[中文版](hardware-validation_CN.md)

CPU-only fixtures verify parsing, command planning and result handling. They do
not prove that a deployed GPU host, network fabric or storage service is healthy.
Run the checks on every supported SKU and network mode before treating a profile
as production-ready. Each check keeps its command output in the run directory;
use that output when recording the hardware baseline.

## Check-by-check validation

| Area | Check | What must be confirmed on hardware |
|---|---|---|
| Network and placement | `network_mode` | IMDS access and schema; `rdmaFabricData.planes` values; automatic detection versus `network.mode` override; non-OCI fallback; rejection of mixed modes. |
| GPU inventory | `nvidia_smi` | GPU count, model, memory, driver minimum, ECC field availability and any SKU-specific partial-host policy. Confirm configured B300/GB300 distinctions and CUDA minimums. |
| GPU health | `kernel_xid`, `ecc_remap`, `pcie_link`, `nvlink`, `clocks_throttle` | Driver output formats, Xid and ECC/row-remapper interpretation, PCIe generation/width and AER counters, NVLink state/error counters, and clock-event masks. Clock checks are snapshots and cannot prove that no transient event occurred. |
| Topology and affinity | `gpu_topology`, `numa_topology`, `numa_affinity` | GPU/NIC enumeration, topology headers, CPU and NUMA affinity columns, real CPU+memory NUMA nodes, zero-MB nodes, and the expected x86 or Grace layout. Presence does not prove bandwidth or affinity quality. |
| Software and services | `software_versions`, `oca_version`, `fabricmanager` | Driver, CUDA, VBIOS, OFED/NIC, DCGM, OCA and (where applicable) Fabric Manager versions; package-manager output; service name, permissions and failure behavior. Validate configured minimums against the deployed image. |
| RDMA discovery | `rdma_iface`, `rdma_link` | ACTIVE + LINK_UP HCA count and names, HCA-to-netdev mapping, and frontend-HCA filtering. In multiplanar mode confirm four `rdma_vf_rail*` devices, `vrf_r*` devices and VF-to-VRF masters. Unused DOWN/DISABLED entries are normal. |
| RDMA prerequisites | `gpudirect_rdma` | `nvidia_peermem` is loaded and the installed perftest binary exposes CUDA mode. |
| RDMA performance | `rdma_perf`, `rdma_bw`, `rdma_lat`, `rdma_read`, `rdma_send`, `gdr_perf` | Server readiness, control ports, matched rail ordering, routable addresses and IP family, MTU/GID settings, NUMA binding, CUDA-buffer support and real average bandwidth/latency columns. Multiplanar VRF/IPv6 commands and the rail-to-NUMA map remain `TODO(verify)` until the reference manual is available. Single-plane names and thresholds are deployment-specific. Calibrate all configured floors instead of treating example values as guarantees. |
| Stress and bandwidth | `gpu_burn`, `gpu_fryer`, `nvbandwidth`, `babelstream` | CUDA architecture and build flags, runtime duration, numerical errors, thermal/cooling/power behavior, telemetry, GPU balance, native output units and test names, P2P/NVLink availability, device selection and SKU-specific floors. Fryer is a load tool and cannot certify numerical correctness. |
| DCGM | `dcgmi` | Installed JSON/schema and supported diagnostic levels, runtime permissions, entity-level findings, idle-GPU requirements and the actual coverage of r1/r2/r3/r4. |
| SSH and execution | `ssh_connectivity` | Controller-to-host and launcher-to-peer keys, host-key policy, timeouts, remote permissions, cancellation and cleanup. A passing probe does not provision a full mesh. |
| Placement and IMEX | `placement`, `imex` | IMDS GMF/local-block values, one-GMF selection, cross-rack preference, expected rack limits, membership/IPs, per-GMF service state and transport health. State or membership alone does not prove IMEX transport. These checks apply to IMEX-capable SKUs. |
| NCCL | `nccl_local_allreduce`, `nccl_local_alltoall`, `nccl_allreduce`, `nccl_alltoall` | nccl-tests options and output, rank count, 16 GiB completion, correctness counters, MPI/UCX/HPC-X launch, exported environment, HCA/interface/GID/traffic-class settings, placement, IMEX/MNNVL/NVLS behavior and scale-specific thresholds. Calibrate each SKU, network mode and host count. |
| Frontend network | `nic_inventory`, `network_ping`, `tcp_bandwidth` | Configured interface link/speed and optional LLDP peer, source-to-target IPv4/IPv6 paths, VRF selection, packet loss, iperf3 JSON parsing and throughput floors. These checks are opt-in and site-specific. |
| Storage | `filesystem_perf`, `lustre_client`, `storage` | Configured filesystems, mount and striping data, fio safety/permissions, read/write performance and thresholds. Write jobs require an explicit directory and size. |
| Object storage | `object_storage`, `object_upload` | Credentials, endpoint/bucket access, TLS and upload/download behavior, cleanup and configured size/latency limits. These checks are opt-in and must use a test location. |
| Baselines and reports | Profiles and generated reports | Operator-approved healthy runs at each SKU, scale and network mode; repeatability under comparable clocks/load; calibrated tolerances; report and raw-output retention; and realistic wall-time budgets when tools must be built. Mock and hardware snapshots are not interchangeable. |

## Profile coverage

The exact lists are defined in `config/base.yaml` (with SKU and environment
overlays). In the default profiles, `basic` is the host handover gate,
`standard` adds stress, bandwidth, DCGM and RDMA, and `extended` adds placement,
IMEX and multi-host NCCL. A10 profiles intentionally omit RDMA and multi-host
NCCL for the supported no-RDMA deployment. Storage, frontend-network and
object-storage checks remain opt-in through `--tests` and their configuration
blocks.

Use `python3 -m gputest.cli list` to inspect the live registry and
`python3 -m gputest.cli run --dry-run` to review commands before touching a
host. Hardware runs should be repeated with `--network-mode single_plane` or
`multiplanar` when IMDS detection is unavailable.

## References

- [OCI GB300 guidance](https://github.com/oracle-quickstart/oci-gpu-quickstarts/blob/main/nvidia/GB300/README-GB300.md)
- [NVIDIA CUDA GPUs](https://developer.nvidia.com/cuda-gpus)
- [DCGM diagnostics](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/dcgm-diagnostics.html)
- [NVIDIA IMEX guide](https://docs.nvidia.com/multi-node-nvlink-systems/imex-guide/overview.html)

The repository does not contain the referenced GB300 handover PDF. Any
PDF-derived command, option, rail-to-NUMA mapping or performance example must
remain marked `TODO(verify)` until it is checked against the source and a real
host capture.
