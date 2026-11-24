# GPUTEST：GPU 验证工具包

[English](README.md) · [详细中文文档](doc/advanced-guide_CN.md)

使用预检、压力、带宽、DCGM、RDMA 和 NCCL 检查验证 NVIDIA GPU 主机。要求 Python 3.10+ 和 PyYAML；模拟模式无需 GPU。

## 项目架构

```text
config.yaml       # SKU 配置、级别、阈值和工具路径
gputest/          # CLI、执行器、检查、解析器和报告
tests/            # 可在无 GPU 环境运行的 pytest
fixtures/         # 模拟命令输出
doc/              # 中英文详细文档
results/          # 报告和原始命令输出
```

CLI 从配置读取级别，通过统一命令执行器运行检查，并保存 `PASS`、`WARN`、`FAIL` 或 `SKIP` 结果及原始输出。

## 安装

```bash
git clone https://github.com/winsonwhe/apacsce-gputest.git
cd apacsce-gputest
./install.sh
```

按需使用 `./install.sh --python`、`--system-deps`、`--gpu-tools` 或 `--ssh`。无 GPU 的跳板机使用 `./install.sh --control-plane --system-deps --python --ssh --gpu-tools`，GPU 工具会在清单中的远程节点构建。实际硬件测试还需要 NVIDIA 驱动/CUDA、DCGM、`numactl`、iproute2、perftest、MPI/UCX 和 nccl-tests（按测试类型准备）。详见[安装说明](doc/installation_CN.md)。

## 快速开始

```bash
# 查看所有已注册检查
python3 -m gputest.cli list

# 无 GPU，使用样例数据运行
python3 -m gputest.cli run --sku a10 --level basic --mock

# 只预览命令，不执行负载或 SSH
python3 -m gputest.cli run --sku gb300 --level standard --dry-run

# 本地主机实际验证
python3 -m gputest.cli run --sku gb300 --level standard

# 双主机验证
python3 -m gputest.cli run --sku gb300 --level extended --nodes host1,host2
```

使用 `--tests check1,check2` 指定检查；无法访问 IMDS 时可用 `--network-mode single_plane|multiplanar` 指定网络模式。报告和原始输出保存在 `results/`。详见[运行说明](doc/running-tests_CN.md)。

## 检查目录

| 类别 | 检查 |
|---|---|
| 预检 | `network_mode`、`nvidia_smi`、`ssh_connectivity`、`fabricmanager`、`numa_topology`、`rdma_iface`、`rdma_link`、`gpu_topology`、`numa_affinity`、`kernel_xid`、`ecc_remap`、`pcie_link`、`nvlink`、`clocks_throttle`、`software_versions`、`oca_version`、`placement`、`imex` |
| 压力 | `gpu_burn`、`gpu_fryer` |
| 带宽 | `nvbandwidth`、`babelstream` |
| RDMA | `gpudirect_rdma`、`rdma_perf`、`rdma_bw`、`rdma_lat`、`rdma_read`、`rdma_send`、`gdr_perf` |
| NCCL | `nccl_local_allreduce`、`nccl_local_alltoall`、`nccl_allreduce`、`nccl_alltoall` |
| 诊断 | `dcgmi`、`storage`、`nic_inventory`、`network_ping`、`tcp_bandwidth`、`lustre_client`、`filesystem_perf`、`object_storage`、`object_upload` |

使用 `python3 -m gputest.cli list` 查看注册表；完整命令和前置条件见[测试目录](doc/test-catalog_CN.md)。

## 级别

| 级别 | 用途 |
|---|---|
| `basic` | 主机本地健康检查和短时 GPU 压力测试；不要求 RDMA 或多机。 |
| `standard` | 在 basic 基础上增加带宽、BabelStream、DCGM，以及支持 RDMA 的机型上的 RDMA 检查。 |
| `extended` | 在 standard 基础上增加本机 NCCL、适用时的 placement/IMEX，以及多机 NCCL。 |

A10 使用专用的 `a10_basic`、`a10_standard` 和 `a10_extended` 配置，默认不包含 RDMA 和多机 NCCL。存储和对象存储检查需要站点路径或凭据，因此默认按需选择。详见[级别说明](doc/levels_CN.md)。
