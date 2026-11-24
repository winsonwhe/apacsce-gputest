#!/usr/bin/env bash
# Install gputest dependencies and configure SSH after the repository is cloned.
#
# Run this script from the apacsce-gputest repository root. It supports Oracle
# Linux/RHEL-family and Ubuntu/Debian-family systems.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SSH_DIR="${HOME}/.ssh"
SSH_KEY="${SSH_DIR}/id_rsa"
HOST_FILE="all_gpu_nodes.txt"
VENV_DIR=".venv"

usage() {
  cat <<'EOF'
Usage: ./install.sh [OPTIONS]

Install and configure gputest. With no options, all modules run in order.

Modules:
  -d, --system-deps   Install OS packages required by Python and GPU builds.
  -g, --gpu-tools     Build missing gpu-burn, cuda-stream, nvbandwidth and gpu-fryer under /opt.
  -p, --python        Create/update .venv, install Python dependencies, pytest and Ruff, then run checks.
  -s, --ssh           Collect the SSH key and all_gpu_nodes.txt, then run setup-ssh.
  -a, --all           Run all modules (the default).
  -h, --help          Show this help and exit.

Environment:
  CUDA_ARCH=sm_86 ./install.sh --gpu-tools  # override BabelStream's CUDA architecture
  NVCC_PATH=/usr/local/cuda-13.2/bin/nvcc ./install.sh --gpu-tools

Examples:
  ./install.sh                 # install everything
  ./install.sh --system-deps   # install only OS packages
  ./install.sh --gpu-tools     # install only GPU tools (requires CUDA/nvcc)
  ./install.sh --python --ssh  # prepare Python and configure SSH
EOF
}

DO_SYSTEM=0
DO_GPU_TOOLS=0
DO_PYTHON=0
DO_SSH=0
if [[ "$#" -eq 0 ]]; then
  DO_SYSTEM=1
  DO_GPU_TOOLS=1
  DO_PYTHON=1
  DO_SSH=1
fi
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    -d|--system-deps) DO_SYSTEM=1 ;;
    -g|--gpu-tools) DO_GPU_TOOLS=1 ;;
    -p|--python) DO_PYTHON=1 ;;
    -s|--ssh) DO_SSH=1 ;;
    -a|--all)
      DO_SYSTEM=1
      DO_GPU_TOOLS=1
      DO_PYTHON=1
      DO_SSH=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ ! -f "${SCRIPT_DIR}/requirements.txt" || ! -d "${SCRIPT_DIR}/gputest" ]]; then
  echo "[ERROR] Run install.sh from a cloned apacsce-gputest repository." >&2
  exit 1
fi
cd "${SCRIPT_DIR}"

echo "[INFO] Repository: ${SCRIPT_DIR}"

if (( DO_SYSTEM )); then
  if [[ ! -f /etc/os-release ]]; then
    echo "[ERROR] Cannot detect the operating system (/etc/os-release is missing)." >&2
    exit 1
  fi
  # shellcheck source=/dev/null
  . /etc/os-release
  OS_ID="${ID:-unknown}"
  OS_ID_LIKE="${ID_LIKE:-}"
  OS_PRETTY_NAME="${PRETTY_NAME:-unknown}"

  case "${OS_ID}" in
    ubuntu|debian)
      PKG_MGR="apt-get"
      VENV_PACKAGES=(python3-pip python3-venv)
      ;;
    rhel|centos|rocky|almalinux|ol|oraclelinux|fedora)
      if command -v dnf >/dev/null 2>&1; then PKG_MGR="dnf"; else PKG_MGR="yum"; fi
      VENV_PACKAGES=(python3-pip)
      ;;
    *)
      case "${OS_ID_LIKE}" in
        *rhel*|*fedora*)
          if command -v dnf >/dev/null 2>&1; then PKG_MGR="dnf"; else PKG_MGR="yum"; fi
          VENV_PACKAGES=(python3-pip)
          ;;
        *debian*)
          PKG_MGR="apt-get"
          VENV_PACKAGES=(python3-pip python3-venv)
          ;;
        *)
          echo "[ERROR] Unsupported OS: ${OS_PRETTY_NAME} (id=${OS_ID})" >&2
          exit 1
          ;;
      esac
      ;;
  esac

  BUILD_PACKAGES=(git make cmake cargo)
  echo "[INFO] Detected OS: ${OS_PRETTY_NAME} (package manager: ${PKG_MGR})"
  if [[ "${PKG_MGR}" == "apt-get" ]]; then
    sudo apt-get update
    sudo apt-get install -y "${VENV_PACKAGES[@]}" "${BUILD_PACKAGES[@]}"
  else
    sudo "${PKG_MGR}" install -y "${VENV_PACKAGES[@]}" "${BUILD_PACKAGES[@]}"
  fi
fi

install_gpu_tools() {
  local name="$1"
  local source_dir="$2"
  local repository="$3"
  local binary="$4"
  local build_type="$5"

  if command -v "${name}" >/dev/null 2>&1; then
    echo "[INFO] ${name} already available at $(command -v "${name}"); skipping installation."
    return
  fi
  if [[ -x "${binary}" ]]; then
    echo "[INFO] ${name} already exists at ${binary}; skipping installation."
    sudo ln -sf "${binary}" "/usr/local/bin/${name}"
    return
  fi
  local nvcc_path="${NVCC_PATH:-$(command -v nvcc 2>/dev/null || true)}"
  if [[ -z "${nvcc_path}" && -x /usr/local/cuda/bin/nvcc ]]; then
    nvcc_path=/usr/local/cuda/bin/nvcc
  fi
  if [[ -z "${nvcc_path}" ]]; then
    for candidate in /usr/local/cuda-*/bin/nvcc; do
      if [[ -x "${candidate}" ]]; then
        nvcc_path="${candidate}"
        break
      fi
    done
  fi
  if [[ -z "${nvcc_path}" ]]; then
    echo "[ERROR] nvcc is required to build ${name}; install CUDA and rerun install.sh." >&2
    exit 1
  fi
  if [[ "${build_type}" == "cargo" ]]; then
    if ! command -v rustup >/dev/null 2>&1; then
      echo "[ERROR] gpu-fryer requires Rustup; install Rustup and rerun ./install.sh --gpu-tools." >&2
      exit 1
    fi
    echo "[INFO] Installing and using Rust toolchain 1.85.0 for ${name}."
    rustup toolchain install 1.85.0
    local cargo_cmd
    cargo_cmd="$(rustup which cargo --toolchain 1.85.0)"
  else
    local cargo_cmd=""
  fi

  echo "[INFO] Installing ${name} under ${source_dir}"
  if [[ ! -d "${source_dir}/.git" ]]; then
    if [[ -e "${source_dir}" ]]; then
      echo "[ERROR] ${source_dir} exists but is not a Git checkout; remove it or choose another path." >&2
      exit 1
    fi
    sudo git clone --depth 1 "${repository}" "${source_dir}"
  fi
  case "${build_type}" in
    make)
      local cuda_root="$(dirname "$(dirname "${nvcc_path}")")"
      sudo make -C "${source_dir}" \
        CUDAPATH="${cuda_root}" CUDA_HOME="${cuda_root}" CUDA_PATH="${cuda_root}"
      ;;
    cmake)
      local cmake_args=(-DCMAKE_CUDA_COMPILER="${nvcc_path}" -DMODEL=cuda)
      if [[ "${name}" == "cuda-stream" ]]; then
        cmake_args+=(-DCUDA_ARCH="${CUDA_ARCH:-sm_103}")
      fi
      sudo cmake -S "${source_dir}" -B "${source_dir}/build" "${cmake_args[@]}"
      sudo cmake --build "${source_dir}/build" -j "$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
      ;;
    cargo)
      sudo "${cargo_cmd}" install --path "${source_dir}" --root "${source_dir}"
      ;;
    *)
      echo "[ERROR] Unknown build type for ${name}: ${build_type}" >&2
      exit 1
      ;;
  esac
  if [[ ! -x "${binary}" ]]; then
    echo "[ERROR] Build completed but ${name} was not found at ${binary}." >&2
    exit 1
  fi
  sudo ln -sf "${binary}" "/usr/local/bin/${name}"
  echo "[INFO] Installed ${name} at ${binary}"
}

if (( DO_GPU_TOOLS )); then
  install_gpu_tools "gpu_burn" "/opt/gpu-burn" \
    "https://github.com/wilicc/gpu-burn.git" "/opt/gpu-burn/gpu_burn" make
  install_gpu_tools "cuda-stream" "/opt/BabelStream" \
    "https://github.com/UoB-HPC/BabelStream.git" "/opt/BabelStream/build/cuda-stream" cmake
  install_gpu_tools "nvbandwidth" "/opt/nvbandwidth" \
    "https://github.com/NVIDIA/nvbandwidth.git" "/opt/nvbandwidth/build/nvbandwidth" cmake
  install_gpu_tools "gpu-fryer" "/opt/gpu-fryer" \
    "https://github.com/huggingface/gpu-fryer.git" "/opt/gpu-fryer/bin/gpu-fryer" cargo
fi

if (( DO_SSH )); then
  mkdir -p "${SSH_DIR}"
  chmod 700 "${SSH_DIR}"
  if [[ -f "${SSH_KEY}" ]]; then
    chmod 400 "${SSH_KEY}"
    echo "[INFO] ${SSH_KEY} already exists; keeping it."
  else
    echo "Paste the PEM private key for the test nodes, then press Ctrl+D:"
    cat > "${SSH_KEY}"
    chmod 400 "${SSH_KEY}"
    echo "[INFO] Private key saved to ${SSH_KEY}"
  fi

  cat <<'EOF'
Enter the GPU nodes for all_gpu_nodes.txt, one node per line.

Example: different SSH users per host
  opc@192.0.2.10
  ubuntu@192.0.2.11
  admin@192.0.2.12

Example: use the default user for hosts without an explicit user
  192.0.2.10
  192.0.2.11
  ubuntu@192.0.2.12

Paste your GPU nodes list now, then press Ctrl+D:
EOF
  cat > "${HOST_FILE}"
  echo "[INFO] Saved host list to ${HOST_FILE}"
fi

if (( DO_PYTHON )); then
  if [[ ! -d "${VENV_DIR}" ]]; then
    echo "[INFO] Creating Python virtualenv in ${VENV_DIR}"
    python3 -m venv "${VENV_DIR}"
  fi
  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"
  python3 -m pip install --upgrade pip
  python3 -m pip install -r requirements.txt
  python3 -m pip install pytest ruff

  python3 -m pytest -q
  python3 -m ruff check .
fi

if (( DO_SSH )); then
  python3 -m gputest.cli setup-ssh \
    --hostfile "${HOST_FILE}" \
    --user ubuntu \
    --private-key "${SSH_KEY}"
fi
