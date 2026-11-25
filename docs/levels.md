# Levels

| Level | Checks included | Use |
|---|---|---|
| `basic` | All tests from the GPU Handover Doc | Baseline handover validation |
| `standard` | Basic plus cross-node, cross-rack, IP ping, mis-cabling, flapping, deep GPU tests, and related extended validation | Cross-host and fabric validation |
| `extended` | Custom Image Test | Custom image validation |

A10 uses `a10_basic`, `a10_standard` and `a10_extended`. These profiles omit RDMA and multi-host NCCL for the supported no-RDMA deployment. Storage, Lustre, object storage and optional network checks are not in a default level because they require site-specific configuration.

Durations and diagnostic levels are configured under `level_settings` and `dcgmi.diag_levels` in `config.yaml`.
