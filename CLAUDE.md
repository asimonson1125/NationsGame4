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
- `military` — division management, unit recruitment, mobilization, peacekeeping missions
- `equipment` — equipment inventory, loot crates, equip/unequip
- `trade` — trade orders (buy/sell)
- `alliance` — create/join/manage alliances
- `mail` — nation-to-nation messaging
- `war` — declare war, deploy divisions, settlement/peace

**Models** (`app/models.py`):
- `User` — auth; `is_admin`, `is_system`, `vacation_mode`, `login_version` (used in session token `id:version`)
- `Nation` — resources (money, food, power, building_materials, consumer_goods, metal, ammunition, fuel, uranium, whz), land (total_land, cleared_land, urban_areas, used_land, forest, grassland, jungle, desert, mountain, tundra, river, lake), GP columns (population_gp, land_gp, factory_gp, building_gp, military_gp), computed `total_gp`, tier, continent, population, `loot_tokens`
- `NaturalResource` — nation_id + resource_key + amount (hash-partitioned)
- `NationFactory` — nation_id + factory_key + count + production_capacity 0–24 (hash-partitioned)
- `FactoryBuildQueue` — nation_id + factory_key + quantity + completes_at
- `NationBuilding` — nation_id + building_key + level
- `BuildingUpgradeQueue` — nation_id + building_key + target_level + completes_at
- `Alliance` / `AllianceApplication` — groups + pending membership requests
- `Division` — nation_id + name + mobilization_state (demobilized|mobilizing|mobilized) + in_combat + is_defensive (hash-partitioned)
- `Unit` — nation_id + division_id + unit_key + level/xp + stats (firepower/armour/maneuver/hp/max_hp) + equipment FKs weapon_id/accessory_id/armour_eq_id (hash-partitioned)
- `RecruitmentQueue` — nation_id + unit_key + completes_at
- `Equipment` — nation_id + equipment_type + rarity + foil + buff_json + unit slots (hash-partitioned)
- `TradeOrder` — nation_id + resource_key + order_type (buy/sell) + quantity + price
- `Message` — sender_id + recipient_id + subject + body + is_read + message_type
- `Battle` — attacker/defender nation + division IDs/names, battle_type (pvp|peacekeeping|pve_mission), status (active|finished), winner
- `WarBattle` — links War to Battle with side (attacker|defender)
- `War` — attacker_nation_id + defender_nation_id + status (active|peace) + war score tracking
- `WarDeploymentQueue` — pending division deployments in a war (status: traveling|arrived)
- `NationEvent` — event_type + description + occurred_at (for nation timeline)
- `CombatReport` — battle_id + attacker_nation_id + log_json

**Background tasks** (`app/tasks.py`) — registered via `register_tasks(app)` with Flask-APScheduler:
- **Hourly** (`process_hourly_tick`): increments `production_capacity` (+1 capped at 24) for all NationFactory rows with count > 0, then runs `tick_nation()` on every nation (population effects → food → growth/starvation → tier update → military upkeep → attrition or healing). Skips vacation-mode nations.
- **Every 60s**: `process_recruitment_queue`, `process_factory_queue`, `process_building_upgrades`, `process_war_deployments`, `process_combat_rounds` (randomized ~60s mean delay between rounds)
- **Daily midnight UTC**: `reset_daily_counters` (resets `mission_skips_today`), `cleanup_pve_battles` (deletes PvE battles older than 2 weeks)

## Testing

```bash
python3 -m pytest                    # run all tests
python3 -m pytest tests/test_war.py  # run a single test file
python3 -m pytest -k test_name       # run a specific test by name
```

Tests use a real PostgreSQL database (`ng4_test`). `conftest.py` creates the DB if missing, runs `db.create_all()` + `create_partitions()` before each test, and drops the public schema after each test (full isolation). Key fixtures: `nation`, `auth_client`, `admin_user`, `admin_client`.

## HTMX Patterns

- **Partials return HTML fragments**, not full pages. Routes swap a specific `#id` target.
- **Error/success helpers** are in `app/helpers.py`: `error_response(message)` and `success_response(message, html)` both set `HX-Trigger` with `showMessage`. `htmx_response()` is the lower-level builder; also always adds `refreshResourceFooter`.
- **`hx-swap="none"`** for collect (no DOM update needed, just toast).
- **`hx-swap="outerHTML"` on `#industry-content`** for build (re-renders the two-tab partial).
- `can_afford(nation, cost_dict)` and `deduct_cost(nation, cost_dict)` in `app/helpers.py` are the standard affordability check + deduction pattern used across all blueprints.

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

**Natural resource inputs** (coal, iron, uranium as raw ore, etc.) are stored in `NaturalResource` rows and included in factory input validation via `stock_map` in `_industry_context()` (`economy/routes.py`). The collection system is wired.

## Discovery Engine

`app/game/discovery.py`: `roll_expansion(continent)` returns `(land_dict, resources_dict)` — continent-weighted terrain distribution, resource discovery chance rolls. `roll_colonization(continent)` does the same at 5× scale. `EXPANSION_LAND_TOTAL = 250` tiles per expansion.

## Template Conventions

- `economy/partials/industry_content.html` — the `<div id="industry-content">` wrapper; included in `industry.html` and also returned directly by `build_factory` route.
- Jinja filter `format_resource` (defined in `app/__init__.py`) — formats large numbers with k/m/b suffixes; use this for static display values. Alpine `fmt(n)` JS function does the same for reactive values.
- Icons: `url_for('static', filename='images/<resource>_icon.png')` with `onerror="this.style.display='none'"` fallback.
- `static_url(filename)` Jinja global returns a cache-busted URL using mtime hash — use instead of `url_for('static', ...)` for versioned assets.
- `cost_class(cost, stockpile)` Jinja filter — returns `text-red-500 font-semibold` if unaffordable, else `text-slate-400`.

## Military System

Units live in `Division` containers. Division `mobilization_state`: `demobilized` → `mobilizing` → `mobilized`. Only mobilized divisions can be deployed to war. `is_defensive=True` marks the division that auto-engages incoming war deployments.

**Unit stats:** `firepower`, `armour`, `maneuver`, `hp`/`max_hp`, `level` (1–15), `xp`. Level-ups grant random stat buffs (`+1 fp/arm/man` or `+10% max_hp`) via `process_xp_gain()` in `app/game/levels.py`. `Unit.effective_max_hp` property factors in equipped armour buffs.

**Recruitment:** costs deducted immediately, unit appears in `RecruitmentQueue` until timer expires, then `process_recruitment_queue` creates the `Unit` row and credits `military_gp`.

**Upkeep:** demobilized units pay money-only; mobilized units pay full resource upkeep. Computed by `compute_total_upkeep(nation_id)` in `app/helpers.py`.

**Combat** (`app/game/combat.py`): round-based simulation. Ability strings on `UnitDef.special_abilities` are parsed by regex functions (`_parse_fp_multiplier`, `_parse_armour_multiplier`, etc.) into live modifiers each round.

## War System

`War` ties two nations. A nation deploys a division via `WarDeploymentQueue` (travel delay). `process_war_deployments` fires a `Battle` on arrival, matched against the defender's `is_defensive` division. Settlement is available when a side reaches 3+ net victories (`compute_war_scores` in `app/game/war.py`). Outcomes: compensation (resource transfer) or annexation (land transfer).

## Equipment System

Equipment has 3 slots per unit category (weapon, accessory, armour) defined in `EQUIPMENT_SLOTS` (`app/game/equipment.py`). Rarities: Common → Uncommon → Rare → Epic → Legendary with buff points 1/2/4/7/10. Drop rates sum to 1. 5% foil chance per drop. Rare requires unit level 5, Epic level 10, Legendary level 15 (`RARITY_LEVEL_REQ` in `app/game/levels.py`). Loot crates cost `loot_tokens`; tokens are earned from battle victories and missions.

## Missions System

`MissionDef` (`app/game/missions.py`) defines PvE encounters: enemy_count range, enemy_composition (unit_key → percent), rewards dict, rarity, cooldown, and optional `chapter_requires` dependency. Rarity weights: common 50 / uncommon 30 / rare 12 / epic 6 / legendary 2. Daily `mission_skips_today` counter resets at midnight.

## GP & Population System

`total_gp` is a PostgreSQL computed column: sum of `population_gp + land_gp + factory_gp + building_gp + military_gp`. Each component is updated at its event (factory built, unit recruited, building upgraded, land expanded). Population drives tier (`compute_tier` in `app/game/population.py`). Tier determines which units/factories/buildings are accessible.
