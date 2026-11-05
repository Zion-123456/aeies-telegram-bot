# AEIES Telegram Academic Assistant

AEIES is a Python Telegram bot foundation for academic assistance. The initial
version provides `/start` and `/help`. Academic workflows, data models, and access
rules will be implemented against the approved project specification.

## Architecture

- `aeies/__main__.py`: application assembly and Telegram polling entry point.
- `aeies/handlers/`: Telegram update handling.
- `aeies/services/`: academic business logic independent of Telegram.
- `aeies/database/`: lazy Supabase client and future persistence adapters.
- `aeies/keyboards/`: future Telegram keyboard builders.
- `aeies/middleware/`: future authorization and request policies.
- `migrations/`: reviewed database schema migrations; none applied yet.
- `tests/`: offline configuration, handler, and application assembly tests.
- `scripts/`: development tooling.
- `backups/`: ignored local backup outputs; never commit student data.

## Development

Use Python 3.12 or newer:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Enter credentials locally or through secure environment settings.
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m aeies
```

`TELEGRAM_BOT_TOKEN` is required for live polling. `SUPABASE_URL` and
`SUPABASE_KEY` are required when database features are enabled. The initial
commands do not require a database. Only run one poller per bot token. Keep
credentials and private academic data out of Git and logs. Never expose a
Supabase privileged key to users; define authorization and row-level security
before adding student records.

No Supabase project or paid resources are created by installation. Offline tests
do not contact Telegram or Supabase. Live integration checks require configured
accounts and credentials. Direct dependencies are pinned; transitive dependencies
are not yet locked.
