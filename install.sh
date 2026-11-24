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

if [[ ! -f "${SCRIPT_DIR}/requirements.txt" || ! -d "${SCRIPT_DIR}/gputest" ]]; then
  echo "[ERROR] Run install.sh from a cloned apacsce-gputest repository." >&2
  exit 1
fi
cd "${SCRIPT_DIR}"

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

echo "[INFO] Repository: ${SCRIPT_DIR}"
echo "[INFO] Detected OS: ${OS_PRETTY_NAME} (package manager: ${PKG_MGR})"

if [[ "${PKG_MGR}" == "apt-get" ]]; then
  sudo apt-get update
  sudo apt-get install -y "${VENV_PACKAGES[@]}"
else
  sudo "${PKG_MGR}" install -y "${VENV_PACKAGES[@]}"
fi

mkdir -p "${SSH_DIR}"
chmod 700 "${SSH_DIR}"
if [[ -f "${SSH_KEY}" ]]; then
  echo "[INFO] ${SSH_KEY} already exists; keeping it."
else
  echo "Paste the PEM private key for the test nodes, then press Ctrl+D:"
  cat > "${SSH_KEY}"
  chmod 400 "${SSH_KEY}"
  echo "[INFO] Private key saved to ${SSH_KEY}"
fi

echo "Paste the test nodes for ${HOST_FILE}, one node per line, then press Ctrl+D:"
cat > "${HOST_FILE}"
echo "[INFO] Saved host list to ${HOST_FILE}"

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

python3 -m gputest.cli setup-ssh \
  --hostfile "${HOST_FILE}" \
  --user ubuntu \
  --private-key "${SSH_KEY}"
