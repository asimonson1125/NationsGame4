import pytest
from sqlalchemy import text, create_engine
from app import create_app, db as _db
from app.models import User, Nation
from run import create_partitions


def ensure_test_db_exists():
    """Connect to default DB and create the test DB if missing."""
    from config import config
    import os
    uri = config['testing'].SQLALCHEMY_DATABASE_URI
    
    # Extract base URI and target DB name
    base_uri, db_name = uri.rsplit('/', 1)
    
    # Try connecting to 'postgres' first, then fall back to the main app DB
    # to issue the CREATE DATABASE command.
    potential_admins = ['postgres', os.environ.get('POSTGRES_DB', 'ng4')]
    
    for admin_db in potential_admins:
        admin_uri = f"{base_uri}/{admin_db}"
        try:
            engine = create_engine(admin_uri, isolation_level='AUTOCOMMIT')
            with engine.connect() as conn:
                exists = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname='{db_name}'")).scalar()
                if not exists:
                    conn.execute(text(f"CREATE DATABASE {db_name}"))
                return # Success
        except Exception:
            continue
    
    print(f"Warning: Could not ensure test database '{db_name}' exists. Tests may fail if it hasn't been created manually.")


@pytest.fixture(scope='session')
def app():
    """Create the Flask app once per test session."""
    ensure_test_db_exists()
    app = create_app('testing')
    yield app


@pytest.fixture(autouse=True)
def setup_db(app):
    """Create all tables and partitions before each test and drop them after."""
    with app.app_context():
        _db.create_all()
        create_partitions()
        yield
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def nation(app):
    """Create a test user + nation and return the nation."""
    u = User(username='tester', email='test@test.com')
    u.set_password('password')
    _db.session.add(u)
    _db.session.flush()
    n = Nation(
        user_id=u.id, name='TestNation', continent='Westberg',
        money=1_000_000, food=100_000, power=100_000,
        building_materials=100_000, consumer_goods=100_000,
        metal=100_000, ammunition=100_000, fuel=100_000,
        uranium=1000,
    )
    _db.session.add(n)
    _db.session.commit()
    return n


@pytest.fixture()
def auth_client(app, client, nation):
    """A test client already logged in as the test nation's user."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(nation.user_id)
    return client


@pytest.fixture()
def admin_user(app):
    """Create an admin user + nation and return the user."""
    u = User(username='admin', email='admin@test.com', is_admin=True)
    u.set_password('password')
    _db.session.add(u)
    _db.session.flush()
    n = Nation(
        user_id=u.id, name='AdminNation', continent='Westberg',
        money=999_999, food=999_999, power=999_999,
    )
    _db.session.add(n)
    _db.session.commit()
    return u


@pytest.fixture()
def admin_client(app, client, admin_user):
    """A test client logged in as an admin user."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_user.id)
    return client
