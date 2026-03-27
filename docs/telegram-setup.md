# Telegram Setup

This document explains how Telegram notifications work in Praina, how to configure them, and how users link their Telegram chat to their Praina account.

## Scope

Praina uses Telegram as an outbound notification channel.

Current design:

- Praina sends Telegram messages
- Telegram does not need to call Praina
- no webhook is required
- no polling worker is required
- linking is done through an on-demand deep link + `getUpdates` discovery flow

This design fits VPN and on-prem deployments because Praina does not need public inbound exposure.

## How It Works

The link flow is:

1. user opens `Profile` in Praina
2. user clicks `Generate Link`
3. Praina creates a one-time code and deep link for the configured bot
4. user opens the bot link and presses `Start` in Telegram
5. user returns to Praina and clicks `Find Chat`
6. Praina calls Telegram `getUpdates`, finds that code, and extracts the matching `chat_id`
7. Praina stores the link
8. future Praina notifications for that user can also be delivered to Telegram

## Operator Setup

### 1. Create a Telegram bot

Use `@BotFather` in Telegram.

Steps:

1. open Telegram
2. chat with `@BotFather`
3. run `/newbot`
4. choose a bot name
5. choose a bot username ending in `bot`
6. copy the bot token

You will need:

- bot token
- bot username

### 2. Configure Praina

Set these environment variables:

```env
TELEGRAM_BOT_TOKEN=<your-bot-token>
TELEGRAM_BOT_USERNAME=<your-bot-username-without-@>
```

Example:

```env
TELEGRAM_BOT_TOKEN=123456789:AA...
TELEGRAM_BOT_USERNAME=praina_notify_bot
```

Important:

- set `TELEGRAM_BOT_USERNAME` without `@`
- restart the backend after changing either Telegram variable
- the profile modal will show `Not configured` in the `Bot` field if the backend process is running without `TELEGRAM_BOT_USERNAME`

For the containerized setup, add them to:

- [deploy/docker/.env.example](/home/luca/dev/code/praina/deploy/docker/.env.example) as real values in your `.env`

For local backend development, set them in:

- [backend/.env](/home/luca/dev/code/praina/backend/.env)

Then restart the backend.

### 3. Apply migrations

If Telegram support was added after your database was created, make sure the latest migration is applied:

```bash
cd /home/luca/dev/code/praina/backend
source .venv/bin/activate
alembic upgrade head
```

### 4. Bot visibility

Users must be able to find and start the configured bot in Telegram.

No webhook setup is needed in this design.

## User Setup

### 1. Start the bot

The user should open the configured bot in Telegram and press `Start`.

This is required so Telegram allows the bot to send messages to that chat.

### 2. Link Telegram in Praina

In Praina:

1. open `Profile`
2. find the Telegram section
3. click `Generate Link`
4. click `Open Bot`
5. press `Start` in Telegram
6. return to Praina
7. click `Find Chat`

If verification succeeds:

- the Telegram chat becomes linked to the Praina user
- Telegram notifications are enabled by default

The user can later:

- disable Telegram notifications
- re-enable Telegram notifications
- disconnect Telegram entirely

## What Gets Sent

Telegram only receives notifications already addressed to that user in Praina.

Praina does not use Telegram as a second permission system.

That means:

- no broadcast to unrelated users
- no project access expansion through Telegram
- no shared group chat logic in this setup

Current behavior:

- Praina creates the normal in-app notification
- if the user has Telegram linked and Telegram delivery enabled
- Praina also sends the notification text to that user’s Telegram chat

## Security Notes

This design is intentionally conservative.

Properties:

- one Telegram chat can be linked to one Praina user
- verification requires receiving a code in that chat
- Praina remains outbound-only with respect to Telegram
- no public inbound endpoint is required

Tradeoffs:

- the bot must appear in recent Telegram updates, so the user must actually press `Start`
- linking depends on Telegram retaining the relevant update until discovery is completed
- this is less immediate than webhook or continuous polling, but simpler operationally

## Operational Notes

### If Telegram is not configured

If these variables are missing:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_BOT_USERNAME`

then Telegram linking and delivery will not work correctly.

Common symptom:

- the profile modal shows `Not configured` in the `Bot` field

In that case, the backend process you are using is running without `TELEGRAM_BOT_USERNAME` loaded.

### If the user does not receive the verification code

Check:

1. the bot token is valid
2. the bot username in config matches the actual bot
3. the user already pressed `Start` on the bot
4. the user clicked `Open Bot` after generating the link
5. the backend host can reach `api.telegram.org`

### If linking fails

Possible reasons:

- the link code expired
- the user did not press `Start` in the bot
- Telegram has no update containing the generated code
- the discovered chat is already linked to another user

## Troubleshooting Checklist

### Backend

Confirm env values are loaded:

```bash
cd /home/luca/dev/code/praina/backend
source .venv/bin/activate
python3 -c "from app.core.config import settings; print(repr(settings.telegram_bot_username)); print(bool(settings.telegram_bot_token))"
```

Expected:

- first line: your bot username, for example `'prainabot'`
- second line: `True`

### Database

Confirm Telegram columns exist:

```bash
cd /home/luca/dev/code/praina/backend
source .venv/bin/activate
python - <<'PY'
from app.core.config import settings
from sqlalchemy import create_engine, text
engine = create_engine(settings.database_url)
with engine.connect() as conn:
    print(conn.execute(text(\"select to_regclass('public.user_accounts')\")).fetchall())
    print(conn.execute(text(\"select column_name from information_schema.columns where table_name='user_accounts' and column_name like 'telegram_%' order by column_name\")).fetchall())
PY
```

### Functional check

Use a real user account:

1. open `Profile`
2. click `Generate Link`
3. click `Open Bot`
4. press `Start` in Telegram
5. return to Praina and click `Find Chat`
6. trigger a Praina notification for that user
7. verify it appears both:
   - in the Praina notification dropdown
   - in Telegram

## Future Improvements

Possible later improvements:

- category-level Telegram notification preferences
- richer Telegram formatting
- links back into Praina
- a more user-friendly onboarding flow if public webhook or polling ever becomes acceptable
