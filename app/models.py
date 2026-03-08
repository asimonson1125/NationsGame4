from datetime import date
from . import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class Alliance(db.Model):
    __tablename__ = 'alliances'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    members = db.relationship('Nation', backref='alliance', lazy=True)


class Nation(db.Model):
    __tablename__ = 'nations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=False)
    flag_url = db.Column(db.String(500), default='')
    leader = db.Column(db.String(120), default='')
    population = db.Column(db.BigInteger, default=1_000_000)
    tier = db.Column(db.Integer, default=1)
    founded_date = db.Column(db.Date, default=date.today)
    description = db.Column(db.Text, default='')
    continent = db.Column(db.String(100), default='')
    alliance_id = db.Column(db.Integer, db.ForeignKey('alliances.id'), nullable=True)

    # Greatness Points components
    population_gp = db.Column(db.BigInteger, default=0)
    land_gp = db.Column(db.BigInteger, default=0)
    factory_gp = db.Column(db.BigInteger, default=0)
    building_gp = db.Column(db.BigInteger, default=0)
    military_gp = db.Column(db.BigInteger, default=0)

    # Core resources
    money = db.Column(db.Float, default=10_000.0)
    food = db.Column(db.Float, default=5_000.0)
    power = db.Column(db.Float, default=5_000.0)
    building_materials = db.Column(db.Float, default=1_000.0)
    consumer_goods = db.Column(db.Float, default=1_000.0)
    metal = db.Column(db.Float, default=500.0)
    fuel = db.Column(db.Float, default=500.0)
    ammunition = db.Column(db.Float, default=0.0)
    uranium = db.Column(db.Float, default=0.0)
    whz = db.Column(db.Float, default=0.0)

    # Land
    total_land = db.Column(db.BigInteger, default=0)
    cleared_land = db.Column(db.BigInteger, default=0)
    urban_areas = db.Column(db.BigInteger, default=0)
    used_land = db.Column(db.BigInteger, default=0)
    forest = db.Column(db.BigInteger, default=0)
    grassland = db.Column(db.BigInteger, default=0)
    jungle = db.Column(db.BigInteger, default=0)
    desert = db.Column(db.BigInteger, default=0)
    mountain = db.Column(db.BigInteger, default=0)
    tundra = db.Column(db.BigInteger, default=0)
    river = db.Column(db.BigInteger, default=0)
    lake = db.Column(db.BigInteger, default=0)

    natural_resources = db.relationship('NaturalResource', backref='nation_ref', lazy='dynamic')
    factories = db.relationship('NationFactory', backref='nation_ref', lazy='dynamic')

    @property
    def total_gp(self):
        return (self.population_gp + self.land_gp + self.factory_gp
                + self.building_gp + self.military_gp)


class NaturalResource(db.Model):
    __tablename__ = 'natural_resources'
    id = db.Column(db.Integer, primary_key=True)
    nation_id = db.Column(db.Integer, db.ForeignKey('nations.id'), nullable=False)
    resource_key = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Integer, default=0)
    __table_args__ = (db.UniqueConstraint('nation_id', 'resource_key'),)


class NationFactory(db.Model):
    __tablename__ = 'nation_factories'
    id = db.Column(db.Integer, primary_key=True)
    nation_id = db.Column(db.Integer, db.ForeignKey('nations.id'), nullable=False)
    factory_key = db.Column(db.String(50), nullable=False)
    count = db.Column(db.Integer, default=0)
    production_capacity = db.Column(db.Integer, default=0)
    __table_args__ = (db.UniqueConstraint('nation_id', 'factory_key'),)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    notifications_enabled = db.Column(db.Boolean, default=True)
    vacation_mode = db.Column(db.Boolean, default=False)
    nation = db.relationship('Nation', backref='user', uselist=False, lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
