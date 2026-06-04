# VPS deploy notes

This project contains a Telegram booking bot and a Flask admin panel.

## Legacy files

These files are kept only as legacy snapshots and are not used by the systemd examples:

- `bot_0.py`
- `bot_work.py`
- `bot_work_1.py`

The active bot entry point is `bot.py`.

## Create a user and project directory

```bash
sudo adduser --system --group --home /opt/booking_bot bookingbot
sudo mkdir -p /opt/booking_bot
sudo chown -R bookingbot:bookingbot /opt/booking_bot
```

Copy the project files to `/opt/booking_bot`. Keep `database.db` with the project unless you set `DATABASE_PATH`.

## Create venv

```bash
cd /opt/booking_bot
sudo -u bookingbot python3 -m venv venv
```

## Install dependencies

```bash
cd /opt/booking_bot
sudo -u bookingbot ./venv/bin/python -m pip install --upgrade pip
sudo -u bookingbot ./venv/bin/python -m pip install -r requirements.txt
```

## Fill .env

```bash
cd /opt/booking_bot
sudo -u bookingbot cp .env.example .env
sudo -u bookingbot nano .env
```

Required values:

```dotenv
BOT_TOKEN=
ADMIN_ID=
ADMIN_LOGIN=
ADMIN_PASSWORD=
DATABASE_PATH=
FLASK_HOST=127.0.0.1
FLASK_PORT=8000
FLASK_DEBUG=0
```

If `DATABASE_PATH` is empty, the app uses `database.db` in the project directory.

## Check bot.py

```bash
cd /opt/booking_bot
sudo -u bookingbot ./venv/bin/python -m py_compile bot.py admin_panel.py database.py
sudo -u bookingbot ./venv/bin/python bot.py
```

Stop the manual bot check with `Ctrl+C`.

## Check admin_panel.py

```bash
cd /opt/booking_bot
sudo -u bookingbot ./venv/bin/python admin_panel.py
```

Open the admin panel according to `FLASK_HOST` and `FLASK_PORT`. For production, place it behind a reverse proxy or SSH tunnel.

## systemd examples

Install the service examples:

```bash
sudo cp /opt/booking_bot/booking_bot.service.example /etc/systemd/system/booking_bot.service
sudo cp /opt/booking_bot/booking_admin.service.example /etc/systemd/system/booking_admin.service
sudo systemctl daemon-reload
sudo systemctl enable booking_bot.service booking_admin.service
sudo systemctl start booking_bot.service booking_admin.service
```

## Logs

```bash
sudo journalctl -u booking_bot.service -f
sudo journalctl -u booking_admin.service -f
sudo journalctl -u booking_bot.service -n 100 --no-pager
sudo journalctl -u booking_admin.service -n 100 --no-pager
```

## Notes

- Never add `.env` to git.
- Reissue the real Telegram token in BotFather before production launch.
- Do not copy legacy files `bot_0.py`, `bot_work.py`, `bot_work_1.py` to the VPS.
- Do not run the old `telegram_bot.service` unless it has been reviewed.
- Do not run Flask with `FLASK_DEBUG=1` in production.
- Back up `database.db` before any schema changes.
