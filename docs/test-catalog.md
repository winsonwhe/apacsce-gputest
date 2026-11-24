# Test catalog

Use `python3 -m gputest.cli list` for the live registry. The checks are grouped below by purpose.

| Group | Checks | Typical prerequisites |
|---|---|---|
| Preflight | `network_mode`, `nvidia_smi`, `ssh_connectivity`, `fabricmanager`, `numa_topology`, `rdma_iface`, `rdma_link`, `gpu_topology`, `numa_affinity`, `kernel_xid`, `ecc_remap`, `pcie_link`, `nvlink`, `clocks_throttle`, `software_versions`, `oca_version`, `placement`, `imex` | NVIDIA tools; SSH/IMDS for selected checks; RDMA or IMEX only where applicable |
| Burn | `gpu_burn`, `gpu_fryer` | CUDA and the selected backend |
| Bandwidth | `nvbandwidth`, `babelstream` | CUDA, compiler/build tools and configured binaries |
| RDMA | `gpudirect_rdma`, `rdma_perf`, `rdma_bw`, `rdma_lat`, `rdma_read`, `rdma_send`, `gdr_perf` | Active RDMA devices, perftest; multi-host for performance checks |
| NCCL | `nccl_local_allreduce`, `nccl_local_alltoall`, `nccl_allreduce`, `nccl_alltoall` | nccl-tests; MPI/UCX and SSH for multi-host checks |
| Diagnostics | `dcgmi`, `storage`, `nic_inventory`, `network_ping`, `tcp_bandwidth`, `lustre_client`, `filesystem_perf`, `object_storage`, `object_upload` | DCGM or site-specific paths, interfaces, services or credentials |

Checks may return `SKIP` when a tool, capability, host count or site configuration is unavailable. Use `--tests` for opt-in storage, network and object-storage checks.
