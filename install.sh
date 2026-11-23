#!/usr/bin/env bash
#
# setup_gputest.sh
# 1. Interactively write the private key of test nodes to ~/.ssh/id_rsa
# 2. Detect the OS (Oracle Linux / RHEL family or Ubuntu / Debian family),
#    install packages with the matching package manager, clone the
#    apacsce-gputest repository, create a Python virtualenv to avoid the
#    PEP 668 "externally-managed-environment" restriction, install
#    dependencies, run tests and lint checks, and set up passwordless SSH
#    access
#
# Supported OS:
#   - RHEL family: Oracle Linux, RHEL, CentOS, Rocky, AlmaLinux, Fedora (dnf/yum)
#   - Debian family: Ubuntu, Debian (apt-get)

set -euo pipefail

SSH_DIR="${HOME}/.ssh"
SSH_KEY="${SSH_DIR}/id_rsa"
REPO_DIR="apacsce-gputest"
HOST_FILE="all_gpu_nodes.txt"
VENV_DIR=".venv"

# ---------- 0. Detect the OS and define the package install function ----------
if [ -f /etc/os-release ]; then
  # shellcheck source=/dev/null
  . /etc/os-release
  OS_ID="${ID:-unknown}"
  OS_ID_LIKE="${ID_LIKE:-}"
  OS_PRETTY_NAME="${PRETTY_NAME:-unknown}"
else
  OS_ID="unknown"
  OS_ID_LIKE=""
  OS_PRETTY_NAME="unknown"
fi

echo "[INFO] Detected OS: ${OS_PRETTY_NAME} (id=${OS_ID})"

case "${OS_ID}" in
  ubuntu|debian)
    PKG_MGR="apt-get"
    # python3-venv provides the ensurepip backend required by `python3 -m venv`
    VENV_EXTRA_PKGS="python3-venv"
    echo "[INFO] Using package manager: apt-get"
    sudo apt-get update
    install_pkg() {
      [ $# -eq 0 ] && return 0
      sudo apt-get install -y "$@"
    }
    ;;
  rhel|centos|rocky|almalinux|ol|oraclelinux|fedora)
    if command -v dnf >/dev/null 2>&1; then
      PKG_MGR="dnf"
    else
      PKG_MGR="yum"
    fi
    VENV_EXTRA_PKGS=""
    echo "[INFO] Using package manager: ${PKG_MGR}"
    install_pkg() {
      [ $# -eq 0 ] && return 0
      sudo "${PKG_MGR}" install -y "$@"
    }
    ;;
  *)
    # Fall back to ID_LIKE for derivatives that do not set ID directly
    case "${OS_ID_LIKE}" in
      *rhel*|*fedora*)
        if command -v dnf >/dev/null 2>&1; then
          PKG_MGR="dnf"
        else
          PKG_MGR="yum"
        fi
        VENV_EXTRA_PKGS=""
        echo "[INFO] Using package manager: ${PKG_MGR}"
        install_pkg() {
          [ $# -eq 0 ] && return 0
          sudo "${PKG_MGR}" install -y "$@"
        }
        ;;
      *debian*)
        PKG_MGR="apt-get"
        VENV_EXTRA_PKGS="python3-venv"
        echo "[INFO] Using package manager: apt-get"
        sudo apt-get update
        install_pkg() {
          [ $# -eq 0 ] && return 0
          sudo apt-get install -y "$@"
        }
        ;;
      *)
        echo "[ERROR] Unsupported OS: ${OS_ID} (${OS_PRETTY_NAME})" >&2
        exit 1
        ;;
    esac
    ;;
esac

# ---------- 1. Prepare the SSH directory ----------
mkdir -p "${SSH_DIR}"
chmod 700 "${SSH_DIR}"

# ---------- 2. Interactively write the private key ----------
if [ -f "${SSH_KEY}" ]; then
  echo "[INFO] ${SSH_KEY} already exists, skip writing private key."
else
  echo "Enter the private key of all test nodes:"
  echo "Paste the PEM-format private key below, then press Ctrl+D when finished."
  # Read the multi-line pasted content (-----BEGIN ... PRIVATE KEY----- ... -----END ...-----)
  cat > "${SSH_KEY}"
  chmod 400 "${SSH_KEY}"
  echo "[INFO] Private key saved to ${SSH_KEY}"
fi

# ---------- 3. Install git ----------
install_pkg git

# ---------- 4. Clone the repository ----------
if [ -d "${REPO_DIR}" ]; then
  echo "[INFO] Directory ${REPO_DIR} already exists, skip cloning."
else
  git clone https://github.com/winsonwhe/apacsce-gputest.git
fi
cd "${REPO_DIR}"

# ---------- 5. Create all_gpu_nodes.txt if missing, then edit it (interactive) ----------
if [ ! -f "${HOST_FILE}" ]; then
  touch "${HOST_FILE}"
  echo "[INFO] ${HOST_FILE} not found, an empty file was created."
fi
vim "${HOST_FILE}"

# ---------- 6. Create a virtualenv and install Python dependencies ----------
install_pkg python3-pip
if [ -n "${VENV_EXTRA_PKGS}" ]; then
  # shellcheck disable=SC2086
  install_pkg ${VENV_EXTRA_PKGS}
fi

if [ ! -d "${VENV_DIR}" ]; then
  echo "[INFO] Creating Python virtualenv in ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
fi

# Activate the virtualenv; all following python/pytest/ruff commands use it.
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m pip install pytest ruff

# ---------- 7. Run tests and lint checks ----------
python3 -m pytest -q
python3 -m ruff check .

# ---------- 8. Set up passwordless SSH access to each node ----------
python3 -m gputest.cli setup-ssh \
  --hostfile "${HOST_FILE}" \
  --user ubuntu \
  --private-key "${SSH_KEY}"