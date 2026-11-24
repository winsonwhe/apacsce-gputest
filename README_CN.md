# gputest：GPU 验证工具包

[English](README.md) | 简体中文

使用预检、持续 GPU 负载、内存带宽、DCGM、双主机 RDMA 和多主机 NCCL 检查，验证 OCI NVIDIA A10、A100、H100、H200、L40S、B200、GB200、B300 和 GB300 主机。项目要求 Python 3.10 及以上，运行时只依赖标准库和 PyYAML；模拟运行不需要 GPU。

## 项目架构

项目采用扁平的验证流程：CLI 从 `config.yaml` 读取配置组合，`gputest`
注册并执行检查，每项检查都会保存原始命令输出，并生成 `PASS`、`WARN`、
`FAIL` 或 `SKIP` 状态。

```text
.
├── config.yaml                 # SKU、配置组合、阈值、工具、网络和 NCCL 设置
├── requirements.txt            # 运行时 Python 依赖
├── gputest/                    # 应用源码
│   ├── cli.py                  # 命令行入口
│   ├── core.py                 # 结果、检查注册、命令执行和节点执行
│   ├── checks.py               # 本地 GPU 和系统验证检查
│   ├── multihost_checks.py     # SSH、RDMA 和 NCCL 检查
│   ├── optional_checks.py      # 可选的网络和存储检查
│   ├── parsers.py              # 命令输出的纯解析器
│   └── reporting.py            # 可读和机器可读的报告
├── tests/                      # Pytest 测试；无需 GPU 即可运行
├── fixtures/                   # 模拟命令输出和解析器测试样例
├── docs/                       # 硬件和部署说明
├── results/                    # 生成的报告和原始命令日志
├── README.md                   # 英文文档
└── README_CN.md                # 中文文档
```

CLI 通过 `core.py` 调用检查；检查使用统一的命令执行器，必要时将命令输出
交给 `parsers.py`，再把结果交由 `reporting.py` 生成报告。

## 安装

请先克隆仓库，再在仓库根目录执行 `install.sh`。脚本会自动识别
Oracle Linux/RHEL 系列或 Ubuntu/Debian 系列系统，安装项目所需的 Python
依赖，创建 `.venv`，运行测试和 Ruff 检查，并配置免密 SSH。

```bash
git clone https://github.com/winsonwhe/apacsce-gputest.git
cd apacsce-gputest
chmod +x install.sh
./install.sh
```

脚本需要交互式终端。运行时会要求输入测试节点使用的私钥，然后提示你直接在终端
粘贴 `all_gpu_nodes.txt` 的内容（每行一个节点）；粘贴完成后按 `Ctrl+D` 保存。SSH 默认用户为
`ubuntu`。运行前需要准备 `sudo` 权限、可访问系统软件包仓库的网络，
以及交互式终端。仓库必须预先克隆完成；`install.sh` 不会克隆或更新 Git 仓库。

在 GPU 主机上，需要安装 NVIDIA 驱动和 CUDA、适用时安装 Fabric Manager，以及 DCGM、numactl、iproute2（`ip`、`rdma`、`ss`）、perftest、GNU `timeout` 和支持 SSH 的 MPI/UCX。构建 nccl-tests（`all_reduce_perf` 和 `alltoall_perf`），并在 `config.yaml` 的 `tools` 中配置可执行文件路径。版本要求随 SKU 和部署环境变化；配置中的最低版本和性能下限需要通过真实硬件验证。

### 依赖工具

| 工具 | 用途及文档 |
|---|---|
| [Python](https://docs.python.org/3/) | 运行 CLI 和检查；要求 3.10 或更新版本。 |
| [PyYAML](https://pyyaml.org/wiki/PyYAMLDocumentation) | 加载 `config.yaml` 中的阈值、配置组合、工具路径和 NCCL 设置。 |
| [pytest](https://docs.pytest.org/) | 运行单元测试和编排测试，包括仅使用 CPU 的样例测试。 |
| [Ruff](https://docs.astral.sh/ruff/) | 检查 Python 代码的风格和常见问题。 |
| [NVIDIA 驱动](https://docs.nvidia.com/datacenter/tesla/)、[CUDA Toolkit](https://docs.nvidia.com/cuda/) | 提供 GPU 访问和 CUDA 工具。 |
| [Fabric Manager](https://docs.nvidia.com/datacenter/tesla/fabric-manager-user-guide/) | 管理受支持的 GB300/B300 系统的 GPU fabric。 |
| [DCGM](https://docs.nvidia.com/datacenter/dcgm/latest/) | 运行 NVIDIA GPU 诊断和健康检查。 |
| [numactl](https://github.com/numactl/numactl) | 选择 NUMA 节点并报告 CPU/内存拓扑。 |
| [iproute2](https://www.kernel.org/pub/linux/utils/net/iproute2/) | 提供接口、VRF 和 RDMA 检查所需的 `ip`、`rdma` 和 `ss`。 |
| [perftest](https://github.com/linux-rdma/perftest) | 提供 RDMA 带宽和延迟测试工具。 |
| [Open MPI](https://www.open-mpi.org/)、[UCX](https://openucx.readthedocs.io/) | 启动多主机 NCCL 任务并提供传输。 |
| [nccl-tests](https://github.com/NVIDIA/nccl-tests) | 提供 `all_reduce_perf` 和 `alltoall_perf`。 |
| [GNU coreutils timeout](https://www.gnu.org/software/coreutils/manual/html_node/timeout-invocation.html) | 限制外部命令运行时间。 |

模拟运行只需要 Python、PyYAML 和项目测试工具。实际硬件检查需要 GPU 主机依赖。需要构建基准测试源码时，还需要 `git`、`make`、CMake 和 `nvcc`。

设置 `build_if_missing: true` 后，本地主机可在缺少源码时克隆并构建 gpu-burn、nvbandwidth 和 BabelStream，但不会安装系统软件包。SSH 目标主机上的可执行文件须提前部署到相同的绝对路径；gpu-burn 的 `compare.ptx` 须与可执行文件位于同一目录。

## 快速开始

在仓库根目录运行：

```bash
python3 -m gputest.cli list
# 无需 GPU；使用样例数据：
python3 -m gputest.cli run --sku gb300 --level basic --mock
# 预览命令，不执行 SSH、构建或负载：
python3 -m gputest.cli run --sku gb300 --level standard --nodes n1,n2 \
  --network-mode multiplanar --dry-run
# 使用已安装工具进行本地实际验证：
python3 -m gputest.cli run --sku gb300 --level basic
# 双主机标准验证：
python3 -m gputest.cli run --sku gb300 --level standard --nodes n1,n2
```

可以使用 IP 地址或 SSH 主机名指定节点，重复使用 `--node`、使用逗号分隔的 `--nodes`，或者通过主机文件指定：

```bash
python3 -m gputest.cli run --sku gb300 --node 192.0.2.10 --node alice@192.0.2.11 --user opc --dry-run
python3 -m gputest.cli run --sku gb300 --nodes 192.0.2.10,192.0.2.11 --dry-run
python3 -m gputest.cli run --sku gb300 --hostfile hosts.txt --user opc --dry-run
```

`hosts.txt` 可以为每台主机分别指定 SSH 用户：

```text
# 每台主机可以使用不同的 SSH 用户
opc@192.0.2.10
ubuntu@192.0.2.11
admin@192.0.2.12
```

也可以省略部分主机的用户名，使用命令中 `--user` 指定的默认用户：

```text
192.0.2.10
192.0.2.11
ubuntu@192.0.2.12
```

使用 `--user opc` 时，前两台主机以 `opc` 登录，第三台以 `ubuntu` 登录。文件支持每行一个或多个主机，以逗号或空格分隔，`#` 后为注释；每台主机只能出现一次。`setup-ssh` 也支持这些主机选择选项。不指定主机选择选项时在本地运行。

基于 MPI 的 NCCL 和多节点 nvbandwidth 还需要在启动节点的 SSH 配置中，为每台主机或 SSH 别名设置对应的 `User`；`--user` 和 `user@host` 控制 gputest 自身的 SSH 连接，不会传递给 MPI。主机文件和启动节点的 SSH 配置应使用相同的名称或别名，并确保启动节点可免密连接其他主机。IPv6 MPI 目标请使用 MPI 安装支持的 SSH 别名。IMEX 成员检查要求所选主机名称与 IMEX 清单一致。

`--nodes` 指定 SSH 主机。各主机的预检、burn、nvbandwidth、BabelStream 和 DCGM 在有限数量的并行工作进程中执行；RDMA 使用前两台主机，NCCL 从所列候选主机中选择。不指定主机选择选项时，单主机检查在本地运行，多主机检查标记为 SKIP。`--tests CHECK,CHECK` 覆盖配置组合中的检查列表，但 burn 时长和 DCGM 级别仍由 `--level` 决定。`--gpu-count` 可覆盖配置的 GPU 数量。请使用独占或空闲的 GPU 主机。

控制端、启动端和其他主机之间需要可信的 SSH 密钥和 known_hosts。建议把 SSH 配置作为 GPU 测试的准备步骤：如果镜像已接受统一私钥对应的公钥，可执行：

```bash
python3 -m gputest.cli setup-ssh \
  --nodes 10.0.1.241,10.0.1.117 \
  --user ubuntu \
  --private-key ~/.ssh/gb300_shared_ed25519
```

该命令使用提供的私钥登录每台节点，把同一套私钥、公钥写入每台节点的 `~/.ssh`，将公钥加入 `authorized_keys`，并配置节点之间的 `known_hosts`。私钥会复制到所有节点，请只使用专用的集群测试密钥，并限制文件权限。执行 `--dry-run` 可先预览命令；完成后使用 `--tests ssh_connectivity` 验证控制端到节点以及启动端到其他节点的连接。所有外部命令均通过统一的执行助手运行，支持超时、原始日志、模拟和预览；远端命令还在目标主机上使用 GNU timeout，以限制 SSH 断开后负载的运行时间。

## 检查目录

下表中的“全部”指配置的 A10、A100、H100、H200、L40S、B200、GB200、B300 和 GB300。命令、参数和阈值来自 `config.yaml`，发现和遥测过程还可能执行其他命令。配置了某个 SKU 并不保证其工具、硬件能力或经过校准的阈值可用。

使用 `python3 -m gputest.cli run --sku <sku> --tests <check>` 运行单项检查；多主机检查加上 `--nodes n1,n2`，使用 `--dry-run` 预览。运行 `python3 -m gputest.cli list` 查看当前注册列表。下表按用途组织，实际执行顺序由配置组合或 `--tests` 决定；类别保留 CLI 中的名称。

### 系统验证

| 类别 | 检查 | 内容与主要命令 | 条件 |
|---|---|---|---|
| preflight | `software_versions` | 驱动、固件和软件版本；`nvidia-smi`、配置的 `nvcc`、`ofed_info`、`dcgmi`、`ibv_devinfo`；仅在机型要求时检查 `nvidia-fabricmanager` | 全部 |
| preflight | `oca_version` | Oracle Cloud Agent 软件包版本；检查 `/etc/os-release` 和软件包管理器 | 全部；未发现或无法比较的版本为 WARN |
| preflight | `numa_topology` | CPU 和内存 NUMA 拓扑；`numactl --hardware` | 全部 |
| preflight | `ssh_connectivity` | SSH 访问和启动端到其他主机的连接 | 全部；多主机 |

### GPU 验证

| 类别 | 检查 | 内容与主要命令 | 条件 |
|---|---|---|---|
| preflight | `nvidia_smi` | GPU、驱动、显存、ECC 模式和计算能力；`nvidia-smi --query-gpu` | 全部 |
| preflight | `gpu_topology` | GPU 和 NIC 拓扑；`nvidia-smi topo -m` | 全部 |
| preflight | `numa_affinity` | 驱动报告的 GPU CPU/NUMA 亲和性；`nvidia-smi topo -m` | 全部；未提供时 WARN |
| preflight | `pcie_link` | GPU PCIe 链路状态和协商参数；`nvidia-smi -q` | 全部 |
| preflight | `nvlink` | NVLink 状态；`nvidia-smi nvlink -s` | 当前配置支持 A100、H100、H200、B200、GB200、GB300；其他 SKIP |
| preflight | `fabricmanager` | Fabric Manager 服务状态；`systemctl is-active nvidia-fabricmanager` | A100、H100、H200、B200、GB200、B300、GB300；其他 SKIP |
| preflight | `kernel_xid` | 本次启动的内核日志中的 NVIDIA Xid；`journalctl -k --no-pager -b` | 全部 |
| preflight | `ecc_remap` | ECC 错误、退役页面和行重映射；`nvidia-smi -q -d ECC,REMAP,RETIRED_PAGES` | 全部 |
| preflight | `clocks_throttle` | GPU 硬件降速、温度和电源制动事件；查询 `clocks_event_reasons.active` | 全部 |
| diagnostics | `dcgmi` | DCGM 诊断；`dcgmi diag -r <level> -j` | 全部 |
| bandwidth | `babelstream` | GPU 内存带宽；`cuda-stream --device <gpu>` | 全部 |
| bandwidth | `nvbandwidth` | 配置的 GPU 内存和互连带宽；`nvbandwidth -t <configured-test>` | 多节点仅 GB300 且至少两台主机；见下方构建限制 |
| burn | `gpu_burn` | 持续计算压力和健康监控；`gpu_burn` 或 `gpu-fryer` | 全部 |

### 网络验证

| 类别 | 检查 | 内容与主要命令 | 条件 |
|---|---|---|---|
| preflight | `network_mode` | 通过 IMDS 检测或确认 OCI RDMA 网络模式 | 全部 |
| diagnostics | `nic_inventory` | 网卡载波、协商速率及可选 LLDP 对端；`ethtool`、`lldpcli` | 需启用并配置接口；LLDP 需要主机代理和交换机通告 |
| preflight | `rdma_iface`、`rdma_link` | 活动 RDMA 设备、网络接口和多平面 VRF 绑定；`rdma link`、`ip -j -d link show`；后者为兼容别名 | 需合适的 RDMA 设备 |
| diagnostics | `network_ping` | 配置的本地或跨主机 IP 路径和丢包，可选采样；`ping` | 需配置路径并允许 ICMP 和路由 |
| rdma | `gpudirect_rdma` | GPUDirect RDMA 前提条件；`lsmod`、`ib_write_bw --help` | 需满足 GPUDirect RDMA 前提条件 |
| diagnostics | `tcp_bandwidth` | 前端或后端 TCP 吞吐；`iperf3` | 需配置路径并启动目标服务器 |
| rdma | `rdma_bw`、`rdma_lat`、`rdma_perf` | 各 rail 的写入带宽、延迟或两者；`ib_write_bw`、`ib_write_lat` | 多主机，需合适的 RDMA 设备 |
| rdma | `rdma_read`、`rdma_send` | 各 rail 的读取或发送带宽；`ib_read_bw`、`ib_send_bw` | 多主机，需合适的 RDMA 设备 |
| rdma | `gdr_perf` | 使用 GPU 内存的各 rail RDMA 写入带宽；`ib_write_bw --use_cuda` | 多主机，需支持 CUDA 的 perftest 和 GPUDirect RDMA |

### 存储验证

| 类别 | 检查 | 内容与主要命令 | 条件 |
|---|---|---|---|
| diagnostics | `storage` | 文件系统容量、条带配置和可选只读 I/O；`df`、`xfs_info`、`lfs`、`fio` | 配置前禁用 |
| diagnostics | `lustre_client` | Lustre 挂载、容量和条带配置；`findmnt`、`lfs` | 需启用并配置已挂载路径 |
| diagnostics | `filesystem_perf` | 本地 NVMe、共享文件系统或 Lustre 的吞吐和 IOPS；`fio` | 需配置任务、路径和负载；写入需要空闲空间 |
| diagnostics | `object_storage` | OCI Object Storage 下载吞吐；`oci os object get` | 需配置存储桶、已有对象、临时目录和读取权限 |
| diagnostics | `object_upload` | OCI Object Storage 上传吞吐和临时对象清理；`oci os object put`、`delete` | 需配置源文件、存储桶、专用前缀、创建/删除权限及受支持的 OCI CLI |

### 分布式 GPU 验证

| 类别 | 检查 | 内容与主要命令 | 条件 |
|---|---|---|---|
| nccl | `nccl_local_alltoall`、`nccl_local_allreduce` | 单机 NCCL 集合通信带宽；`alltoall_perf`、`all_reduce_perf` | 本地主机 |
| preflight | `placement` | GPU 内存 fabric 和部署组位置；IMDS 查询或配置的清单 | 多主机 |
| preflight | `imex` | IMEX 服务和多主机成员；节点配置文件、`systemctl`、IMDS | GB200、GB300；多主机 |
| nccl | `nccl_allreduce`、`nccl_alltoall` | 多主机 NCCL 集合通信带宽；通过 `mpirun` 运行 nccl-tests | 多主机 |

`nvbandwidth.cuda_arch` 目前只列出 A10、B300 和 GB300；其他 SKU 即使已安装二进制文件，也需先在 `config.yaml` 中添加架构。GB300 配置了 `nvlink: true`；B300 的部署相关 NVLink 行为尚待验证，因此跳过。多平面 RDMA 的 perftest 命令加上配置的 `ip vrf exec <vrf> numactl -N <node>` 前缀，并使用配置的 IPv6/GID 选项。

`oca_version` 检查每台选定主机的 Oracle Cloud Agent 包版本：读取 `/etc/os-release`，在 Debian/Ubuntu 优先使用 `dpkg-query` 和 snap，在 Oracle Linux/RHEL 系列优先使用 `rpm`，也会探测其他包管理器。检查记录所有检测到的版本和原始输出，默认在所有配置组合中启用；设置 `oca_version.enabled: false` 可关闭。最低版本配置为 `1.64.0`，可通过带引号的数字 `oca_version.min_version` 调整。未配置最低版本或未检测到包时报告 WARN。比较只接受数字版本核心及可选的数字软件包发行号；epoch、预发布和其他后缀无法比较，报告 WARN。该检查不验证服务或插件健康状态。TODO(verify)：在实际 OCI 镜像上确认包名和查询输出；自定义或非软件包安装可能需要额外检测。

## 配置组合

| 配置组合 | 每台主机 burn 时长 | 检查 | 预计时间 |
|---|---:|---|---|
| `basic` | 120 秒 | 网络模式、GPU、GPU/NIC 拓扑、Fabric Manager、NUMA、RDMA 设备/VRF、短时 burn | 工具已安装时约 5 分钟 |
| `standard` | 1,200 秒 | basic 预检、SSH、burn、nvbandwidth、BabelStream、DCGM r2、RDMA 带宽和延迟 | 20 分钟 burn 加诊断和带宽测试时间 |
| `extended` | 3,600 秒 | standard 检查、GMF 位置、IMEX、DCGM r3、多主机 all-reduce 和 all-to-all | 1 小时以上 |

`a100_standard`、`h100_extended` 等 SKU 专用组合是基础组合的别名。Fabric Manager、NVLink 和 IMEX 按各 SKU 的能力标志选择，不支持的检查为 SKIP。调整 `level_settings.<level>.burn_duration_s` 可更改 burn 时长；设置 `dcgmi.diag_levels.extended: 4` 可使用 r4（使用 `a10_extended` 别名时也需调整该别名）。构建、超时、大量 GPU 和诊断级别都可能延长运行时间。basic 默认不包含 DCGM；显式选择时使用 r1。

## 网络、位置和检查行为

OCI shape 名称不会决定网络模式。自动模式根据目标主机 IMDS 的 `rdmaFabricData.planes` 判断：4 为多平面，缺失或 1 为单平面；IMDS 不可达时使用 `network.fallback_mode` 并报告 WARN。`--network-mode` 或 `network.mode` 可覆盖检测结果，`network_mode` 预检会检查可访问的 IMDS 是否存在冲突。模式预检失败会阻止负载运行。预览模式显示发现步骤的占位符，并使用显式模式或回退模式；可通过 `--network-mode` 预览所需命令。

- `rdma_iface`（兼容别名 `rdma_link`）发现 ACTIVE + LINK_UP 设备及网络接口。单平面的数量和可选固定设备按 SKU 配置，不假定接口名称、VRF 或 IPv6。多平面验证四个 VF 设备、`vrf_r0..3` 和各网络接口的 VRF 主设备，忽略未使用的 DOWN 链路。`gpu_topology` 检查 GPU/NIC 是否出现在拓扑中。
- `gpu_burn` 验证错误计数、GPU 数量和各 GPU 吞吐偏差，并在负载期间采样温度和功率。无法获得遥测时为 WARN。可选的 `gpu-fryer` **不检查数值正确性**。采样可能遗漏瞬时事件；不会强制执行绝对温度或功率上限。
- `nvbandwidth` 将各配置的聚合 SUM（GB/s）与下限比较。可选的 GB300 多节点模式需要 MULTINODE 构建、同一 GMF 和 IMEX；参见 [NVIDIA 指南](https://github.com/NVIDIA/nvbandwidth#multi-node-support)。
- `babelstream` 在每个 GPU 上运行，将 MB/s 换算成 GB/s，比较每项 Copy/Mul/Add/Triad/Dot 测量并报告均值和离散程度。`dcgmi` 请求对应诊断级别的 JSON，即使命令失败也保留各测试和实体的结果及警告。
- `rdma_perf` 对每个 rail/设备执行 `ib_write_bw` 和 `ib_write_lat`；`rdma_bw` 和 `rdma_lat` 各选一项，`rdma_read` 和 `rdma_send` 执行对应带宽测试，`gdr_perf` 使用 `--use_cuda` 测试 GPU 内存。程序自动读取服务端/客户端地址，并在启动客户端前探测服务端就绪状态。多平面使用配置的 VRF、NUMA、IPv6 和 GID；单平面优先 IPv4，仅在发现或通过 `rdma_perf.single_plane.ip_family` 固定时启用 IPv6。报告各 rail 和 `(max - min) / mean` 差异。
- `numa_affinity` 验证驱动是否报告每个 GPU 的 CPU 和 NUMA 亲和性；多平面 RDMA 命令还会应用配置的各 rail NUMA 绑定。
- `nccl_allreduce` / `nccl_alltoall` 每个 GPU 使用一个 rank 和 `-b 1G -e 16G -f 2 -g 1 -n 50`。环境和启动参数位于模式专用配置块；多平面在超过 32 台主机时切换调优，单平面 HCA 名称通过发现获得且所选主机必须一致。请求的最大消息尺寸下，in-place 和 out-of-place 的 busbw 均须达到下限；命令错误、缺失输出和验证错误均导致失败。
- `nccl_local_allreduce` / `nccl_local_alltoall` 单独执行单机集合通信；独立阈值暂未设置，等待按 SKU 和 GPU 数量采集基线。
- `storage` 可收集 `df`、XFS/Lustre 容量和条带信息，并对已有文件运行只读 `fio`。只有配置专用 `storage.path` 后才启用。

### 可选网络和存储验收检查

`extended` 包含以下检查，但各项在启用自己的配置并提供所需路径或接口之前均处于禁用状态，也可通过 `--tests` 选择。工具路径在 `config.yaml` 的 `tools` 下配置；`ethtool`、`lldpcli`、Linux `ping`、`iperf3`、`findmnt`、`lfs`、`fio` 和 OCI CLI 仅为使用它们的检查所需。先用 `--dry-run` 预览所有主机的命令。性能阈值取决于部署环境；未配置阈值时报告 WARN。

- `nic_inventory` 使用 `ethtool` 检查各配置网卡的载波和协商速率，并可选比较 LLDP 机箱和端口标识。LLDP 需要交换机通告和主机代理；缺少对端时 WARN。各主机上的接口必须能被 `ethtool` 看到，虚拟功能可能不提供物理链路速率。LLDP 和连通性可以发现部分接线错误，但不能证明所有接线正确；需验证部署的 `lldpcli` 字段和预期交换机端口清单。
- `network_ping` 检查明确配置的 IPv4/IPv6 源和目标路径，可选源 VRF。每条路径的 `node` 指向 `--nodes` 中的名称，省略时本地执行。仅列出当前部署中预期可通信的路径。`sample_count: 0` 检查全部路径；正数使用 `seed` 对每台源主机进行可复现采样。丢包超过 `max_loss_pct` 时失败。需允许 ICMP、路由、地址和 VRF 访问；同机 ping 可能不经过网卡或交换机。
- `tcp_bandwidth` 使用 `iperf3` 从配置的源地址测量 TCP 吞吐，可选 VRF。需在每个目标单独启动服务端、开放端口并确保足够的 CPU 和带宽。`reverse: true` 测量反向；`node` 规则与 ping 相同。此检查测试 TCP/IP；RDMA verbs 由 `rdma_perf` 等检查在前两台主机上单独测试。
- `lustre_client` 验证路径位于 Lustre 文件系统并运行 `lfs df` 和 `lfs getstripe`；需在各主机安装客户端并挂载。实际 I/O 测量使用 `filesystem_perf`。
- `filesystem_perf` 对本地 NVMe、共享文件系统或 Lustre 运行配置的 `fio` 顺序或随机读写任务。需独立验证挂载点和底层设备。读取需要已有测试文件并使用只读模式；写入在专用目录创建唯一文件并请求 fio 删除，需预留空间，并在超时、中断或失败后检查残留。各主机并行执行，结果按主机报告，并非同步聚合基准。工作负载、块大小、队列深度、文件大小和阈值应匹配验收计划，并考虑缓存、条带和共享负载。
- `object_storage` 将已有对象下载到临时目录中的唯一文件，测量包含 CLI 启动的端到端吞吐后删除文件。`object_upload` 通过条件创建将已有源文件上传到专用前缀下的唯一对象，测量吞吐后删除该对象。各主机需配置 OCI CLI 身份认证、区域/配置文件和存储桶权限；上传需要创建和删除权限，下载需要读取权限和临时空间。请求和存储可能产生费用；超时、中断或清理失败可能留下文件或对象，应检查记录的路径或名称并清理。TODO(verify)：使用实际 OCI CLI 验证条件上传选项和分段上传行为。这些检查不测试元数据请求速率。

配置 `config.yaml` 相应部分后，可预览：

```bash
python3 -m gputest.cli run --sku gb300 --nodes n1,n2 \
  --tests nic_inventory,network_ping,tcp_bandwidth,lustre_client,filesystem_perf,object_storage,object_upload --dry-run
```

这些数据平面探测不会审计所有 VCN 路由表、安全列表、网络安全组或物理交换机端口。基于 CFAB 的前端 RDMA 和特定 TCP-over-RDMA 协议尚未实现，需先确认部署含义及支持的软硬件栈。协商链路速率不等于实测应用吞吐；应在建立可靠基线后再配置 200/400 Gb/s 目标。

NCCL/placement 根据 `customerGpuMemoryFabric`（GMF）对节点分组。最多 18 台主机的任务必须位于同一 GMF；更大任务优先选择相同 `customerLocalBlock`。跨机架的 block 不同或未知时报告 WARN。`--node-count N` 为 NCCL 选择 N 台候选主机；单机检查仍覆盖全部 `--nodes`。非 OCI 清单或额外机架成员可显式配置：

```yaml
placement:
  rack_max_nodes: 18
  inventory:
    n1: {gmf: rack1, local_block: block1}
    n2: {gmf: rack1, local_block: block1}
```

IMEX 仅用于 GB300，并在启用 MNNVL 的 NCCL 前检查。已有节点文件必须包含选定的同 GMF 主机，不能包含跨机架成员；额外成员需要清单条目。使用 IMEX 文件中的准确主机名或 IP，且服务必须运行。gputest 验证成员和状态，不安装、重启或配置 IMEX，也不证明传输健康。IMEX 域按 GMF 划分，不跨机架。

## 报告和阈值

每次运行在 `results/run-<timestamp>/` 下写入 `results.json`、`results.md` 和完整原始命令日志，可通过 `--output-dir` 覆盖。Markdown 包含概览表、各检查测量值、阈值规则/数值/来源、原始输出摘录，以及每个 WARN/FAIL 的排障提示。JSON 包含相同的 `metrics`、`thresholds` 和 `hints` 字段。终端显示简要汇总；任何检查失败时退出码为 1，否则为 0（WARN/SKIP 仍会显示）。重新生成 Markdown 并打印汇总：

```bash
python3 -m gputest.cli report results/run-YYYYMMDD-HHMMSS
```

阈值来源标记为 **config default**、**PDF example** 或 **baseline**，并记录配置路径或基线文件/键。修改后的配置值仍标记为 config default，以区别示例和基线；报告会记录所用配置文件。手动替换来自 PDF 的限值时，也要设置 `threshold_source: config default`。命令或解析错误以及报告的数值计算失败不依赖性能阈值。

随附的多平面 RDMA 示例（约 459 Gb/s、3.8–4.0 us）使用较宽限值（最低 321.3 Gb/s、最高 6 us），**只是示例，不是性能保证**。单平面 RDMA 和 NCCL 默认未设置限值，校准前为 WARN。可选的 `nccl.<mode>.example_reference_gbs.<collective>` 接受 2/16/32/64/80 等精确规模键，默认使用参考值的 80%；由于缺少经过验证的 PDF 规模测量，表格保持为空。nvbandwidth/BabelStream 的配置下限也需要校准。排障建议在 `config.yaml` 中，依据提供的手册摘录及 [OCI README](https://github.com/oracle-quickstart/oci-gpu-quickstarts/blob/main/nvidia/GB300/README-GB300.md)。

## 已知良好基线

```bash
python3 -m gputest.cli run --sku gb300 --level standard --nodes n1,n2 \
  --baseline save --baseline-file baselines/site.json
python3 -m gputest.cli run --sku gb300 --level standard --nodes n1,n2 \
  --baseline compare --baseline-file baselines/site.json
```

仅当选定检查完成且没有失败、缺失工具或操作警告时才保存快照；唯一例外是仅因未设置阈值而出现的基准测试 WARN，以便首次校准。失败运行或预览不会覆盖已有快照。保存前请确认硬件和负载处于已知良好状态，软件无法独立证明这一点。

比较覆盖各 GPU burn 吞吐、每个 nvbandwidth SUM、每个 GPU 的 BabelStream 测量、每条 RDMA rail 的带宽/延迟，以及最大 NCCL 消息尺寸的两种内存布局。比较保留配置限值并增加基线限值；性能回退、健康/状态回退及缺失或不兼容的观测均会失败。`baseline` 中配置容差：通常 20%，burn 为 10%，NCCL 为 20%（记录带宽的 80%）；延迟可在容差范围内增加。

记录区分 SKU、模式、GPU 数量、规模、配置组合、负载选项以及模拟/实际运行。时长、精度、消息尺寸或调优变化需要新基线。各检查独立记录，保存其他组合或检查会添加对应范围的记录；同一检查/规模的记录会被后续成功保存替换。主机按位置配对，rail/设备和 GPU 指标名称必须一致。旧版 gputest 的版本化基线文件需要重新生成。模拟基线仅用于编排测试。

## 使用 mpirun 运行多主机 NCCL

NCCL 在第一台选定主机上使用 `mpirun`。将 `tools.mpirun` 设为 Open MPI/HPC-X 可执行文件，模式专用 MPI 参数位于 `nccl.<mode>.mpi_args`。所有选定主机需要匹配的 nccl-tests、CUDA/NCCL/MPI 库，以及控制端和启动主机到目标主机的可信免密 SSH。使用各主机相同的绝对路径。

```bash
# 预览两种集合通信和所有远端命令：
python3 -m gputest.cli run --sku gb300 --nodes n1,n2 \
  --network-mode multiplanar --tests nccl_allreduce,nccl_alltoall --dry-run
# 通过 mpirun 执行：
python3 -m gputest.cli run --sku gb300 --nodes n1,n2 \
  --network-mode multiplanar --tests nccl_allreduce,nccl_alltoall
```

生成的 MPI 命令指定所选主机及 slots、总 rank 数、每个 GPU 一个 rank，并通过 `-x` 传递配置的环境变量。集合通信前执行 GMF/local-block 选择和各 GMF 的 IMEX 验证。测试前请按集群流程准备独占或空闲主机。

## 添加检查

在 `gputest/parsers.py` 添加纯解析函数，在 `gputest/checks.py` 添加一个带装饰器的函数，并添加样例、单元测试和可选的配置组合条目。所有外部命令使用 `ctx.run`，可配置的期望值放入 YAML。以下为完整的 persistence mode 检查示例：

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
# config.yaml (also add persistence to a level if desired)
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


使用 `python3 -m gputest.cli run --sku gb300 --tests persistence --mock` 运行。依赖硬件相关解析之前，请用真实输出替换示例样例并记录来源。

## 仍需硬件验证

逐项清单见 [docs/hardware-validation.md](docs/hardware-validation.md)。仅 CPU 验证未使用 GPU 硬件或 SSH/MPI 集群。本仓库缺少参考 PDF；来自 PDF 的 NUMA 映射、选项和性能示例仍保留 `TODO(verify)`。样例来源记录在 [fixtures/README.md](fixtures/README.md)。
