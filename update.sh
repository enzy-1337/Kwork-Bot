#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/kwork"

if [[ ! -d "${INSTALL_DIR}" ]]; then
  echo "[INFO] Создаю директорию ${INSTALL_DIR}..."
  sudo mkdir -p "${INSTALL_DIR}" 2>/dev/null || mkdir -p "${INSTALL_DIR}"
fi

cd "${INSTALL_DIR}"

echo "[INFO] Обновляю код из Git..."
git pull --rebase

echo "[INFO] Пересобираю и перезапускаю контейнеры..."
docker compose up -d --build

echo "[OK] Обновление завершено."
