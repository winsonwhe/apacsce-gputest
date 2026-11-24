# 级别说明

| 级别 | 包含内容 | 用途 |
|---|---|---|
| `basic` | 本地主机预检和短时 `gpu_burn` | 快速主机验收；不要求 RDMA 或多机 |
| `standard` | basic 加带宽、BabelStream、DCGM、SSH，以及通用配置中的 RDMA 检查 | 日常 GPU 和 fabric 验证 |
| `extended` | standard 加本机 NCCL、适用时的 placement/IMEX 和多机 NCCL | 发布或集群验收 |

A10 使用 `a10_basic`、`a10_standard` 和 `a10_extended`。针对支持的无 RDMA 部署，这些配置不包含 RDMA 和多机 NCCL。存储、Lustre、对象存储和可选网络检查需要站点配置，因此不放入默认级别。

运行时长和 DCGM 诊断级别配置在 `config.yaml` 的 `level_settings` 和 `dcgmi.diag_levels` 下。
