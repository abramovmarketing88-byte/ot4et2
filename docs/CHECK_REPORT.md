# Отчёт проверки проекта

## 1. Компиляция
- **python -m compileall -q alembic bot core main.py** — выполняется без ошибок (exit 0).

## 2. Импорты и структура
- **main.py**: подключает register, integrations, telegram_integration, ai_mode, ai_admin, profiles, reports, settings; регистрирует `on_business_connection_update` на `dp.update` с фильтром по `business_connection`.
- **core.avito.webhook_server**: используется в startup/shutdown — модуль есть.
- Локальный запуск без `BOT_TOKEN`/`DATABASE_URL` падает на загрузке `core.config` — ожидаемо; на Railway переменные заданы.

## 3. Клавиатуры ↔ обработчики
- **main:integrations**, **main:menu**, **main:reports** — обрабатываются в register/integrations.
- **intg:avito**, **intg:back**, **intg:telegram** — в integrations.py и telegram_integration.py.
- **tg_int:bot**, **tg_int:test_send**, **tg_int:business**, **tg_target:input_chat**, **tg_target:forward**, **tg_target:welcome_msg** — все есть в telegram_integration.py.
- **ai_set:*** (back_hub, toggle, prompt, prompt_full, prompt_edit, prompt_tpl, prompt_tpl_sel, prompt_file, context, ctx_*, format, fmt_*, delay, limits, limit_*, stopwords, notify_chat, notify_forward, handoff*, model, model_confirm, followups) — все обрабатываются в ai_mode.py.

## 4. Критичные потоки
- **Тест-чат**: при входе по «💬 Тест-чат» выставляются `user.current_branch_id`, `user.current_mode = "ai_seller"`, FSM `AiSellerStates.chatting` — сообщения обрабатывает `ai_chat_message` → LLMClient.generate_reply.
- **LLM**: при заданном `LLM_API_KEY` вызывается `_openai_call` (OpenAI API); иначе stub + предупреждение в лог.
- **Промпт**: кнопка «📄 Посмотреть полностью» отправляет полный текст частями по 4000 символов.
- **Telegram-интеграция**: целевой чат (ввод/пересылка), тест отправки, Business (инструкция + сохранение по апдейту).

## 5. Безопасность
- В telegram_integration: `get_target_by_id(target_id, user_id, session)` — проверка владельца; `_parse_target_id` в try/except.
- В ai_mode: `_get_profile_ai(telegram_id, profile_id, session)` — проверка владельца профиля.

## 6. Миграции
- Цепочка: … → 20260218_ai_ux → 20260218_tg_int.
- telegram_targets: user_id, target_chat_id, title, welcome_message, is_active, created_at; индексы user_id, target_chat_id.
- telegram_business_connections: user_id, connection_id (unique), business_user_id, user_chat_id, is_disabled, recipients_scope, created_at, updated_at.

## 7. Линтер
- Ошибок по bot/, core/ не выявлено.

## Рекомендации
- На Railway должны быть заданы: **BOT_TOKEN**, **DATABASE_URL**, **LLM_API_KEY** (для реальных ответов в тест-чате).
- Для полной проверки после деплоя: /start → Каналы/Интеграции → Telegram → Подключить бота (chat_id/тест) и Тест-чат в ИИ-продавце с включённым ИИ.
