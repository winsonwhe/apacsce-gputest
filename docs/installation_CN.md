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
- `--control-plane`：将当前主机视为无 GPU 的跳板机；跳过本地 GPU 工具构建，但保留对 `all_gpu_nodes.txt` 中 GPU 节点的远程安装。
- `--all`：执行所有模块；不带参数时的默认行为。

如果从没有 GPU/CUDA 的跳板机管理 GPU 节点，建议执行：

```bash
./install.sh --control-plane --system-deps --python --ssh --gpu-tools
```

该命令在跳板机上准备 Python、Git、curl 和 SSH，在清单中的每台 GPU 节点上安装系统构建依赖并构建 GPU 工具。跳板机不需要 `nvidia-smi`、`nvcc` 或 CUDA；GPU 节点需要预先安装 CUDA。`install.sh` 会自动将无法枚举 NVIDIA GPU 的主机视为跳板机，并跳过本机 GPU 工具构建；需要强制使用此行为时可加 `--control-plane`。若只需要控制端，不安装远程 GPU 工具，则使用 `./install.sh --control-plane --python --ssh`。

实际硬件验证还需要按检查类型准备驱动/CUDA、DCGM、`numactl`、iproute2、perftest、GNU `timeout`、MPI/UCX 和 nccl-tests。工具路径和阈值配置在 `config/ 中。

模拟运行只需要 Python、PyYAML 和项目测试工具。
