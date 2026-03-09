# NationsGame 4 (NG4)

A browser-based nation-building simulator. Players manage resources, industry, land, and military across five continents.

**Stack:** Flask · SQLAlchemy (PostgreSQL with Partitioning) · HTMX · Alpine.js · Tailwind CSS · Flask-Caching (SimpleCache dev / Redis prod)

---

## Development

```bash
pip3 install -r requirements.txt   # Python dependencies
npm install                        # Tailwind CSS (dev only)
python3 run.py init-db             # create DB tables (first run only)
python3 run.py                     # dev server (debug, auto-reload)
```

No `python` binary on this machine — always use `python3` / `pip3`.

Local development requires a PostgreSQL instance. The application uses declarative hash partitioning for scalability.

1.  **Start PostgreSQL:** Ensure a DB named `ng4` exists.
2.  **Initialize:** `python3 run.py init-db` (creates tables and 16 hash partitions).
3.  **Run:** `python3 run.py`.

## Testing

```bash
pytest tests/
```

**Note:** Tests require a running PostgreSQL instance. The test runner will:
1.  Automatically create a database named `ng4_test` if it doesn't exist.
2.  Initialize the schema and create 2 hash partitions for each partitioned table (military, trade, etc.) before each test run.
3.  Wipe the test data after each test.

### Tailwind CSS

The CDN play script has been replaced with a local JIT build. After editing templates, rebuild CSS:

```bash
npm run build:css              # one-off minified build
npm run watch:css              # watch mode for development
```

The built file lives at `app/static/css/style.css`. Source styles are in `app/static/css/input.css` and `tailwind.config.js`.

---

## Database Management

### Flask Shell

Use the Flask shell to manually modify the database using SQLAlchemy models. This works in both local development and production (PostgreSQL).

**Local Development:**
```bash
flask shell
```

**Docker / Production:**
```bash
docker exec -it ng-app flask shell
```

**Example: Set a user to admin**
```python
from app.models import User
from app import db

# Find user by username and set is_admin to True
user = User.query.filter_by(username='Cascadalyst').first()
if user:
    user.is_admin = True
    db.session.commit()
    print(f"User {user.username} is now an admin.")
else:
    print("User not found.")
```

---

### Option A: Docker Compose (recommended)

**Standalone** (includes Nginx):
```bash
python3 setup_env.py
docker compose --profile standalone up --build -d
```

**Behind Nginx Proxy Manager** (or another external proxy):
```bash
python3 setup_env.py           # set APP_PORT when prompted, e.g. 127.0.0.1:8001
docker compose up --build -d   # starts app, postgres, redis — no nginx
```
Then point NPM to `http://127.0.0.1:8001`.

The script prompts for all required vars, generating a random `SECRET_KEY` and Postgres password automatically.

Services:

| Service | Image | Purpose |
|---------|-------|---------|
| `db` | postgres:16-alpine | Primary database |
| `redis` | redis:7-alpine | Flask-Caching backend |
| `app` | Built from Dockerfile | Flask + Gunicorn |
| `nginx` | nginx:alpine | Reverse proxy, static files, gzip |

The app is accessible at `http://localhost` (or the `HOST_PORT` set in `.env`). Database tables are created automatically on first boot via `docker-entrypoint.sh`.

### Option B: Manual Gunicorn

```bash
pip3 install -r requirements.txt
python3 setup_env.py           # generates .env with a random SECRET_KEY
# edit .env — set DATABASE_URL, REDIS_URL, etc.
source .env
gunicorn -c gunicorn.conf.py wsgi:app
```

`setup_env.py` flags:
- `--defaults` — accept all defaults without prompting (CI/scripted deploys)
- `--force` — overwrite an existing `.env`

Point Nginx (or another reverse proxy) at `localhost:8000` using the provided `nginx/nginx.conf` as a reference.

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | — | Flask session secret |
| `DATABASE_URL` | Yes (prod) | `postgresql://ng4:ng4@localhost:5432/ng4` | SQLAlchemy connection string |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Flask-Caching Redis backend |
| `CACHE_TYPE` | No | `RedisCache` | Cache backend (`SimpleCache` or `RedisCache`) |
| `WEB_CONCURRENCY` | No | `4` | Gunicorn worker count |
| `POSTGRES_DB` | Docker only | `ng4` | PostgreSQL database name |
| `POSTGRES_PORT`| No | `5433` | Host port for local development |
| `POSTGRES_USER` | Docker only | `ng4` | PostgreSQL user |
| `POSTGRES_PASSWORD` | Docker only | — | PostgreSQL password |
| `HOST_PORT` | Docker only | `80` | Host port mapped to Nginx |

---

## Project Structure

```
app/
  auth/          # login, register, logout
  economy/       # land expansion, industry, colonization
  main/          # home, leaderboard, nation profile
  military/      # units, battles, equipment
  trade/         # market
  game/          # pure game logic (no Flask imports)
    cache.py        ← cached accessors for static game data
    population.py   ← population tick rates
    discovery.py    ← land/resource weights per continent
    factories.py    ← 66 factory definitions
    units.py        ← unit stats and upkeep
    combat.py       ← battle resolution
    equipment.py    ← equipment buffs
    constants.py    ← continent list, resource keys
  models.py      # SQLAlchemy models
  tasks.py       # APScheduler hourly/minutely jobs
  templates/
    base.html       # navbar, footer, toast system
    shared/         # reusable macros (_equipment_macros.html)
  static/
    css/
      input.css     # Tailwind source + custom styles
      style.css     # built output (committed)
    images/
      icons/        # resource, land, and unit type icons
      continents/   # continent background images
nginx/
  nginx.conf       # production reverse proxy config
config.py          # dev/prod/test Flask config
wsgi.py            # production WSGI entry point
gunicorn.conf.py   # Gunicorn worker settings
docker-compose.yml # multi-container deployment
Dockerfile         # app container image
docker-entrypoint.sh
tailwind.config.js # Tailwind theme (extracted from CDN config)
package.json       # npm scripts for CSS build
```

---

## Key Tuning Parameters

### Population Tick — `app/game/population.py`

Runs **hourly** via APScheduler. Applied per capita.

```python
# Rates expressed as 1/N where N = people per unit per hour.
POPULATION_RATES = {
    'money':           1/100,   # 100 people per tax dollar
    'food':           -1/2000, # 2000 people per food
    'power':          -1/2500, # 2500 people per power
    'consumer_goods': -1/5000, # 5000 people per consumer goods
}

# Consumer goods consumption only kicks in above this threshold.
CG_POPULATION_THRESHOLD = 100_000

# Tier thresholds: (min_population, tier) — checked highest-first
# T1: <75k | T2: 75k–150k | T3: 150k–350k | T4: 350k–1M | T5: 1M–2.5M | T6: 2.5M+
TIER_THRESHOLDS = [
    (2_500_000, 6),
    (1_000_000, 5),
    (350_000,   4),
    (150_000,   3),
    (75_000,    2),
]

# Growth constants
GROWTH_MULTIPLIER = 0.05       # base hourly growth factor
FOOD_PER_CITIZEN = 0.1          # food cost per new citizen
LAND_PER_POPULATION = 1000      # 1 tile per 1,000 new pop
STARVATION_RATE = 0.01          # 1% population loss per hour when starving
```

---

### Land & Resource Distribution — `app/game/discovery.py`

Controls what terrain and resources appear when a nation expands or colonizes. Weights are relative — higher = more likely.

**`LAND_WEIGHTS`** — terrain distribution per continent:

| Continent     | Dominant terrain      |
|---------------|-----------------------|
| Westberg      | Forest (43)           |
| Amarino       | Jungle (60)           |
| San Sebastian | Mixed                 |
| Tind          | Mountain (34), Tundra (30) |
| Zaheria       | Desert (85)           |

**`RESOURCE_WEIGHTS`** — natural resource discovery odds per continent. Higher weight = discovered in larger quantities on expansion.

**Expansion land formula:** `max(1, population // 100)` tiles per expansion; colonization gives 5×.

---

### Military Upkeep — `app/game/units.py`

Each unit definition has a per-hour `upkeep` dict (e.g. `{money: 5, food: 1, ammunition: 1}`). If a nation can't afford full upkeep for any resource, **all units take 10% max-HP attrition** (floored at 20% max HP) that tick instead of deducting resources.

---

### Factory Production Capacity — `app/tasks.py`

`increment_production_capacity` runs **hourly**, adding +1 capacity to every factory (max 24). Factories collect resources proportional to capacity at collection time.

---

## Background Jobs

| Job | Frequency | Function |
|-----|-----------|----------|
| Population tick | Hourly | `process_population_tick` |
| Military upkeep | Hourly | `deduct_military_upkeep` |
| Factory capacity | Hourly | `increment_production_capacity` |
| Factory queue | Every 60s | `process_factory_queue` |
| Battle tick | Every 60s | `process_battle_tick` |

Jobs are registered in `app/tasks.py` and guarded with `WERKZEUG_RUN_MAIN` to prevent double-start in debug mode.

---

## HTMX / Alpine Conventions

- Partials return HTML fragments and swap a specific `#id` target.
- Errors use `HX-Trigger: {"showMessage": {...}}` — the toast in `base.html` listens for this.
- Alpine dropdowns in the navbar use a `close-nav-dropdowns` window event to coordinate mutual exclusion.
- `[x-cloak] { display: none !important; }` lives in `app/static/css/input.css` (compiled into `style.css`) to prevent FOUC.

---

## Starter State (on Registration)

New nations receive: 2 farms, 1 windmill, 5 quarry, and 500 tiles of land distributed by continent weights.
