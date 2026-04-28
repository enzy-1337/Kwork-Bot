#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="kwork-monitor-bot"
ENV_FILE=".env"
INSTALL_DIR="/opt/kwork"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

print_info() { echo -e "\033[1;34m[INFO]\033[0m $1"; }
print_warn() { echo -e "\033[1;33m[WARN]\033[0m $1"; }
print_ok() { echo -e "\033[1;32m[OK]\033[0m $1"; }
print_err() { echo -e "\033[1;31m[ERR]\033[0m $1"; }

require_root_or_sudo() {
  if [[ "${EUID}" -ne 0 ]] && ! command -v sudo >/dev/null 2>&1; then
    print_err "Нужны root-права или sudo."
    exit 1
  fi
}

run_as_root() {
  if [[ "${EUID}" -eq 0 ]]; then
    bash -c "$1"
  else
    sudo bash -c "$1"
  fi
}

check_debian() {
  if [[ ! -f /etc/os-release ]]; then
    print_warn "Не удалось определить ОС. Продолжаем."
    return
  fi
  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ "${ID:-}" != "debian" ]]; then
    print_warn "Скрипт оптимизирован под Debian 12/13, у вас: ${PRETTY_NAME:-unknown}."
  else
    print_ok "Обнаружена ОС: ${PRETTY_NAME:-Debian}."
  fi
}

install_packages() {
  print_info "Обновляю apt и устанавливаю базовые зависимости..."
  run_as_root "apt-get update -y"
  run_as_root "apt-get install -y ca-certificates curl gnupg lsb-release git rsync"
}

install_docker_if_needed() {
  if command -v docker >/dev/null 2>&1; then
    print_ok "Docker уже установлен."
    return
  fi

  print_info "Docker не найден. Устанавливаю Docker Engine..."
  run_as_root "install -m 0755 -d /etc/apt/keyrings"
  run_as_root "curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc"
  run_as_root "chmod a+r /etc/apt/keyrings/docker.asc"
  run_as_root "echo \
    \"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
    https://download.docker.com/linux/debian $(. /etc/os-release && echo \$VERSION_CODENAME) stable\" \
    > /etc/apt/sources.list.d/docker.list"
  run_as_root "apt-get update -y"
  run_as_root "apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
  print_ok "Docker установлен."
}

ensure_docker_running() {
  print_info "Проверяю сервис Docker..."
  run_as_root "systemctl enable docker"
  run_as_root "systemctl start docker"
}

sync_project_to_opt() {
  print_info "Синхронизирую проект в ${INSTALL_DIR}..."
  run_as_root "mkdir -p '${INSTALL_DIR}'"
  run_as_root "rsync -a --delete \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude '.env' \
    '${SOURCE_DIR}/' '${INSTALL_DIR}/'"
  cd "${INSTALL_DIR}"
  print_ok "Проект размещен в ${INSTALL_DIR}."
}

ask_required() {
  local prompt="$1"
  local var_name="$2"
  local value=""
  while [[ -z "${value}" ]]; do
    read -r -p "${prompt}: " value
  done
  printf -v "${var_name}" "%s" "${value}"
}

ask_default() {
  local prompt="$1"
  local default="$2"
  local var_name="$3"
  local value=""
  read -r -p "${prompt} [${default}]: " value
  value="${value:-$default}"
  printf -v "${var_name}" "%s" "${value}"
}

create_env_file() {
  print_info "Настройка .env (интерактивно)"
  ask_required "Введите BOT_TOKEN Telegram-бота" BOT_TOKEN
  ask_required "Введите OWNER_TELEGRAM_ID" OWNER_TELEGRAM_ID

  ask_default "Введите имя БД PostgreSQL" "kwork_bot" POSTGRES_DB
  ask_default "Введите пользователя БД" "kwork" POSTGRES_USER
  ask_default "Введите пароль БД" "kwork" POSTGRES_PASSWORD
  ask_default "Интервал парсинга (сек)" "45" PARSE_INTERVAL_SECONDS
  ask_default "URL Kwork раздела IT" "https://kwork.ru/projects?category=it" KWORK_PROJECTS_URL
  ask_default "AI провайдер (ollama|hf|gemini)" "ollama" AI_PROVIDER
  ask_default "Ollama модель" "qwen2.5:7b" OLLAMA_MODEL
  ask_default "Уровень логирования" "INFO" LOG_LEVEL

  DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}"

  cat > "${ENV_FILE}" <<EOF
BOT_TOKEN=${BOT_TOKEN}
OWNER_TELEGRAM_ID=${OWNER_TELEGRAM_ID}

DATABASE_URL=${DATABASE_URL}

KWORK_PROJECTS_URL=${KWORK_PROJECTS_URL}
PARSE_INTERVAL_SECONDS=${PARSE_INTERVAL_SECONDS}
REQUEST_TIMEOUT_SECONDS=20
LOG_LEVEL=${LOG_LEVEL}

AI_PROVIDER=${AI_PROVIDER}
OLLAMA_URL=http://ollama:11434/api/generate
OLLAMA_MODEL=${OLLAMA_MODEL}

GEMINI_API_KEY=
HF_API_TOKEN=
HF_MODEL=HuggingFaceH4/zephyr-7b-beta
EOF

  print_ok "Файл ${ENV_FILE} создан."
}

start_stack() {
  print_info "Собираю и запускаю контейнеры..."
  docker compose up -d --build
  print_ok "Контейнеры запущены."
}

optional_ollama_pull() {
  if [[ "${AI_PROVIDER}" != "ollama" ]]; then
    return
  fi
  print_info "Проверяем загрузку модели Ollama (${OLLAMA_MODEL})..."
  print_warn "Первая загрузка модели может занять несколько минут."
  docker compose exec -T ollama ollama pull "${OLLAMA_MODEL}" || print_warn "Не удалось автоматически подтянуть модель. Выполните вручную позже."
}

print_final_notes() {
  cat <<EOF

Готово.
Рабочая директория: ${INSTALL_DIR}
Полезные команды:
  cd ${INSTALL_DIR}
  docker compose ps
  docker compose logs -f bot
  docker compose restart bot
  docker compose pull && docker compose up -d

Для GitHub:
  cd ${INSTALL_DIR}
  git init
  git add .
  git commit -m "Initial production-ready MVP"
  git remote add origin <ваш_repo_url>
  git push -u origin main
EOF
}

main() {
  print_info "Запуск установщика ${PROJECT_NAME}"
  require_root_or_sudo
  check_debian
  install_packages
  install_docker_if_needed
  ensure_docker_running
  sync_project_to_opt
  create_env_file
  start_stack
  optional_ollama_pull
  print_final_notes
}

main "$@"
