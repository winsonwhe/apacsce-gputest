# Installation

## Python-only setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest -q
```

## Installer modules

`install.sh` must run from an existing checkout. It supports:

- `--system-deps`: install OS packages.
- `--python`: create/update `.venv`, install Python dependencies, pytest and Ruff.
- `--gpu-tools`: build configured GPU tools under `/opt`.
- `--ssh`: configure shared-key SSH and collect `all_gpu_nodes.txt`.
- `--control-plane`: treat the current host as a GPU-less jump host; skip local GPU-tool builds while retaining remote installation on hosts in `all_gpu_nodes.txt`.
- `--all`: run every module (the default with no arguments).

From a jump host without CUDA or a GPU, use:

```bash
./install.sh --control-plane --system-deps --python --ssh --gpu-tools
```

This prepares Python, Git, curl and SSH locally, then installs build dependencies and builds GPU tools on every GPU node in the inventory. The jump host does not need `nvidia-smi`, `nvcc`, or CUDA; GPU nodes need CUDA installed beforehand. `install.sh` automatically treats a host with no enumerated NVIDIA GPU as a control plane and skips local GPU tool builds; use `--control-plane` to force that behavior. For control-plane setup alone, use `./install.sh --control-plane --python --ssh`.

Hardware validation also needs the driver/CUDA, DCGM, `numactl`, iproute2, perftest, GNU `timeout`, MPI/UCX and nccl-tests as required by the selected checks. Configure paths and thresholds in `config/`.

Mock runs only need Python, PyYAML and the project test tools.
