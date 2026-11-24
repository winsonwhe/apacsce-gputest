# Levels

| Level | Checks included | Use |
|---|---|---|
| `basic` | Local preflight and short `gpu_burn` | Fast host acceptance; no RDMA or multi-host requirement |
| `standard` | Basic plus bandwidth, BabelStream, DCGM, SSH and RDMA checks in the generic profile | Routine GPU and fabric validation |
| `extended` | Standard plus local NCCL, placement/IMEX where supported and multi-host NCCL | Release or cluster acceptance |

A10 uses `a10_basic`, `a10_standard` and `a10_extended`. These profiles omit RDMA and multi-host NCCL for the supported no-RDMA deployment. Storage, Lustre, object storage and optional network checks are not in a default level because they require site-specific configuration.

Durations and diagnostic levels are configured under `level_settings` and `dcgmi.diag_levels` in `config.yaml`.
