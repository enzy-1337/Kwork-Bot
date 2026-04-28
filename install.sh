#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="kwork-monitor-bot"
ENV_FILE=".env"
INSTALL_DIR="/opt/kwork"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NON_INTERACTIVE="${NON_INTERACTIVE:-false}"
AUTO_MIGRATE_DOCKER_ROOT="${AUTO_MIGRATE_DOCKER_ROOT:-false}"
FORCE_OLLAMA="${FORCE_OLLAMA:-false}"

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

get_free_gb_for_path() {
  local path="$1"
  df -BG --output=avail "${path}" | awk 'NR==2 { gsub(/[^0-9]/, "", $1); print $1 }'
}

migrate_docker_root_to_srv() {
  local target_dir="/srv/docker"
  print_info "Перенос Docker data-root в ${target_dir}..."
  run_as_root "systemctl stop docker"
  run_as_root "mkdir -p '${target_dir}'"
  run_as_root "rsync -a /var/lib/docker/ '${target_dir}/'"
  run_as_root "mkdir -p /etc/docker"
  run_as_root "cat > /etc/docker/daemon.json <<'EOF'
{
  \"data-root\": \"${target_dir}\"
}
EOF"
  run_as_root "systemctl daemon-reload"
  run_as_root "systemctl start docker"
  print_ok "Docker data-root перенесен в ${target_dir}."
}

check_and_offer_docker_root_migration() {
  local root_dir free_gb min_gb=10
  root_dir="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)"
  if [[ -z "${root_dir}" ]]; then
    print_warn "Не удалось определить Docker Root Dir. Пропускаю проверку диска."
    return
  fi

  free_gb="$(get_free_gb_for_path "${root_dir}")"
  free_gb="${free_gb:-0}"
  print_info "Docker Root Dir: ${root_dir} (свободно: ${free_gb}G)"

  if [[ "${root_dir}" == "/srv/docker" ]]; then
    return
  fi

  if (( free_gb < min_gb )); then
    print_warn "Свободного места для Docker мало (< ${min_gb}G)."
    if [[ "${AUTO_MIGRATE_DOCKER_ROOT}" == "true" || "${AUTO_MIGRATE_DOCKER_ROOT}" == "1" ]]; then
      migrate_docker_root_to_srv
    elif ask_yes_no_default_no "Перенести Docker data-root в /srv/docker сейчас?"; then
      migrate_docker_root_to_srv
    else
      print_warn "Перенос пропущен. Возможны ошибки 'no space left on device' при pull/build."
    fi
  fi
}

ensure_install_dir() {
  print_info "Создаю директорию ${INSTALL_DIR}..."
  run_as_root "mkdir -p '${INSTALL_DIR}'"
  print_ok "Директория ${INSTALL_DIR} готова."
}

sync_project_to_opt() {
  local source_real install_real
  source_real="$(readlink -f "${SOURCE_DIR}")"
  install_real="$(readlink -f "${INSTALL_DIR}")"

  if [[ "${source_real}" == "${install_real}" ]]; then
    print_info "Исходники уже находятся в ${INSTALL_DIR}, синхронизация не требуется."
    cd "${INSTALL_DIR}"
    return
  fi

  print_info "Синхронизирую проект в ${INSTALL_DIR}..."
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

ask_yes_no_default_no() {
  local prompt="$1"
  if [[ "${NON_INTERACTIVE}" == "true" || "${NON_INTERACTIVE}" == "1" ]]; then
    return 1
  fi
  local answer=""
  read -r -p "${prompt} [y/N]: " answer
  case "${answer}" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

get_env_value() {
  local key="$1"
  local file="$2"
  if [[ ! -f "${file}" ]]; then
    return
  fi
  awk -F= -v k="${key}" '$1 == k { print substr($0, index($0, "=") + 1); exit }' "${file}"
}

create_env_file() {
  if [[ -f "${ENV_FILE}" ]]; then
    print_warn "Файл ${ENV_FILE} уже существует в ${INSTALL_DIR}."
    if [[ "${NON_INTERACTIVE}" == "true" || "${NON_INTERACTIVE}" == "1" ]]; then
      print_info "NON_INTERACTIVE=true: использую существующий ${ENV_FILE}."
      return
    fi
    if ! ask_yes_no_default_no "Хотите пересоздать ${ENV_FILE}?"; then
      print_info "Использую существующий ${ENV_FILE}."
      return
    fi
  fi

  print_info "Настройка .env (интерактивно)"
  ask_required "Введите BOT_TOKEN Telegram-бота" BOT_TOKEN
  ask_required "Введите OWNER_TELEGRAM_ID" OWNER_TELEGRAM_ID

  ask_default "Введите имя БД PostgreSQL" "kwork_bot" POSTGRES_DB
  ask_default "Введите пользователя БД" "kwork" POSTGRES_USER
  ask_default "Введите пароль БД" "kwork" POSTGRES_PASSWORD
  ask_default "Интервал парсинга (сек)" "45" PARSE_INTERVAL_SECONDS
  ask_default "URL Kwork проектов" "https://kwork.ru/projects" KWORK_PROJECTS_URL
  ask_default "Включить proxychains для всего трафика бота? (true|false)" "true" BOT_PROXYCHAINS_ENABLED
  ask_default "PROXYCHAINS SOCKS5 host" "host.docker.internal" PROXYCHAINS_SOCKS5_HOST
  ask_default "PROXYCHAINS SOCKS5 port" "1080" PROXYCHAINS_SOCKS5_PORT
  ask_default "Пускать DNS через proxychains? (true|false)" "false" PROXYCHAINS_PROXY_DNS
  ask_default "Требовать aiogram proxy обязательно? (true|false)" "false" TELEGRAM_PROXY_REQUIRED
  ask_default "URL прокси для aiogram (если нужен), иначе пусто" "" TELEGRAM_PROXY_URL
  ask_default "ID forum-группы Telegram (chat_id вида -100..., пусто для ЛС)" "-1003906969456" TELEGRAM_FORUM_CHAT_ID
  ask_default "Автосоздание топиков при старте? (true|false)" "true" FORUM_AUTO_CREATE_TOPICS
  ask_default "Максимальная длина названия топика" "120" FORUM_TOPIC_TITLE_MAX_LENGTH
  ask_default "Название Ollama-топика" "Ollama" OLLAMA_TOPIC_NAME
  ask_default "Cookie для авторизации на Kwork (для кнопки отклика), можно оставить пустым" "" KWORK_COOKIE
  ask_default "AI провайдер (ollama|hf|gemini)" "ollama" AI_PROVIDER
  ask_default "Ollama модель" "qwen2.5:3b" OLLAMA_MODEL
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
BOT_PROXYCHAINS_ENABLED=${BOT_PROXYCHAINS_ENABLED}
PROXYCHAINS_SOCKS5_HOST=${PROXYCHAINS_SOCKS5_HOST}
PROXYCHAINS_SOCKS5_PORT=${PROXYCHAINS_SOCKS5_PORT}
PROXYCHAINS_PROXY_DNS=${PROXYCHAINS_PROXY_DNS}
TELEGRAM_PROXY_REQUIRED=${TELEGRAM_PROXY_REQUIRED}
TELEGRAM_PROXY_URL=${TELEGRAM_PROXY_URL}
TELEGRAM_FORUM_CHAT_ID=${TELEGRAM_FORUM_CHAT_ID}
FORUM_AUTO_CREATE_TOPICS=${FORUM_AUTO_CREATE_TOPICS}
FORUM_TOPIC_TITLE_MAX_LENGTH=${FORUM_TOPIC_TITLE_MAX_LENGTH}
OLLAMA_TOPIC_NAME=${OLLAMA_TOPIC_NAME}
KWORK_COOKIE=${KWORK_COOKIE}

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
  local ai_provider="${AI_PROVIDER:-}"
  if [[ -z "${ai_provider}" ]]; then
    ai_provider="$(get_env_value "AI_PROVIDER" "${ENV_FILE}")"
  fi
  ai_provider="${ai_provider:-ollama}"
  if [[ "${FORCE_OLLAMA}" == "true" || "${FORCE_OLLAMA}" == "1" ]]; then
    ai_provider="ollama"
  fi

  print_info "Собираю и запускаю контейнеры..."
  if [[ "${ai_provider}" == "ollama" ]]; then
    docker compose --profile ollama up -d --build
  else
    docker compose up -d --build db bot
  fi
  print_ok "Контейнеры запущены."
}

optional_ollama_pull() {
  local ai_provider="${AI_PROVIDER:-}"
  local ollama_model="${OLLAMA_MODEL:-}"
  if [[ -z "${ai_provider}" ]]; then
    ai_provider="$(get_env_value "AI_PROVIDER" "${ENV_FILE}")"
  fi
  if [[ -z "${ollama_model}" ]]; then
    ollama_model="$(get_env_value "OLLAMA_MODEL" "${ENV_FILE}")"
  fi
  ollama_model="${ollama_model:-qwen2.5:3b}"

  if [[ "${ai_provider}" != "ollama" ]]; then
    return
  fi
  print_info "Проверяем загрузку модели Ollama (${ollama_model})..."
  print_warn "Первая загрузка модели может занять несколько минут."
  docker compose exec -T ollama ollama pull "${ollama_model}" || print_warn "Не удалось автоматически подтянуть модель. Выполните вручную позже."
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
  check_and_offer_docker_root_migration
  ensure_install_dir
  sync_project_to_opt
  create_env_file
  start_stack
  optional_ollama_pull
  print_final_notes
}

main "$@"
