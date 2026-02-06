# Project structure (Railway-friendly)

This document describes the expected layout so that the app runs correctly (locally and on Railway).

## Required layout

```
<project_root>/          ← Run "python main.py" and "alembic" from here (Railway: set Root Directory to this folder)
├── main.py              ← Entry point
├── alembic.ini          ← script_location = alembic
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── bot/
│   ├── handlers/        ← All Telegram handlers (register, profiles, reports)
│   │   ├── __init__.py
│   │   ├── register.py
│   │   ├── profiles.py
│   │   └── reports.py
│   ├── errors.py
│   ├── keyboards.py
│   ├── middleware.py
│   └── states.py
├── core/
│   ├── avito/           ← Avito API only
│   │   ├── auth.py
│   │   └── client.py
│   ├── database/        ← DB models and session only
│   │   ├── models.py
│   │   └── session.py
│   ├── config.py
│   ├── report_runner.py
│   ├── scheduler.py
│   └── timezone.py
├── utils/
│   ├── analytics.py
│   └── formatter.py
├── requirements.txt
└── Dockerfile
```

## Checklist

1. **Handlers** — All in `bot/handlers/`: `register.py`, `profiles.py`, `reports.py`.
2. **Database** — Models and session in `core/database/`: `models.py`, `session.py`.
3. **Avito API** — In `core/avito/`: `auth.py`, `client.py`.
4. **Alembic** — Folder `alembic/` exists; `alembic.ini` has `script_location = alembic`.
5. **main.py** imports:
   - `bot.errors`, `bot.handlers.*`, `bot.middleware`
   - `core.database.session`, `core.scheduler`
   - `core.config` (inside `main()`)

## Railway

- Set **Root Directory** to the folder that contains `main.py`, `bot/`, `core/`, and `alembic/`.  
  If the repo is `prodjekt_parser_tg` and the bot lives in `avito_analytics_bot/`, set Root Directory to **`avito_analytics_bot`**.
- The Dockerfile `COPY . .` expects the build context to be this same root (so build from that root).

## Extended layout (schedule & messages)

Дополнительные модули и изменения для расписания, периодов и сбора сообщений:

```
├── core/
│   ├── database/
│   │   └── models.py        <- Добавляем настройки расписания
│   ├── avito/
│   │   └── messenger.py     <- НОВЫЙ: Логика сбора сообщений
│   ├── scheduler.py         <- Расширяем для динамических задач
│   └── report_runner.py     <- Добавляем поддержку периодов
├── bot/
│   ├── handlers/
│   │   └── settings.py      <- НОВЫЙ: Настройка времени и частоты
│   ├── keyboards.py         <- Инлайновые меню для выбора дат/дней
│   └── states.py            <- Состояния для ввода интервалов
└── utils/
    └── formatter.py         <- Логика формирования Excel
```

## Architecture flow (diagram)

```mermaid
flowchart TD
    A[Container start] --> B[alembic upgrade head]
    B --> C[main.py]
    C --> D[Logging init]
    D --> E[Create Bot & Dispatcher]
    E --> F[Attach middleware (DB session)]
    F --> G[Register handlers]
    G --> H[on_startup: init_db + scheduler]
    H --> I[Long polling: dp.start_polling]

    I --> J{Incoming update?}
    J -->|Yes| K[Handler (register/profiles/reports)]
    K --> L[Business logic: Avito API / reports]
    L --> M[Database (SQLAlchemy)]
    M --> I

    H --> N[Scheduler (APScheduler)]
    N --> O[Check report tasks]
    O --> P[Send reports to Telegram]
    P --> I

    I --> Q{SIGTERM/SIGINT}
    Q -->|Yes| R[on_shutdown: stop_scheduler + dispose DB]
    R --> S[Process exit]
```
