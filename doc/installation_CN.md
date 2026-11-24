# 安装说明

## 仅安装 Python 依赖

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest -q
```

## 安装脚本模块

`install.sh` 必须在已克隆的仓库根目录执行：

- `--system-deps`：安装系统依赖。
- `--python`：创建或更新 `.venv`，安装 Python 依赖、pytest 和 Ruff。
- `--gpu-tools`：在 `/opt` 下构建配置的 GPU 工具。
- `--ssh`：配置共享密钥 SSH 并收集 `all_gpu_nodes.txt`。
- `--all`：执行所有模块；不带参数时的默认行为。

实际硬件验证还需要按检查类型准备驱动/CUDA、DCGM、`numactl`、iproute2、perftest、GNU `timeout`、MPI/UCX 和 nccl-tests。工具路径和阈值配置在 `config.yaml` 中。

模拟运行只需要 Python、PyYAML 和项目测试工具。
