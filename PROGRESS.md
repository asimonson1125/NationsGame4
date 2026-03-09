# NG4 Implementation Progress

Reference: `../MODERNIZATION_STRATEGY.md`

---

## Phase 1: Core Framework & Identity ✅
**Goal:** Flask environment and primary "Hypermedia" shells.

- [x] Flask app factory with SQLAlchemy, Flask-Login, Flask-WTF (CSRF)
- [x] Blueprints: `auth`, `main`
- [x] SQLAlchemy models: `User`, `Nation`, `Alliance`
- [x] `base.html` — dark sidebar with Alpine.js dropdowns, resource footer (HTMX 60s refresh), GP modal, toast system
- [x] Session-based auth: login, logout, register
- [x] Home page (`/`) — nation header, settings panels via `hx-post`, no page reloads
- [x] GP Breakdown modal — loaded on-demand via `htmx.ajax` (`/gp-breakdown`)
- [x] NG3 assets copied to `app/static/images/` and served via Flask static

---

## Phase 2: Hypermedia Economy & Production ✅
**Goal:** Resource engine using HTMX partials.

- [x] Resource footer with per-resource net income/consumption rates (`+X/h` / `-X/h`)
- [x] `economy` blueprint — `NaturalResource`, `NationFactory` models; 12 land columns on Nation
- [x] Land page (`/land`) — Expand Borders, Colonists (tier 6+), Buy Cleared Land, Build Urban Areas
- [x] Discovery engine (`app/game/discovery.py`) — continent-weighted terrain distribution and natural resource discovery rolls; `roll_expansion` / `roll_colonization`
- [x] Factory definitions (`app/game/factories.py`) — 9 factory types (Farm, Windmill, Quarry, Consumer Factory, Foundry, Munitions Plant, Oil Refinery, Nuclear Plant, WHZ Lab)
- [x] Industry page (`/industry`) — production capacity progress bar, hours input, collect route with Alpine.js filter by output type
- [x] Flask-APScheduler background task — increments all factory `production_capacity` by 1/hour (capped at 24)
- [x] Starter factories seeded on registration (2 farms, 1 windmills, 1 quarries)
- [x] Industry page two-tab layout — Collect tab (existing) + Build tab (Alpine.js reactive cost preview, tier gate, HTMX OOB swap)
- [x] `FactoryDef` extended with `build_cost`, `land_required`, `gp_value`; all 9 factories populated from NG3 data
- [x] `POST /industry/build` route — validates tier/land/resources, deducts costs, upserts `NationFactory`, updates `factory_gp`, returns partial (reopens Build tab)

---

## Phase 3: Real-Time Military Engine 🔧 (In Progress)
**Goal:** Combat loop with HTMX polling.

### Unit System
- [x] Unit definitions (`app/game/units.py`) — all NG3 unit types with stats, abilities, costs, upkeep
- [x] `Division` and `Unit` models — division management (create, rename, disband, mobilize/demobilize)
- [x] `RecruitmentQueue` model — timed recruitment with queue limit (max 10), 50% refund on cancel
- [x] Recruitment page (`/military/recruitment`) — tier-gated unit shop, live countdown timers
- [x] Background task processes recruitment queue every 60s, awards military GP on completion
- [x] Military upkeep task (hourly) — deducts upkeep resources; attrition (10% max HP) if nation can't afford
- [x] Unit management — move between divisions, rename, disband (with military GP update)
- [x] Unit state locking — cannot move/disband units in mobilized divisions

### Combat Engine
- [x] NG3 combat formulas ported to Python (`app/game/combat.py`)
  - Damage: `FP×10 − Armour×5 + randint(-4,+4)`
  - d100 hit roll with maneuver modifier: critical (≥90, ×1.5), graze (1–10, ×0.5), miss (≤0, ×0)
  - Type-based FP/armour multipliers, defending bonus (AllStatsMultiplier), support damage reduction, maneuver buffs/debuffs
- [x] Pool-based initiative selection — all alive units weighted by effective maneuver, one attack per tick, no retaliation
- [x] Retreat mechanic — side retreats when strength drops below 1/3 of opponent's
- [x] Immediate battle end when last enemy unit is destroyed (same tick)
- [x] Combat detail popup — full damage calculation breakdown (d20 button per log entry, Alpine.js modal outside HTMX poll zone)
- [x] Unit identifying indices in battle logs — `"{unitName} ({divisionName}-{index})"`

### Battle UI
- [x] Battle page (`/military/battle/<id>`) with HTMX 2s polling for live battles
- [x] NG3-style 3-column layout: Defender (blue, left) | Combat Log (center) | Attacker (red, right)
- [x] Strength bar, colored stat boxes (FP/AR/MAN/HP), unit index subscripts
- [x] Log ordering by ID (stable within-tick ordering)

### Battle State Management
- [x] Unit snapshots saved on battle end — finished battles show historical unit state, immune to future division changes
- [x] Post-battle cleanup: destroyed units disbanded (military GP updated), survivors healed to full HP
- [x] `battle_type` column (pvp/pve) on Battle model

### PvE (Peacekeeping)
- [x] Peacekeeping deployment — generates half-strength NPC "Insurgent Forces" division mirroring player's unit types
- [x] NPC nation/user system (`_system_npc` / `Insurgents`)
- [x] NPC division deleted immediately after PvE battle ends
- [x] PvE battle log cleanup task (every 24h) — deletes finished PvE battles older than 2 weeks

### Military Overview
- [x] Division tabs with Alpine.js state preserved across HTMX swaps (x-data outside swap zone, innerHTML swap)
- [x] Unit cards with HP bar, stat bars, type badge, level/XP
- [x] Resource footer refresh on military GP changes
- [x] Equipment system - Unintended consequences notwithstanding!!!
- [x] Battle history / reports listing page
- [x] Continent/equipment combat buffs


---

## Phase 4: Market & Growth Logic ⬜
**Goal:** Secure, transactional social features.

- [x] Global market listing UI with HTMX resource filter (`/market?resource=metal`)
- [x] Atomic trade transactions in Flask (SQLAlchemy)
- [x] tiers, population growth setting (urban land expansion cost)

---

## Phase 5: Optimization & Visual Polish ✅
**Goal:** Performance and UX refinement.

- [x] Alpine.js tooltips on resource icons (replace JS fetch listeners)
- [x] Flask-Caching for static data (continent weights, unit base stats)
- [x] Tailwind CSS JIT bundle optimization
- [x] Gunicorn + Nginx production deployment config
- [x] Docker compose compatibility w/ separate database container

Future:
- Wars
- unit leveling (level bonuses are unit-innate)
- Events (a la 2.0)
- Alliance leaderboard — server-rendered table
- Live alliance search — `hx-trigger="keyup changed delay:500ms"`\
- Rate Limiting