#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/enzy-1337/Kwork-Bot.git"
INSTALL_DIR="/opt/kwork"

info() { echo -e "\033[1;34m[INFO]\033[0m $1"; }
ok() { echo -e "\033[1;32m[OK]\033[0m $1"; }
err() { echo -e "\033[1;31m[ERR]\033[0m $1"; }

run_as_root() {
  if [[ "${EUID}" -eq 0 ]]; then
    bash -c "$1"
  else
    sudo bash -c "$1"
  fi
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

ensure_base_tools() {
  if need_cmd git && need_cmd curl; then
    return
  fi
  info "Устанавливаю базовые утилиты (git, curl)..."
  run_as_root "apt-get update -y"
  run_as_root "apt-get install -y git curl ca-certificates"
}

clone_or_update_repo() {
  info "Подготавливаю директорию ${INSTALL_DIR}..."
  run_as_root "mkdir -p '${INSTALL_DIR}'"

  if [[ -d "${INSTALL_DIR}/.git" ]]; then
    info "Репозиторий уже существует, синхронизирую с origin/main..."
    git -C "${INSTALL_DIR}" remote set-url origin "${REPO_URL}" || true
    git -C "${INSTALL_DIR}" fetch --all --prune
    git -C "${INSTALL_DIR}" checkout -B main origin/main
    # В установочной директории не держим локальные правки: берем чистое состояние из GitHub.
    git -C "${INSTALL_DIR}" reset --hard origin/main
    git -C "${INSTALL_DIR}" clean -fd
  else
    info "Клонирую репозиторий ${REPO_URL}..."
    run_as_root "rm -rf '${INSTALL_DIR}'/* '${INSTALL_DIR}'/.[!.]* '${INSTALL_DIR}'/..?* 2>/dev/null || true"
    git clone "${REPO_URL}" "${INSTALL_DIR}"
  fi

  ok "Исходники готовы в ${INSTALL_DIR}."
}

run_installer() {
  cd "${INSTALL_DIR}"
  chmod +x bootstrap.sh install.sh update.sh
  info "Запускаю основной установщик..."
  ./install.sh
}

main() {
  ensure_base_tools
  clone_or_update_repo
  run_installer
}

main "$@"
