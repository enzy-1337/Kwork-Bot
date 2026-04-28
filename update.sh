#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/kwork"
REPO_URL="https://github.com/enzy-1337/Kwork-Bot.git"
ENV_FILE=".env"

get_env_value() {
  local key="$1"
  local file="$2"
  if [[ ! -f "${file}" ]]; then
    return
  fi
  awk -F= -v k="${key}" '$1 == k { print substr($0, index($0, "=") + 1); exit }' "${file}"
}

if [[ ! -d "${INSTALL_DIR}" ]]; then
  echo "[INFO] Создаю директорию ${INSTALL_DIR}..."
  sudo mkdir -p "${INSTALL_DIR}" 2>/dev/null || mkdir -p "${INSTALL_DIR}"
fi

cd "${INSTALL_DIR}"

if [[ ! -d ".git" ]]; then
  echo "[ERR] В ${INSTALL_DIR} нет git-репозитория."
  echo "[INFO] Используйте bootstrap.sh для первичной установки."
  exit 1
fi

echo "[INFO] Синхронизирую код с GitHub..."
git remote set-url origin "${REPO_URL}" || true
git fetch origin
git checkout -B main origin/main
git reset --hard origin/main
git clean -fd

echo "[INFO] Пересобираю и перезапускаю контейнеры..."
AI_PROVIDER="$(get_env_value "AI_PROVIDER" "${ENV_FILE}")"
AI_PROVIDER="${AI_PROVIDER:-ollama}"
if [[ "${AI_PROVIDER}" == "ollama" ]]; then
  docker compose --profile ollama up -d --build
else
  docker compose up -d --build db bot
fi

echo "[OK] Обновление завершено."
