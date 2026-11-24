# 测试目录

使用 `python3 -m gputest.cli list` 查看当前注册表。测试按用途分组如下。

| 分组 | 检查 | 典型前置条件 |
|---|---|---|
| 预检 | `network_mode`、`nvidia_smi`、`ssh_connectivity`、`fabricmanager`、`numa_topology`、`rdma_iface`、`rdma_link`、`gpu_topology`、`numa_affinity`、`kernel_xid`、`ecc_remap`、`pcie_link`、`nvlink`、`clocks_throttle`、`software_versions`、`oca_version`、`placement`、`imex` | NVIDIA 工具；部分检查需要 SSH/IMDS、RDMA 或 IMEX |
| 压力 | `gpu_burn`、`gpu_fryer` | CUDA 和对应后端 |
| 带宽 | `nvbandwidth`、`babelstream` | CUDA、编译工具和配置的可执行文件 |
| RDMA | `gpudirect_rdma`、`rdma_perf`、`rdma_bw`、`rdma_lat`、`rdma_read`、`rdma_send`、`gdr_perf` | 活跃 RDMA 设备、perftest；性能检查需要多机 |
| NCCL | `nccl_local_allreduce`、`nccl_local_alltoall`、`nccl_allreduce`、`nccl_alltoall` | nccl-tests；多机检查还需要 MPI/UCX 和 SSH |
| 诊断 | `dcgmi`、`storage`、`nic_inventory`、`network_ping`、`tcp_bandwidth`、`lustre_client`、`filesystem_perf`、`object_storage`、`object_upload` | DCGM 或站点专用路径、接口、服务和凭据 |

缺少工具、能力、主机数量或站点配置时，检查可能返回 `SKIP`。存储、网络和对象存储检查使用 `--tests` 显式选择。
