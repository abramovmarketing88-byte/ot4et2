# Как протестировать бота

## Что нужно

1. **Python 3.10+** (для `zoneinfo`).
2. **PostgreSQL** — база для бота и планировщика.
3. **Токен бота** — получить у [@BotFather](https://t.me/BotFather).
4. **Учётные данные Avito** (для добавления профиля) — client_id и client_secret из [личного кабинета Avito для бизнеса](https://www.avito.ru/professionals).

## Шаг 1: База данных

Запустите PostgreSQL и создайте БД:

```sql
CREATE DATABASE avito_bot;
```

Или через Docker:

```bash
docker run -d --name avito-pg -e POSTGRES_USER=user -e POSTGRES_PASSWORD=pass -e POSTGRES_DB=avito_bot -p 5432:5432 postgres:15
```

## Шаг 2: Переменные окружения

Скопируйте пример и заполните:

```bash
copy .env.example .env
```

В `.env` обязательно:

| Переменная       | Описание                          |
|------------------|-----------------------------------|
| `BOT_TOKEN`      | Токен от @BotFather               |
| `DATABASE_URL`   | `postgresql+asyncpg://user:pass@localhost:5432/avito_bot` |
| `ADMIN_CHAT_ID`  | (опционально) Ваш Telegram chat_id для уведомлений об ошибках |

Для добавления профиля Avito позже понадобятся `AVITO_CLIENT_ID` и `AVITO_CLIENT_SECRET` (можно оставить пустыми и заполнить при тесте `/add_profile`).

## Шаг 3: Установка и запуск

Из корня проекта (папка `avito_analytics_bot`):

```bash
cd avito_analytics_bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

В логах должно быть: `Bot started.`, `Scheduler started (timezone=Europe/Moscow).`

## Шаг 4: Проверка в Telegram

1. Найти бота по имени и нажать **Start** — должно прийти приветствие и список команд.
2. **`/profiles`** — список профилей (сначала пусто).
3. **`/add_profile`** — добавить профиль Avito (нужны client_id и client_secret из ЛК Avito).
4. После добавления профиля — **`/profiles`** → выбрать профиль → «Настроить отчёт» → указать чат и время (например `10:00`).
5. **`/cancel`** — отмена текущего действия в FSM.

## Шаг 5: Проверка отчётов по расписанию

- Планировщик раз в минуту сверяет время по Москве с полем `report_time` у активных задач.
- Чтобы отчёт ушёл «прямо сейчас», в настройках отчёта задайте время, равное текущему (по Москве) в формате **ЧЧ:ММ**, например `14:35`.
- В следующую минуту в указанный чат придёт отчёт за вчера (метрики Avito).

## Узнать свой chat_id для ADMIN_CHAT_ID

Напишите боту любое сообщение, затем откройте в браузере (подставьте свой `BOT_TOKEN`):

```
https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
```

В ответе найдите `"chat":{"id": 123456789}` — это ваш `chat_id`.

## Частые проблемы

| Проблема | Решение |
|----------|--------|
| `ModuleNotFoundError` | Запускать из папки `avito_analytics_bot` или установить пакет: `pip install -e .` из родительской папки. |
| Ошибка подключения к БД | Проверить, что PostgreSQL запущен и `DATABASE_URL` в `.env` верный. |
| Avito возвращает 401 | Проверить client_id и client_secret, пересоздать профиль через `/add_profile`. |
| Отчёт не приходит в чат | Убедиться, что бот добавлен в чат и время `report_time` совпадает с текущим (Москва) в формате ЧЧ:ММ. |
