# 级别说明

| 级别 | 包含内容 | 用途 |
|---|---|---|
| `basic` | GPU Handover Doc 中的全部测试 | 基础交付验收 |
| `standard` | basic 加跨节点、跨机架、IP ping、错缆（mis-cabling）、链路抖动（flapping）、深层 GPU 测试及相关扩展验证 | 跨主机和 fabric 验证 |
| `extended` | Custom Image Test（自定义镜像测试） | 自定义镜像验证 |

A10 使用 `a10_basic`、`a10_standard` 和 `a10_extended`。针对支持的无 RDMA 部署，这些配置不包含 RDMA 和多机 NCCL。存储、Lustre、对象存储和可选网络检查需要站点配置，因此不放入默认级别。

运行时长和 DCGM 诊断级别配置在 `config/base.yaml` 的 `level_settings` 和 `dcgmi.diag_levels` 下。
