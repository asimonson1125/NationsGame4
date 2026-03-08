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
- [x] Starter factories seeded on registration (10 farms, 5 windmills, 5 quarries)
- [x] Industry page two-tab layout — Collect tab (existing) + Build tab (Alpine.js reactive cost preview, tier gate, HTMX OOB swap)
- [x] `FactoryDef` extended with `build_cost`, `land_required`, `gp_value`; all 9 factories populated from NG3 data
- [x] `POST /industry/build` route — validates tier/land/resources, deducts costs, upserts `NationFactory`, updates `factory_gp`, returns partial (reopens Build tab)

---

## Phase 3: Real-Time Military Engine ⬜
**Goal:** Combat loop with SSE streaming.

- [ ] Port Maneuver Roll and Damage formulas to Python
- [ ] Battle polling — `GET /battle/status/<id>` via HTMX every 2s
- [ ] SSE streaming — Flask streams combat log fragments to HTMX listener
- [ ] Recruitment panel — hiring a unit swaps the Division List fragment

---

## Phase 4: Market & Alliance Logic ⬜
**Goal:** Secure, transactional social features.

- [ ] Global market listing UI with HTMX resource filter (`/market?resource=metal`)
- [ ] Atomic trade transactions in Flask (SQLAlchemy)
- [ ] Alliance leaderboard — server-rendered table
- [ ] Live alliance search — `hx-trigger="keyup changed delay:500ms"`

---

## Phase 5: Optimization & Visual Polish ⬜
**Goal:** Performance and UX refinement.

- [ ] Alpine.js tooltips on resource icons (replace JS fetch listeners)
- [ ] Flask-Caching for static data (continent weights, unit base stats)
- [ ] Tailwind CSS JIT bundle optimization
- [ ] Gunicorn + Nginx production deployment config
