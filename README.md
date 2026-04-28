# Kwork IT Monitor Bot (aiogram 3.x)

Production-oriented MVP Telegram-бота для мониторинга новых заказов в IT-разделе Kwork без официального API.

## Возможности

- Асинхронный парсинг Kwork каждые 30-60 секунд.
- Антидубликаты: in-memory TTL cache + проверка в PostgreSQL.
- Фильтрация по бюджету, категориям, keywords, blacklist, срочности.
- Оценка заказа: интересность, вероятность получения, сложность, сроки, рекомендованная цена.
- Генерация уникального отклика через AI (Ollama в MVP).
- Telegram admin-панель и inline-кнопки.
- Доступ только владельцу (`OWNER_TELEGRAM_ID`), остальные игнорируются.
- Docker + docker-compose.

## Структура

```text
bot/
core/
parsers/
services/
database/
handlers/
keyboards/
middlewares/
utils/
config/
```

## Быстрый старт (локально)

1. Скопируйте `.env.example` в `.env`.
2. Укажите `BOT_TOKEN`, `OWNER_TELEGRAM_ID`, `DATABASE_URL`.
3. Установите зависимости:
   - `pip install -r requirements.txt`
4. Запуск:
   - `python main.py`

## Запуск в Docker

1. `cp .env.example .env`
2. Заполните переменные в `.env`
3. `docker compose up -d --build`
4. Если нужен локальный Ollama, запускайте с профилем:
   - `docker compose --profile ollama up -d --build`

## Telegram только через прокси

- Реализация как в `c:/remna`: контейнер `bot` запускается через `proxychains4` (`scripts/bot-entrypoint.sh`).
- Это проксирует весь исходящий TCP-трафик бота через SOCKS5 на хосте.
- В `.env`:
  - `BOT_PROXYCHAINS_ENABLED=true`
  - `PROXYCHAINS_SOCKS5_HOST=host.docker.internal`
  - `PROXYCHAINS_SOCKS5_PORT=1080`
  - `PROXYCHAINS_PROXY_DNS=false` (обычно так безопаснее для Docker DNS).
- В `docker-compose.yml` добавлен `host.docker.internal:host-gateway`.
- Дополнительный режим `TELEGRAM_PROXY_URL` (aiogram session proxy) оставлен опционально, но при `BOT_PROXYCHAINS_ENABLED=true` обычно не нужен.

## Установка одной командой (Debian 12/13)

Запуск прямо с сервера одной командой (`curl + bash`):

- `bash <(curl -fsSL https://raw.githubusercontent.com/enzy-1337/Kwork-Bot/main/bootstrap.sh)`

Что делает `bootstrap.sh`:
- создает `/opt/kwork`;
- клонирует/обновляет репозиторий в `/opt/kwork`;
- запускает `install.sh`, который устанавливает Docker/Compose, спрашивает `.env` и поднимает сервисы.

Локальный запуск (если вы уже в репозитории):

1. Дайте права на запуск:
   - `chmod +x bootstrap.sh install.sh update.sh`
2. Запустите установщик:
   - `./install.sh`
3. Скрипт:
   - установит проект в `/opt/kwork`;
   - установит Docker/Compose и `git` (если их нет);
   - запросит данные и создаст `.env`;
  - поднимет контейнеры (`db`, `bot`);
  - при `AI_PROVIDER=ollama` поднимет также `ollama` и попробует подтянуть модель.

## Обновление после заливки в GitHub

- Для будущих обновлений:
  - `cd /opt/kwork && ./update.sh`
- Скрипт сделает `git pull --rebase` и перезапустит контейнеры с пересборкой.

## Telegram команды

- `/start`
- `/panel`
- `/stats`
- `/settings`
- `/categories`
- `/keywords`
- `/blacklist`

## Как работает мониторинг

1. Фоновый сервис тянет страницу проектов Kwork.
2. Выделяет новые заказы и автоматически оставляет IT-релевантные (в т.ч. `Разработка и IT`, боты, скрипты, веб-разработка, AI, автоматизация).
3. Пропускает уже обработанные.
4. Применяет фильтры владельца.
5. Сохраняет подходящие заказы в БД.
6. Отправляет карточку заказа владельцу в Telegram.

## Важные заметки по MVP

- Верстка Kwork может меняться, поэтому CSS-селекторы в `parsers/kwork_parser.py` нужно периодически обновлять.
- Для AI-провайдера `hf`/`gemini` добавьте соответствующие адаптеры в `services/ai_service.py`.
- Для продакшена рекомендуется добавить Alembic миграции, healthcheck, метрики и прокси для устойчивого парсинга.
- Файл `.env` уже исключен из Git через `.gitignore`, это безопасно для публикации репозитория.
