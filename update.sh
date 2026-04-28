#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/kwork"
cd "${INSTALL_DIR}"

echo "[INFO] Обновляю код из Git..."
git pull --rebase

echo "[INFO] Пересобираю и перезапускаю контейнеры..."
docker compose up -d --build

echo "[OK] Обновление завершено."
