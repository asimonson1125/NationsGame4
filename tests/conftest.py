import pytest
from app import create_app, db as _db
from app.models import User, Nation


@pytest.fixture(scope='session')
def app():
    """Create the Flask app once per test session with an in-memory SQLite DB."""
    app = create_app('testing')
    yield app


@pytest.fixture(autouse=True)
def setup_db(app):
    """Create all tables before each test and drop them after."""
    with app.app_context():
        _db.create_all()
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
