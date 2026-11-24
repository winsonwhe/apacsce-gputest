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
- `--all`: run every module (the default with no arguments).

Hardware validation also needs the driver/CUDA, DCGM, `numactl`, iproute2, perftest, GNU `timeout`, MPI/UCX and nccl-tests as required by the selected checks. Configure paths and thresholds in `config.yaml`.

Mock runs only need Python, PyYAML and the project test tools.
