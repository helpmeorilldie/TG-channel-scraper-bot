# Venice Scraper

Telegram bot that exports channel member lists (user id, username, name) as CSV,
using the requester's own account via MTProto. Free/paid daily quotas, UPI
payments with manual admin approval.

## Deploy (Render)

1. Push this repo to GitHub.
2. Render → New → Web Service → connect the repo.
3. Build: `pip install -r requirements.txt` · Start: `python bot.py`.
4. Health check path: `/health`.
5. Env vars: `BOT_TOKEN`, `TG_API_ID`, `TG_API_HASH`, `ADMIN_IDS`, `UPI_ID`.
   Do **not** set `SESSION_ENC_KEY`; `.session_key` is generated on first boot.
6. Optional but recommended: add a 1 GB Disk mounted at `/var/data` and set
   `DATA_DIR=/var/data`, plus pin `SESSION_ENC_KEY` in the dashboard.

## Local

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill it in
python bot.py
