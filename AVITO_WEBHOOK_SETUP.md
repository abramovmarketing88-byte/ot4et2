# Avito webhook + AI replies: what was implemented and what to do next

## What was implemented

### 1) Avito Messenger API: send + mark read
File: `core/avito/client.py`
- `send_message_text(user_id, chat_id, text)`
- `mark_chat_read(user_id, chat_id)`

These are used to send AI replies back into Avito chats and mark the chat read.

### 2) Webhook server (aiohttp)
File: `core/avito/webhook_server.py`

Features:
- HTTP server for Avito webhooks
- Quick 200 OK response
- Background processing:
  - find profile by `user_id`
  - check AI is enabled for that profile
  - save message to DB (`AIDialogMessage`)
  - generate reply (LLM stub)
  - send reply to Avito
  - mark chat read

### 3) App lifecycle wiring
File: `main.py`
- `on_startup()` starts the Avito webhook server (if enabled)
- `on_shutdown()` stops it

### 4) Config flags
File: `core/config.py`
Added:
- `AVITO_WEBHOOK_ENABLED` (bool, default False)
- `AVITO_WEBHOOK_HOST` (default `0.0.0.0`)
- `AVITO_WEBHOOK_PORT` (default `8000`, can be overridden by `PORT`)
- `AVITO_WEBHOOK_PATH` (default `/avito/webhook`)
- `AVITO_WEBHOOK_SECRET` (optional shared secret)

## What you must do (required)

### 1) Railway Variables
Add in Railway → service → Variables:

- `AVITO_WEBHOOK_ENABLED=true`
- `AVITO_WEBHOOK_PATH=/avito/webhook`
- `AVITO_WEBHOOK_PORT=8000` (optional; Railway can supply `PORT`)
- `AVITO_WEBHOOK_SECRET=<your-secret>` (optional, if you want to validate requests)

### 2) Avito Developer Portal
Register webhook URL:

```
https://<your-service>.railway.app/avito/webhook
```

### 3) Ensure AI is enabled for profile
In bot UI:
- Enable AI for the Avito profile
- Otherwise incoming messages will be ignored

## What is still missing (expected)

1) Real LLM integration
   - Current `core/llm/client.py` is a stub
2) Attachments (images / voice)
3) Webhook signature verification
4) Rate limits / throttling for AI replies
5) Robust dialog context (beyond “last N”)

## Minimal test checklist

1. Deploy with `AVITO_WEBHOOK_ENABLED=true`
2. Check logs for:
   - `Avito webhook server started on http://0.0.0.0:PORT/avito/webhook`
3. Send a message in Avito chat
4. Expect:
   - message saved in DB
   - AI reply sent back to Avito chat

