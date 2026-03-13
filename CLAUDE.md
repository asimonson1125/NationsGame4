# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
python3 run.py          # start dev server (debug mode, auto-reload)
python3 run.py init-db  # create DB tables (first run only)
```

No `python` binary — always use `python3`/`pip3` on this machine.

PostgreSQL is required for all environments. Schema is initialized via `python3 run.py init-db`, which also creates the necessary hash partitions.

## Migrations

Schema changes use a lightweight migration system in `migrations/`. Each migration is a Python module with a `migrate(app)` function. The runner tracks applied migrations in a `_migrations_applied` table.

**Adding a migration:**
1. Create `migrations/<name>.py` with a `migrate(app)` function using raw SQL via `db.session.execute(text(...))`
2. Add the module name to the `MIGRATIONS` list in `migrations/__init__.py`

**Running migrations:**
```bash
# Run all pending migrations (preferred)
python3 -c "from run import app; from migrations import run_all; run_all(app)"

# Run a single migration directly
python3 -c "from run import app; from migrations.<name> import migrate; migrate(app)"
```

Migrations must be idempotent — use `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, and `ON CONFLICT DO NOTHING` for data backfills. Never drop or destructively alter existing columns in a migration.

## Architecture

**Stack:** Flask + SQLAlchemy (PostgreSQL with Partitioning) + HTMX + Alpine.js + Tailwind CSS. No build step — all JS/CSS are CDN-loaded.

**App factory:** `app/__init__.py` — registers blueprints, Jinja2 filter `format_resource`, Flask-APScheduler (hourly production tick), Flask-Login.

**Blueprints:**
- `auth` — `/login`, `/logout`, `/register`
- `main` — `/` (home), `/gp-breakdown`, `/resource-footer`, `/update-flag`, `/update-description`
- `economy` — `/land`, `/expand-borders`, `/colonize`, `/buy-cleared-land`, `/build-urban-areas`, `/industry`, `/industry/build`, `/industry/collect/<key>`

**Models** (`app/models.py`):
- `User` — auth only
- `Nation` — resource columns (money, food, power, building_materials, consumer_goods, metal, ammunition, fuel, uranium, whz), land columns (cleared_land, urban_areas, forested_land, mountainous_land, coastal_land, fertile_land, arid_land, tundra_land, swamp_land, volcanic_land, used_land, total_land), GP columns (land_gp, factory_gp), tier, continent, flag_url, description
- `NaturalResource` — nation_id + resource_key + amount
- `NationFactory` — nation_id + factory_key + count + production_capacity (0–24)
- `NationBuilding` — nation_id + building_key + level (unique per nation+key)
- `BuildingUpgradeQueue` — nation_id + building_key + target_level + completes_at (unique per nation+key)
- `Alliance` — basic group

**Background task** (`app/tasks.py`): `increment_production_capacity` runs hourly, adds 1 to every `NationFactory.production_capacity` (capped at 24). Guarded with `WERKZEUG_RUN_MAIN` to avoid double-start in debug mode.

## HTMX Patterns

- **Partials return HTML fragments**, not full pages. Routes swap a specific `#id` target.
- **Error responses:** `_error_response(message)` returns an empty response with `HX-Trigger: {"showMessage": {...}}` — the toast system in `base.html` listens for this event.
- **Success triggers:** Routes set `HX-Trigger` with `showMessage` and/or `refreshResourceFooter` headers.
- **`hx-swap="none"`** for collect (no DOM update needed, just toast).
- **`hx-swap="outerHTML"` on `#industry-content`** for build (re-renders the two-tab partial).

## Alpine.js Patterns

- `[x-cloak] { display: none !important; }` must appear in `<style>` before Alpine loads — it's in `base.html` to prevent flash-of-unstyled-content.
- Tab state: `x-data="{ tab: '{{ default_tab | default(\'collect\') }}' }"` — `default_tab` is passed from the route on build success to reopen the Build tab.
- Build card reactivity: `x-data="{ qty: 1, fmt(n){...} }"` per card; land/cost values use `x-text="fmt(qty * {{ server_value }})"`. Input/output rates are static Jinja (not reactive).

## Building System

**Definitions** (`app/game/buildings.py`): 8 buildings in `BUILDING_DEFS`, split into two modes.

**Military buildings** gate unit recruitment by tier. Each has `unit_type` and `unlock_tier`. The required building level for a unit of a given tier is `tier - (unlock_tier - 1)`.

| Building | unit_type | unlock_tier | max_level |
|---|---|---|---|
| Barracks | Infantry | 1 | 4 |
| Special Forces HQ | Special Forces | 2 | 4 |
| Armored Vehicle Factory | Armour | 3 | 5 |
| Artillery & Defense Base | Static | 3 | 5 |
| Airfield | Air | 4 | 5 |

Example: an Infantry Tier 3 unit requires Barracks Lvl `3 - (1-1) = 3`.

**Factory prerequisite buildings** gate natural-resource-consuming factories by tier band. Each has `factory_category` and `level_max_tier` list. The required level is the first index where `tier <= level_max_tier[i]`, plus 1.

| Building | factory_category | max_level | level_max_tier |
|---|---|---|---|
| Botanical Research Station | flora | 4 | [2, 4, 6, 10] |
| Wildlife Ranch | fauna | 3 | [2, 4, 6] |
| Mining Bureau | mined | 3 | [2, 4, 6] |

Example: a flora tier 5 factory requires Botanical Research Station Lvl 3 (since 5 ≤ 6, the third band).

**Models:** `NationBuilding` (nation_id, building_key, level) + `BuildingUpgradeQueue` (nation_id, building_key, target_level, completes_at). Upgrades autocomplete via `process_building_upgrades()` (60s scheduler task), matching the factory build queue pattern.

**Seeding:** All nations start with Barracks Lvl 1 — seeded on registration in `auth/routes.py` and backfilled via `migrations/add_buildings.py`.

**Gate enforcement:** `build_factory` (economy) and `recruit_unit` (military) both check building prerequisites and return an error toast if unmet. `factory_lock_map` and `building_lock_map` dicts are computed in `_industry_context()` and `_building_lock_map()` respectively for template rendering.

## Factory System

**Definitions** (`app/game/factories.py`): 66 factories in `FACTORY_DEFS` dict, keyed by snake_case string (e.g. `farm`, `coal_power_plant`, `nuclear_reactor`). All match NG3 data exactly.

`FactoryDef` fields: `name`, `tier` (1–10), `category` (`'flora'`/`'fauna'`/`'mined'`/`''`), `inputs` (dict res→rate/h), `outputs` (dict res→rate/h), `max_collect_hours`, `build_cost` (dict res→amount), `land_required` (dict land_type→tiles), `gp_value`. Factories with a non-empty `category` require the corresponding prerequisite building (see Building System above).

Resource key aliases used in definitions: `_M=money`, `_P=power`, `_F=food`, `_BM=building_materials`, `_CG=consumer_goods`, `_ME=metal`, `_AM=ammunition`, `_FU=fuel`, `_UR=uranium`, `_WH=whz`.

**Starter factories** seeded on registration (in `auth/routes.py`).

**Natural resource inputs** (coal, iron, uranium as raw ore, etc.) are on `NationFactory` definitions but the `NaturalResource` collection system isn't wired — `getattr(nation, 'coal', 0)` returns 0, so affected factories will always fail the input check until that system is built.

## Discovery Engine

`app/game/discovery.py`: `roll_expansion(continent)` returns `(land_dict, resources_dict)` — continent-weighted terrain distribution, resource discovery chance rolls. `roll_colonization(continent)` does the same at 5× scale. `EXPANSION_LAND_TOTAL = 250` tiles per expansion.

## Template Conventions

- `economy/partials/industry_content.html` — the `<div id="industry-content">` wrapper; included in `industry.html` and also returned directly by `build_factory` route.
- Jinja filter `format_resource` (defined in `app/__init__.py`) — formats large numbers with k/m/b suffixes; use this for static display values. Alpine `fmt(n)` JS function does the same for reactive values.
- Icons: `url_for('static', filename='images/<resource>_icon.png')` with `onerror="this.style.display='none'"` fallback.

## Progress Reference

See `PROGRESS.md` for phase completion status. Phases 3–5 (military engine, market/alliance, optimization) are not yet started.
