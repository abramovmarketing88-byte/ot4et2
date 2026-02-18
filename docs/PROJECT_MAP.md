# PROJECT MAP — Avito Analytics Telegram Bot

## 1) Project Overview

### Назначение продукта
`ot4et2` — это Telegram long-polling бот на `aiogram`, который позволяет владельцу Avito-аккаунтов подключать несколько профилей, получать аналитические отчёты по метрикам Avito (просмотры, контакты, расходы, баланс), настраивать расписание рассылки и выгружать Avito Messenger-чаты в Excel. Бот работает как фоновый worker-процесс, хранит состояние в БД (PostgreSQL/SQLite), использует APScheduler для периодических задач и Alembic для миграций.

### Основные пользовательские сценарии
1. Пользователь делает `/start` → создаётся запись `users`.
2. Пользователь добавляет Avito-профиль через `/add_profile` (name + client_id + client_secret) → бот валидирует креды и сохраняет `user_id` Avito.
3. Через `/profiles` пользователь открывает профиль и:
   - настраивает чат назначения отчётов,
   - настраивает время и частоту (daily / interval / weekly / monthly),
   - выбирает метрики отчёта,
   - запрашивает отчёт «сейчас» или исторический за период.
4. В группах/каналах команда `/stats` формирует сводный отчёт по всем профилям, привязанным к `chat_id`.
5. Для профиля можно сделать выгрузку чатов Avito Messenger в `.xlsx`.

### Основные роли/актеры
- **Пользователь Telegram** — настраивает профили и отчёты.
- **Администратор (опционально ADMIN_CHAT_ID)** — получает уведомления об ошибках токенов/интеграций.
- **Avito API** — OAuth, статистика, balance, messenger endpoints.
- **PostgreSQL/SQLite** — хранение профилей, задач отчётов, user mapping.
- **APScheduler** — orchestration и исполнение scheduled отчётов.

---

## 2) System Components (модули)

### Компонент: Worker / Bootstrap
- **Ответственность:** инициализация логирования, бота, диспетчера, middleware, lifecycle, retry/backoff и graceful shutdown.
- **Главные файлы:** `main.py`.
- **Входы:** ENV (`BOT_TOKEN`, retry/timeouts, `DATABASE_URL`), SIGTERM/SIGINT.
- **Выходы:** active polling loop, запуск/остановка scheduler, закрытие DB engine.

### Компонент: Telegram Handlers (UI/оркестрация сценариев)
- **Ответственность:** обработка команд и callback’ов (`/start`, `/profiles`, `/add_profile`, `/stats`, `/settings`, `/cancel`), FSM-сценарии, настройки профилей/отчётов.
- **Главные файлы:**
  - `bot/handlers/register.py`
  - `bot/handlers/profiles.py`
  - `bot/handlers/reports.py`
  - `bot/handlers/settings.py`
  - `bot/keyboards.py`, `bot/states.py`
- **Входы:** Telegram updates + DB session из middleware.
- **Выходы:** сообщения пользователю, изменения в БД, триггеры `sync_scheduler_tasks()`.

### Компонент: Middleware + Error Handling
- **Ответственность:** 1 async DB session на update; глобальная обработка ошибок и optional notify админу.
- **Главные файлы:** `bot/middleware.py`, `bot/errors.py`.
- **Входы:** aiogram event lifecycle, exceptions.
- **Выходы:** transactional commit/rollback, логирование, admin notifications.

### Компонент: Domain/Integrations — Avito
- **Ответственность:** OAuth2 client_credentials, вызовы Avito API, сбор метрик/баланса/чатов.
- **Главные файлы:** `core/avito/auth.py`, `core/avito/client.py`, `core/avito/messenger.py`.
- **Входы:** `client_id/client_secret`, `access_token`, `user_id`, даты/фильтры.
- **Выходы:** JSON-данные метрик и чатов; persisted token/user_id.

### Компонент: Reporting Engine
- **Ответственность:** формирование отчётов, агрегация по нескольким профилям, отправка в Telegram.
- **Главные файлы:** `core/report_runner.py`, `utils/analytics.py`, `utils/formatter.py`.
- **Входы:** `ReportTask`, `AvitoProfile`, выбранные метрики, период.
- **Выходы:** MarkdownV2 report messages, Excel-файл выгрузки чатов.

### Компонент: Scheduler
- **Ответственность:** маппинг DB-настроек расписания в APScheduler jobs, запуск отчётов по cron/interval, периодическая ресинхронизация.
- **Главные файлы:** `core/scheduler.py`.
- **Входы:** `ReportTask` + `AvitoProfile` из DB.
- **Выходы:** runtime jobs в `SQLAlchemyJobStore`, вызовы `run_report()`.

### Компонент: Data Access / Schema
- **Ответственность:** SQLAlchemy модели, async engine/session, инициализация таблиц, миграции.
- **Главные файлы:**
  - `core/database/models.py`
  - `core/database/session.py`
  - `alembic/env.py`
  - `alembic/versions/*.py`
- **Входы:** `DATABASE_URL`, schema metadata.
- **Выходы:** транзакции, таблицы, миграции.

---

## 3) Runtime & Deployment

### Локальный запуск
1. Поднять Postgres (например, `docker-compose up -d` из корня).
2. Установить зависимости: `pip install -r requirements.txt`.
3. Заполнить ENV (минимум `BOT_TOKEN`, `DATABASE_URL`).
4. Применить миграции: `alembic upgrade head`.
5. Запустить worker: `python main.py`.

Альтернатива: запуск через shell script `./start.sh` (выполняет `alembic upgrade head`, затем `python -u main.py`).

### Продовый запуск
- **Container entrypoint:** `Dockerfile` → `CMD ["./start.sh"]`.
- **Procfile:** `worker: ./start.sh`.
- **start.sh:** diagnostic + `alembic upgrade head` + `python -u main.py`.
- **Railway guidance:** описан в `DEPLOY_RAILWAY.md`; целевая модель — worker 24/7.

### Railway/infra: сервисы, переменные окружения, базы
- **Сервис приложения:** один worker-процесс (bot).
- **База:** PostgreSQL (рекомендуется), локально допустим SQLite fallback.
- **Переменные окружения (подтверждённые кодом):**
  - `BOT_TOKEN` (required),
  - `DATABASE_URL`,
  - `AVITO_CLIENT_ID`, `AVITO_CLIENT_SECRET`, `AVITO_REDIRECT_URI`,
  - `ADMIN_CHAT_ID`,
  - `WORKER_STARTUP_TIMEOUT_SEC`, `WORKER_STARTUP_RETRIES`, `WORKER_POLLING_RETRIES`, `WORKER_RETRY_BACKOFF_BASE_SEC`, `WORKER_RETRY_BACKOFF_MAX_SEC`.

### Команды запуска
- `python main.py`
- `./start.sh`
- `alembic upgrade head && python main.py` (как в документах деплоя)

### Health endpoints / ports
- HTTP health endpoint **не реализован** (бот не поднимает web-server).
- Порты приложения не публикуются; только исходящие соединения к Telegram/Avito/DB.

---

## 4) Data Layer

### СУБД и драйвер
- Runtime app: `SQLAlchemy AsyncSession` + `postgresql+asyncpg` (или SQLite async dialect).
- Alembic и APScheduler JobStore используют **sync URL** (удаляется `+asyncpg`/`+aiosqlite`).

### Основные таблицы/модели
1. `users`
   - PK: `telegram_id`.
   - Назначение: пользователь Telegram.

2. `avito_profiles`
   - PK: `id`, FK: `owner_id -> users.telegram_id`.
   - Бизнес-поля: `profile_name`, `client_id`, `client_secret`, `user_id`, `access_token`, `token_expires_at`.
   - Поля расписания: `report_frequency`, `report_interval_value`, `report_weekdays`, `report_time`, `report_timezone`, `is_report_active`.

3. `report_tasks`
   - PK: `id`, FK: `profile_id -> avito_profiles.id`.
   - Поля доставки/расписания: `chat_id`, `report_time`, `is_active`, `report_days`, `report_period`.
   - Поле конфигурации метрик: `report_metrics` (JSON-string).

### Миграции
- Миграции находятся в `alembic/versions`.
- Цепочка:
  - `20250206_sched` — `report_tasks.report_days/report_period`;
  - `20250206_profile_sched` — поля расписания в `avito_profiles`;
  - `20250206_flex` — no-op revision (документирование фичи).
- Применение: `alembic upgrade head`.

### Типичные запросы/связи
- Получение профилей пользователя: `AvitoProfile.owner_id == telegram_id`.
- Получение/создание `ReportTask` по `profile_id`.
- Для `/stats`: выбор всех `ReportTask` по `chat_id` + join `profile` через `selectinload`.
- Для scheduler: выбор активных задач с `chat_id != 0`, join `profile`, построение trigger по полям профиля.

---

## 5) API Surface (внутренний Telegram API-контракт)

> Здесь API = публичные Telegram команды и callback contract (`callback_data`), т.к. HTTP REST/OpenAPI нет.

### Команды
- `GET update /start` (Telegram command) — регистрация пользователя и приветствие.
- `/add_profile` — запуск FSM добавления профиля.
- `/profiles` — список профилей и вход в настройки.
- `/stats` — отчёт в текущий чат (если этот чат привязан в `ReportTask`).
- `/settings` — хинт на сценарий настройки через `/profiles`.
- `/cancel` — сброс текущего FSM сценария.

### Ключевые callback endpoints (по `callback_data`)
- `profile_view:{id}` — карточка профиля.
- `profile_report:{id}` — экран настроек отчёта.
- `report_now:{id}` — немедленный отчёт.
- `report_historical:{id}` — запуск historical FSM.
- `report_characteristics:{id}` / `report_toggle:{id}:{metric}` / `report_metrics_all:{id}` — выбор метрик.
- `report_set_chat:{id}` / `report_chat_here:{id}` / `report_chat_forward:{id}` — назначение `chat_id`.
- `report_set_time:{id}` — установка времени.
- `report_frequency:{id}` / `freq_set:{id}:{daily|interval|weekly|monthly}` / `report_day_toggle:{id}:{0..6}` — настройка частоты.
- `export_messenger:{id}` — выгрузка чатов/сообщений в Excel.

### Что критично для навигации UI
- `/profiles` как основной хаб.
- `profile_view` → `profile_report` → (`set_chat`, `set_time`, `frequency`, `characteristics`).
- `/stats` как операционный trigger отчёта в групповых чатах.

### Авторизация/сессии/токены
- Telegram auth опирается на `from_user.id` + ownership checks в запросах.
- Avito auth: OAuth2 client_credentials, токены хранятся в `avito_profiles.access_token/token_expires_at`, обновляются по сроку.
- DB session scope: один update = одна сессия через middleware.

---

## 6) Data Flow Diagrams (ASCII)

### 6.1 Request flow: Telegram UI -> Bot -> DB

```text
[Telegram User]
    |
    | command/callback
    v
[aiogram Dispatcher]
    |
    | DbSessionMiddleware (session per update)
    v
[Handler]
    |
    +--> read/write SQLAlchemy models (users/avito_profiles/report_tasks)
    |
    +--> call report_runner / scheduler sync
    v
[Telegram response message]
```

### 6.2 Auth flow (Avito OAuth)

```text
[Handler or Scheduler]
    |
    v
[AvitoAuth.ensure_token]
    |
    +-- token missing/expired? -- yes --> POST /token (client_credentials)
    |                                  --> save access_token + token_expires_at (UTC)
    |                                  --> optional GET /core/v1/accounts/self -> save user_id
    |
    +-- no --> reuse access_token
    v
[AvitoClient API calls]
```

### 6.3 Scheduled reporting flow

```text
[start_scheduler(bot)]
    |
    +--> set_report_bot(bot)
    +--> AsyncIOScheduler.start()
    +--> sync_scheduler_tasks() reads DB
             |
             +--> create job per active ReportTask
                     (Cron: daily/weekly/monthly fallback | Interval: every N days)

[job fire]
    -> run_scheduled_report(task_id)
       -> load task+profile
       -> run_report(bot, task, profile)
       -> send Telegram message
```

### 6.4 /stats combined report flow

```text
[/stats in group/channel]
    -> query ReportTask by chat_id
    -> collect related profiles
    -> run_combined_report_to_chat(...)
        -> for each profile: ensure_token + fetch_all_metrics
        -> aggregate metrics
        -> send one combined report message
```

### 6.5 Messenger export flow

```text
[callback export_messenger:{profile_id}]
    -> ensure Avito token
    -> GET /messenger/.../chats
    -> for each chat: GET /messages
    -> normalize rows
    -> pandas -> xlsx buffer
    -> send_document to Telegram
```

### 6.6 Historical report flow

```text
[callback report_historical]
    -> FSM waiting_start_date -> waiting_end_date
    -> validate YYYY-MM-DD and range
    -> choose destination chat (task.chat_id or current chat)
    -> run_report_to_chat(start_date, end_date)
```

---

## 7) Observability

### Логи
- Инициализация логирования сделана в `main.py` (stream = stdout, level=DEBUG).
- В `alembic/env.py` логгер Alembic принудительно переведён на stdout (важно для Railway).
- Логи есть в ключевых местах:
  - startup/shutdown worker;
  - scheduler sync и ошибки джобов;
  - исключения Avito API / отправки сообщений;
  - глобальный error handler update-level.

### Метрики/трейсинг
- Технические метрики (Prometheus/OpenTelemetry) **не реализованы**.
- Косвенные бизнес-метрики формируются в отчётах пользователю (views/contacts/spending/etc.).

### Частые ошибки и где ловить
- Обработчик update-level: `bot/errors.py::global_error_handler`.
- Ошибки Avito токена/статистики: `core/report_runner.py` + `core/avito/auth.py`.
- Ошибки джобов: `core/scheduler.py::run_scheduled_report/sync_scheduler_tasks`.
- Ошибки миграций/подключения БД: startup (`start.sh`, `main.py`, `core/database/session.py`, `alembic/env.py`).

---

## 8) Failure Modes & Safeguards

1. **Нет `BOT_TOKEN` / битый env** → приложение падает на инициализации `Settings`.
   - Safeguard: явный exception + debug print в stderr.

2. **Неверный `DATABASE_URL` или БД недоступна** → падение миграций/сессий.
   - Safeguard: retry-loop только для worker phase; миграции остаются hard-fail.

3. **Конфликт async/sync драйверов для Alembic/JobStore**.
   - Safeguard: явное преобразование URL в sync variant в `alembic/env.py` и `core/scheduler.py`.

4. **Просроченные/невалидные Avito credentials** → ошибки `ensure_token()` / 401.
   - Safeguard: admin notify (`ADMIN_CHAT_ID`) + user-facing error message.

5. **`user_id` профиля не сохранён** → отчёты не формируются.
   - Safeguard: проверка `profile.user_id` с понятным сообщением пользователю.

6. **`chat_id` не установлен у ReportTask** → scheduled/on-demand отчёт может уйти не туда или не уйти.
   - Safeguard: fallback to current chat для `report_now`, явные подсказки в UI.

7. **Схема БД рассинхронизирована с кодом (`report_metrics` и др.)**.
   - Safeguard: `init_db()` пытается добавить `report_metrics` через ALTER TABLE fallback.
   - Риск: bypass Alembic может привести к скрытым несовместимостям в будущем.

8. **Telegram parse errors (MarkdownV2 escaping)**.
   - Safeguard: форматтер использует escaping helper.

9. **Сбой внешнего API Avito / rate limiting / partial data**.
   - Safeguard: обработка исключений, fallback на item stats при нулевых totals, частичные сводки.

10. **Scheduler drift / stale jobs при смене настроек**.
   - Safeguard: `sync_scheduler_tasks()` вызывается после изменений и периодически каждые 15 минут.

### Места, чувствительные к миграциям/совместимости
- `ReportTask.report_metrics/report_days/report_period`.
- `AvitoProfile.report_frequency/report_interval_value/report_weekdays/report_time/report_timezone/is_report_active`.
- Логика handlers/scheduler жёстко завязана на эти поля.

---

## 9) Productization Plan (вынос в отдельный продукт/модуль)

### 9.1 Что является ядром
- Domain ядро:
  - `AvitoAuth`, `AvitoClient` abstraction,
  - вычисление/агрегация метрик,
  - scheduling policy (daily/weekly/interval/monthly),
  - report formatting.
- Platform ядро:
  - storage models + migrations,
  - worker lifecycle/backoff,
  - delivery adapters (Telegram now, потенциально email/webhook позже).

### 9.2 Какие зависимости абстрагировать
1. **Transport layer (Telegram)** → выделить интерфейс `ReportDeliveryPort`.
2. **Avito API** → `AvitoGatewayPort` (token, stats, messenger).
3. **Scheduler engine** → `ScheduleEnginePort` (register/update/remove jobs).
4. **Persistence** → repository слой (`UserRepo`, `ProfileRepo`, `ReportTaskRepo`).

### 9.3 Какие интерфейсы выделить (ports/adapters)
- `AuthServicePort`: `ensure_token(profile)`.
- `MetricsServicePort`: `fetch_metrics(profile, period)`.
- `ReportServicePort`: `build_report(metrics, selected_fields)`.
- `DeliveryPort`: `send_text(chat_id, text)`, `send_file(chat_id, bytes, filename)`.
- `SchedulePort`: `sync(tasks)` / `run(task_id)`.

### 9.4 Минимальный starter kit для нового проекта

```text
new_product/
  app/
    entrypoints/
      worker.py              # lifecycle, polling/webhook bootstrap
    domain/
      entities.py            # User/Profile/Task domain models
      services/
        auth_service.py
        metrics_service.py
        report_service.py
        schedule_service.py
      ports/
        avito_port.py
        delivery_port.py
        scheduler_port.py
        repository_port.py
    adapters/
      telegram/
      avito/
      scheduler_aps/
      storage_sqlalchemy/
    config/
      settings.py
    observability/
      logging.py
      tracing.py (optional)
  migrations/
  tests/
  docker/
    Dockerfile
    docker-compose.yml
  docs/
    PROJECT_MAP.md
    ADR/
```

### 9.5 Пошаговый план выноса
1. Зафиксировать текущий контракт callbacks/commands как продуктовый API.
2. Вынести `core/avito/*` и `core/report_runner.py` в отдельный package `analytics_core`.
3. Вынести `core/scheduler.py` в adapter слой с интерфейсом schedule-port.
4. Добавить repository abstraction поверх SQLAlchemy моделей.
5. Покрыть domain-сервисы unit-тестами без Telegram runtime.
6. Подготовить второй delivery adapter (например, HTTP webhook/email) для проверки модульности.

---

## Repository Scan (контрольный список шага A)

- **Entrypoint:** `main.py`.
- **Конфиги/деплой:** `Dockerfile`, `Procfile`, `start.sh`, `run.sh`, `docker-compose.yml`, `DEPLOY_RAILWAY.md`.
- **DB/ORM:** `core/database/models.py`, `core/database/session.py`.
- **Миграции:** `alembic/env.py`, `alembic/versions/*.py`, `alembic.ini`.
- **API-контракт (Telegram):** `bot/handlers/*.py`, `bot/keyboards.py`, `bot/states.py`.
- **Интеграции:** Avito OAuth/Stats/Messenger (`core/avito/*`).
- **Фоновые задачи:** APScheduler (`core/scheduler.py`) + periodic sync.
- **Тесты:** автоматических тестов в репозитории не найдено (`tests/` отсутствует).
- **CI:** файлов `.github/workflows` и иных CI-конфигов не найдено.

---

## ASSUMPTION / Verification Notes

1. **ASSUMPTION:** В проде используется Railway с отдельным PostgreSQL-сервисом и worker-процессом 24/7.
   - Подтверждать по: `DEPLOY_RAILWAY.md`, Railway project settings.

2. **ASSUMPTION:** `AVITO_REDIRECT_URI` пока не используется в активных сценариях кода.
   - Подтверждать по: `core/config.py` и отсутствие обращений к полю через `rg "AVITO_REDIRECT_URI"`.

3. **ASSUMPTION:** Поле `report_period` (day/week/month) подготовлено под будущую логику, но в scheduler на cron-триггеры влияет в ограниченной степени.
   - Подтверждать по: `core/scheduler.py`, `bot/keyboards.py` (`report_period_kb`) и `bot/handlers/*`.
