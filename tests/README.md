# Tests

## Prerequisites

```bash
pip3 install pytest
```

All other dependencies (Flask, SQLAlchemy, etc.) are the same as the main app.

## Running Tests

From the project root (`NG4/`):

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run a specific test file
python3 -m pytest tests/test_units.py -v
python3 -m pytest tests/test_combat.py -v
python3 -m pytest tests/test_models.py -v
python3 -m pytest tests/test_routes.py -v
python3 -m pytest tests/test_tasks.py -v

# Run a specific test class or function
python3 -m pytest tests/test_combat.py::TestManeuverRoll -v
python3 -m pytest tests/test_routes.py::TestRecruitment::test_recruit_unit_success -v

# Run with short summary
python3 -m pytest tests/ --tb=short
```

## Test Structure

| File | What it covers |
|------|----------------|
| `conftest.py` | Shared fixtures: in-memory DB, test app, auth client, test nation |
| `test_units.py` | Unit definitions — counts, stat ranges, NG3 data spot-checks |
| `test_combat.py` | Combat engine — ability parsing, effective stats, maneuver rolls, damage |
| `test_models.py` | Database models — Division, Unit, RecruitmentQueue, Battle, CombatReport |
| `test_routes.py` | HTTP routes — overview, division CRUD, recruitment, unit management |
| `test_tasks.py` | Background tasks — recruitment queue processing, upkeep/attrition |

## Notes

- Tests use a **PostgreSQL database** (configured via `TestingConfig` in `config.py`) — the dev DB is never touched.
- Each test rolls back its transaction so tests are isolated.
- CSRF is disabled in the test app config.
- The `auth_client` fixture provides a pre-authenticated test client with a nation that has plenty of resources.
- Combat tests use `FakeUnit` objects that mirror DB Unit rows without needing the database.
