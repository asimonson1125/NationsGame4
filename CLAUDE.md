# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
python3 run.py          # start dev server (debug mode, auto-reload)
python3 run.py init-db  # create DB tables (first run only)
```

No `python` binary — always use `python3`/`pip3` on this machine.

The SQLite DB (`ng4.db`) is created in the project root on first run via `db.create_all()` in `run.py`. No migrations are used; schema changes require dropping and recreating the DB in development.

## Architecture

**Stack:** Flask + SQLAlchemy (SQLite dev / PostgreSQL prod) + HTMX + Alpine.js + Tailwind CSS. No build step — all JS/CSS are CDN-loaded.

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

## Factory System

**Definitions** (`app/game/factories.py`): 66 factories in `FACTORY_DEFS` dict, keyed by snake_case string (e.g. `farm`, `coal_power_plant`, `nuclear_reactor`). All match NG3 data exactly.

`FactoryDef` fields: `name`, `tier` (1–10), `inputs` (dict res→rate/h), `outputs` (dict res→rate/h), `max_collect_hours`, `build_cost` (dict res→amount), `land_required` (dict land_type→tiles), `gp_value`.

Resource key aliases used in definitions: `_M=money`, `_P=power`, `_F=food`, `_BM=building_materials`, `_CG=consumer_goods`, `_ME=metal`, `_AM=ammunition`, `_FU=fuel`, `_UR=uranium`, `_WH=whz`.

**Starter factories** seeded on registration: 2 farms, 1 windmill, 1 quarry (in `auth/routes.py`).

**Natural resource inputs** (coal, iron, uranium as raw ore, etc.) are on `NationFactory` definitions but the `NaturalResource` collection system isn't wired — `getattr(nation, 'coal', 0)` returns 0, so affected factories will always fail the input check until that system is built.

## Discovery Engine

`app/game/discovery.py`: `roll_expansion(continent)` returns `(land_dict, resources_dict)` — continent-weighted terrain distribution, resource discovery chance rolls. `roll_colonization(continent)` does the same at 5× scale. `EXPANSION_LAND_TOTAL = 250` tiles per expansion.

## Template Conventions

- `economy/partials/industry_content.html` — the `<div id="industry-content">` wrapper; included in `industry.html` and also returned directly by `build_factory` route.
- Jinja filter `format_resource` (defined in `app/__init__.py`) — formats large numbers with k/m/b suffixes; use this for static display values. Alpine `fmt(n)` JS function does the same for reactive values.
- Icons: `url_for('static', filename='images/<resource>_icon.png')` with `onerror="this.style.display='none'"` fallback.

## Progress Reference

See `PROGRESS.md` for phase completion status. Phases 3–5 (military engine, market/alliance, optimization) are not yet started.
