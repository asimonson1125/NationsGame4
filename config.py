import os
from datetime import timedelta
from dotenv import load_dotenv
from app.game.changelog import CHANGELOG

# Load .env file if it exists
load_dotenv()

_version = CHANGELOG[0]['version'].replace('.', '_').replace('-', '_') if CHANGELOG else '0'

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {'options': '-c timezone=utc'}
    }
    SCHEDULER_API_ENABLED = False
    CACHE_DEFAULT_TIMEOUT = 300
    CACHE_KEY_PREFIX = f'ng4_{_version}_'
    
    # Upload configuration
    _basedir = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(_basedir, 'uploads'))
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB
    
    # Session and Cookie configuration
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'

class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # Disable secure cookies for local development
    REMEMBER_COOKIE_SECURE = False
    # Default to localhost:5433 if not inside container
    _user = os.environ.get('POSTGRES_USER', 'ng4')
    _pw = os.environ.get('POSTGRES_PASSWORD', 'ng4')
    _db = os.environ.get('POSTGRES_DB', 'ng4')
    _port = os.environ.get('POSTGRES_PORT', '5433')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 
        f'postgresql://{_user}:{_pw}@localhost:{_port}/{_db}'
    )
    CACHE_TYPE = 'SimpleCache'


class ProductionConfig(Config):
    DEBUG = False
    _user = os.environ.get('POSTGRES_USER', 'ng4')
    _pw = os.environ.get('POSTGRES_PASSWORD', 'ng4')
    _db = os.environ.get('POSTGRES_DB', 'ng4')
    _port = os.environ.get('POSTGRES_PORT', '5433')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 
        f'postgresql://{_user}:{_pw}@localhost:{_port}/{_db}'
    )
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'RedisCache')
    CACHE_REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')


class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    WTF_CSRF_ENABLED = False
    # Use individual variables to construct test DB URI
    _user = os.environ.get('POSTGRES_USER', 'ng4')
    _pw = os.environ.get('POSTGRES_PASSWORD', 'ng4')
    _port = os.environ.get('POSTGRES_PORT', '5433')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'TEST_DATABASE_URL',
        f'postgresql://{_user}:{_pw}@localhost:{_port}/ng4_test'
    )
    CACHE_TYPE = 'SimpleCache'
    
    # Ensure DB_PARTITIONS is set for tests
    if 'DB_PARTITIONS' not in os.environ:
        os.environ['DB_PARTITIONS'] = '2'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
