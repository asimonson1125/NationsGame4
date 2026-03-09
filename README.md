# NationsGame 4 (NG4)

A browser-based nation-building simulator. Players manage resources, industry, land, and military across five continents.

**Stack:** Flask · SQLAlchemy (SQLite dev / PostgreSQL prod) · HTMX · Alpine.js · Tailwind CSS (CDN, no build step)

---

## Running the App

```bash
python3 run.py          # dev server (debug, auto-reload)
python3 run.py init-db  # create DB tables (first run only)
```

No `python` binary on this machine — always use `python3` / `pip3`.

The SQLite DB (`ng4.db`) is created in the project root. No migrations — schema changes require a DB drop/recreate in development.

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
    images/
      icons/        # resource, land, and unit type icons
      continents/   # continent background images
```

---

## Key Tuning Parameters

### Population Tick — `app/game/population.py`

Runs **hourly** via APScheduler. Applied per capita.

```python
POPULATION_RATES = {
    'money':           1/100,   # 100 people per tax dollar/hr
    'food':           -1/2000,  # 2000 people per food/hr
    'power':          -1/2500,  # 2500 people per power/hr
    'consumer_goods': -1/5000,  # 5000 people per consumer goods/hr
}
```

Rates are `1/N` where N = people required per unit. Positive = nation gains, negative = nation consumes.

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
- `[x-cloak] { display: none !important; }` lives in `base.html` before Alpine loads to prevent FOUC.

---

## Starter State (on Registration)

New nations receive: 2 farms, 1 windmill, 5 quarry, and 500 tiles of land distributed by continent weights.
