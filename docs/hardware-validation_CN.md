# 仍需进行的硬件验证

[English](hardware-validation.md)

仅使用 CPU fixture 可以验证解析、命令规划和结果处理，不能证明实际 GPU 主机、网络 fabric 或存储服务健康。将某个 profile 用于生产前，应在每个支持的 SKU 和网络模式上运行检查。每项检查都会把命令输出保存在运行目录中，应使用这些输出建立硬件基线。

## 逐项验证清单

| 领域 | 检查 | 需要在真实硬件上确认的内容 |
|---|---|---|
| 网络与放置 | `network_mode` | IMDS 可访问性和 schema；`rdmaFabricData.planes` 的取值；自动检测、`network.mode` 覆盖和非 OCI 回退；混合模式是否被拒绝。 |
| GPU 清单 | `nvidia_smi` | GPU 数量、型号、显存、驱动最低版本、ECC 字段可用性和 SKU 的部分主机策略；确认 B300/GB300 区分及 CUDA 最低版本配置。 |
| GPU 健康 | `kernel_xid`、`ecc_remap`、`pcie_link`、`nvlink`、`clocks_throttle` | 驱动输出格式、Xid 和 ECC/行重映射解释、PCIe 代际/宽度及 AER 计数、NVLink 状态/错误计数和时钟事件掩码。时钟检查是快照，不能证明没有瞬态事件。 |
| 拓扑与亲和性 | `gpu_topology`、`numa_topology`、`numa_affinity` | GPU/NIC 枚举、拓扑表头、CPU/NUMA 亲和性列、实际有 CPU 和内存的 NUMA 节点、0 MB 节点，以及 x86 或 Grace 布局。设备存在不等于带宽或亲和性正确。 |
| 软件与服务 | `software_versions`、`oca_version`、`fabricmanager` | 驱动、CUDA、VBIOS、OFED/NIC、DCGM、OCA 以及适用时 Fabric Manager 的版本；包管理器输出；服务名称、权限和故障行为。应按实际镜像校准最低版本。 |
| RDMA 发现 | `rdma_iface`、`rdma_link` | ACTIVE + LINK_UP 的 HCA 数量和名称、HCA 到 netdev 的映射以及前端 HCA 过滤。多平面模式还要确认四个 `rdma_vf_rail*`、`vrf_r*` 以及 VF 到 VRF 的 master 绑定。未使用的 DOWN/DISABLED 条目可以正常存在。 |
| RDMA 前置条件 | `gpudirect_rdma` | `nvidia_peermem` 已加载，且安装的 perftest 支持 CUDA 模式。 |
| RDMA 性能 | `rdma_perf`、`rdma_bw`、`rdma_lat`、`rdma_read`、`rdma_send`、`gdr_perf` | 服务端就绪、控制端口、两端 rail 顺序、可路由地址和 IP 族、MTU/GID、NUMA 绑定、CUDA buffer 支持，以及真实的平均带宽/延迟列。多平面 VRF/IPv6 命令和 rail 到 NUMA 的映射在参考手册可用前仍标记为 `TODO(verify)`。单平面名称和阈值依部署而定；应校准配置下限，不能把示例值当作保证。 |
| 压力与带宽 | `gpu_burn`、`gpu_fryer`、`nvbandwidth`、`babelstream` | CUDA 架构和构建参数、运行时长、数值错误、温度/散热/功耗、遥测、GPU 均衡性、原生输出单位和测试名、P2P/NVLink、设备选择及 SKU 下限。Fryer 只产生负载，不能证明数值正确性。 |
| DCGM | `dcgmi` | 已安装的 JSON/schema、支持的诊断级别、运行权限、实体级发现、空闲 GPU 要求，以及 r1/r2/r3/r4 的实际覆盖范围。 |
| SSH 与执行 | `ssh_connectivity` | 控制端到主机、launcher 到对端的密钥，known-host 策略、超时、远端权限、取消和清理。探测通过不等于已配置完整 mesh。 |
| 放置与 IMEX | `placement`、`imex` | IMDS 的 GMF/local-block、单 GMF 选择、跨 rack 偏好、rack 上限、成员/IP、每个 GMF 的服务状态和传输健康。状态或成员信息本身不能证明 IMEX 传输正常；这些检查只适用于支持 IMEX 的 SKU。 |
| NCCL | `nccl_local_allreduce`、`nccl_local_alltoall`、`nccl_allreduce`、`nccl_alltoall` | nccl-tests 参数和输出、rank 数、16 GiB 完成、正确性计数器、MPI/UCX/HPC-X 启动、环境变量导出、HCA/接口/GID/traffic class、放置、IMEX/MNNVL/NVLS，以及按规模设置的阈值。应按 SKU、网络模式和主机数分别校准。 |
| 前端网络 | `nic_inventory`、`network_ping`、`tcp_bandwidth` | 配置接口的链路/速率和可选 LLDP 对端、IPv4/IPv6 源到目标路径、VRF、丢包率、iperf3 JSON 解析和吞吐下限。这些检查需要站点配置并默认选择性启用。 |
| 存储 | `filesystem_perf`、`lustre_client`、`storage` | 配置的文件系统、挂载和 striping 信息、fio 安全性/权限、读写性能和阈值。写入任务必须显式配置目录和大小。 |
| 对象存储 | `object_storage`、`object_upload` | 凭据、endpoint/bucket 访问、TLS、上传/下载行为、清理以及配置的大小/延迟限制。这些检查需要选择性启用并使用测试位置。 |
| 基线与报告 | Profile 和生成的报告 | 每个 SKU、规模和网络模式下由运维确认的健康运行；相同负载/时钟下的可重复性；校准后的容差；报告和原始输出留存；以及工具需要构建时的真实耗时。模拟快照不能替代硬件快照。 |

## Profile 覆盖范围

具体列表定义在 `config/base.yaml`，并可由 SKU 和环境 overlay 覆盖。默认配置中，`basic` 是主机交接门禁，`standard` 增加压力、带宽、DCGM 和 RDMA，`extended` 再增加放置、IMEX 和多主机 NCCL。支持的无 RDMA A10 部署会在专用 profile 中省略 RDMA 和多主机 NCCL。存储、前端网络和对象存储检查需要通过 `--tests` 及对应配置块选择性启用。

使用 `python3 -m gputest.cli list` 查看实时注册表，使用 `python3 -m gputest.cli run --dry-run` 在接触主机前检查命令。IMDS 不可用时，硬件运行应显式使用 `--network-mode single_plane` 或 `multiplanar`。

## 参考资料

- [OCI GB300 指南](https://github.com/oracle-quickstart/oci-gpu-quickstarts/blob/main/nvidia/GB300/README-GB300.md)
- [NVIDIA CUDA GPU 列表](https://developer.nvidia.com/cuda-gpus)
- [DCGM 诊断](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/dcgm-diagnostics.html)
- [NVIDIA IMEX 指南](https://docs.nvidia.com/multi-node-nvlink-systems/imex-guide/overview.html)

仓库中没有引用的 GB300 handover PDF。任何来自 PDF 的命令、参数、rail 到 NUMA 映射或性能示例，在对照原文并取得真实主机输出前都必须保留 `TODO(verify)` 标记。
