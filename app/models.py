import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
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
    demonym = db.Column(db.String(120), default='')
    flag_url = db.Column(db.String(500), default='')
    leader = db.Column(db.String(120), default='')
    population = db.Column(db.BigInteger, default=1_000_000)
    tier = db.Column(db.Integer, default=1)
    founded_date = db.Column(db.Date, default=date.today)
    description = db.Column(db.Text, default='')
    continent = db.Column(db.String(100), default='')
    growth_rate = db.Column(db.Integer, default=50)  # 0-100 percent
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
    power = db.Column(db.Float, default=2500.0)
    building_materials = db.Column(db.Float, default=2500.0)
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

    # Loot tokens (for equipment crates)
    loot_tokens = db.Column(db.Float, default=0.0)

    natural_resources = db.relationship('NaturalResource', backref='nation_ref', lazy='dynamic')
    factories = db.relationship('NationFactory', backref='nation_ref', lazy='dynamic')
    divisions = db.relationship('Division', backref='nation_ref', lazy='dynamic')
    units = db.relationship('Unit', backref='nation_ref', lazy='dynamic')
    recruitment_queue = db.relationship('RecruitmentQueue', backref='nation_ref', lazy='dynamic')
    build_queue = db.relationship('FactoryBuildQueue', backref='nation_ref', lazy='dynamic')
    equipment = db.relationship('Equipment', backref='nation_ref', lazy='dynamic')
    trade_orders = db.relationship('TradeOrder', backref='nation_ref', lazy='dynamic')
    messages_received = db.relationship('Message', foreign_keys='Message.recipient_id', backref='recipient_nation', lazy='dynamic')

    def get_resource(self, key):
        return getattr(self, key, 0) or 0

    def add_resource(self, key, amount):
        setattr(self, key, self.get_resource(key) + amount)

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
    is_admin = db.Column(db.Boolean, default=False)
    notifications_enabled = db.Column(db.Boolean, default=True)
    vacation_mode = db.Column(db.Boolean, default=False)
    nation = db.relationship('Nation', backref='user', uselist=False, lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Division(db.Model):
    __tablename__ = 'divisions'
    id = db.Column(db.Integer, primary_key=True)
    nation_id = db.Column(db.Integer, db.ForeignKey('nations.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False, default='New Division')
    mobilization_state = db.Column(db.String(20), default='demobilized')  # demobilized|mobilizing|mobilized
    in_combat = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    units = db.relationship('Unit', backref='division_ref', lazy='dynamic', order_by='Unit.id')


class Unit(db.Model):
    __tablename__ = 'units'
    id = db.Column(db.Integer, primary_key=True)
    nation_id = db.Column(db.Integer, db.ForeignKey('nations.id'), nullable=False)
    division_id = db.Column(db.Integer, db.ForeignKey('divisions.id'), nullable=True)
    unit_key = db.Column(db.String(50), nullable=False)
    custom_name = db.Column(db.String(120), default='')
    level = db.Column(db.Integer, default=1)
    xp = db.Column(db.Integer, default=0)
    firepower = db.Column(db.Integer, default=0)
    armour = db.Column(db.Integer, default=0)
    maneuver = db.Column(db.Integer, default=0)
    hp = db.Column(db.Integer, default=0)
    max_hp = db.Column(db.Integer, default=0)
    weapon_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=True)
    accessory_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=True)
    armour_eq_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=True)

    weapon = db.relationship('Equipment', foreign_keys=[weapon_id])
    accessory = db.relationship('Equipment', foreign_keys=[accessory_id])
    armour_eq = db.relationship('Equipment', foreign_keys=[armour_eq_id])

    @classmethod
    def create_from_def(cls, nation_id, unit_key, **overrides):
        from .game.units import UNIT_DEFS
        udef = UNIT_DEFS[unit_key]
        return cls(
            nation_id=nation_id, unit_key=unit_key,
            firepower=udef.firepower, armour=udef.armour,
            maneuver=udef.maneuver, hp=udef.max_hp, max_hp=udef.max_hp,
            **overrides,
        )

    @property
    def equipment_items(self):
        return [eq for eq in (self.weapon, self.accessory, self.armour_eq) if eq]

    def _eq_buff_total(self, buff_type):
        """Sum flat buff values of a given type across all equipped items."""
        total = 0
        for eq in self.equipment_items:
            for b in eq.buffs:
                if b.buff_type == buff_type:
                    total += b.value
        return total

    def _eq_hp_multiplier(self):
        """Multiplicative HP multiplier from all equipped items."""
        mult = 1.0
        for eq in self.equipment_items:
            for b in eq.buffs:
                if b.buff_type == 'HP':
                    mult *= b.value
        return mult

    @property
    def effective_firepower(self):
        return self.firepower + self._eq_buff_total('Firepower')

    @property
    def effective_armour(self):
        return self.armour + self._eq_buff_total('Armour')

    @property
    def effective_maneuver(self):
        return self.maneuver + self._eq_buff_total('Maneuver')

    @property
    def effective_max_hp(self):
        return round(self.max_hp * self._eq_hp_multiplier())


class RecruitmentQueue(db.Model):
    __tablename__ = 'recruitment_queue'
    id = db.Column(db.Integer, primary_key=True)
    nation_id = db.Column(db.Integer, db.ForeignKey('nations.id'), nullable=False)
    unit_key = db.Column(db.String(50), nullable=False)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completes_at = db.Column(db.DateTime, nullable=False)


class FactoryBuildQueue(db.Model):
    __tablename__ = 'factory_build_queue'
    id = db.Column(db.Integer, primary_key=True)
    nation_id = db.Column(db.Integer, db.ForeignKey('nations.id'), nullable=False)
    factory_key = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completes_at = db.Column(db.DateTime, nullable=False)


class Battle(db.Model):
    __tablename__ = 'battles'
    id = db.Column(db.Integer, primary_key=True)
    attacker_division_id = db.Column(db.Integer, nullable=True)
    defender_division_id = db.Column(db.Integer, nullable=True)
    attacker_division_name = db.Column(db.String(120), nullable=True)
    defender_division_name = db.Column(db.String(120), nullable=True)
    attacker_nation_id = db.Column(db.Integer, db.ForeignKey('nations.id'), nullable=False)
    defender_nation_id = db.Column(db.Integer, db.ForeignKey('nations.id'), nullable=False)
    status = db.Column(db.String(20), default='active')  # active|finished
    winner = db.Column(db.String(20), nullable=True)      # attacker|defender|null
    battle_type = db.Column(db.String(10), default='pvp')  # pvp|pve
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = db.Column(db.DateTime, nullable=True)
    attacker_snapshot = db.Column(db.Text, nullable=True)  # JSON unit state at battle end
    defender_snapshot = db.Column(db.Text, nullable=True)  # JSON unit state at battle end

    attacker_nation = db.relationship('Nation', foreign_keys=[attacker_nation_id])
    defender_nation = db.relationship('Nation', foreign_keys=[defender_nation_id])
    reports = db.relationship('CombatReport', backref='battle_ref', lazy='dynamic',
                              order_by='CombatReport.created_at')


class CombatReport(db.Model):
    __tablename__ = 'combat_reports'
    id = db.Column(db.Integer, primary_key=True)
    battle_id = db.Column(db.Integer, db.ForeignKey('battles.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text, nullable=True)  # JSON breakdown of combat calc
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Equipment(db.Model):
    __tablename__ = 'equipment'
    id = db.Column(db.Integer, primary_key=True)
    nation_id = db.Column(db.Integer, db.ForeignKey('nations.id'), nullable=False)
    equipment_type = db.Column(db.String(50), nullable=False)  # e.g. "Infantry Weapon"
    rarity = db.Column(db.String(20), nullable=False, default='Common')
    is_foil = db.Column(db.Boolean, default=False)
    buff_hash = db.Column(db.String(64), nullable=False)
    buff_json = db.Column(db.Text, nullable=False, default='[]')
    count = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('nation_id', 'equipment_type', 'rarity', 'is_foil', 'buff_hash'),
    )

    @property
    def buffs(self):
        """Deserialize buff_json into attribute-accessible objects."""
        return [SimpleNamespace(**b) for b in json.loads(self.buff_json or '[]')]


class TradeOrder(db.Model):
    __tablename__ = 'trade_orders'
    id = db.Column(db.Integer, primary_key=True)
    nation_id = db.Column(db.Integer, db.ForeignKey('nations.id'), nullable=False)
    resource_key = db.Column(db.String(50), nullable=False)
    resource_type = db.Column(db.String(10), nullable=False)   # commodity | natural
    order_type = db.Column(db.String(4), nullable=False)       # buy | sell
    price_per_unit = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    quantity_filled = db.Column(db.Integer, default=0)
    status = db.Column(db.String(10), default='open')          # open | filled | cancelled
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class TradeExecution(db.Model):
    __tablename__ = 'trade_executions'
    id = db.Column(db.Integer, primary_key=True)
    buyer_nation_id = db.Column(db.Integer, db.ForeignKey('nations.id'), nullable=False)
    seller_nation_id = db.Column(db.Integer, db.ForeignKey('nations.id'), nullable=False)
    resource_key = db.Column(db.String(50), nullable=False)
    resource_type = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_per_unit = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    fee = db.Column(db.Float, nullable=False)
    executed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    buyer_nation = db.relationship('Nation', foreign_keys=[buyer_nation_id])
    seller_nation = db.relationship('Nation', foreign_keys=[seller_nation_id])


class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('nations.id'), nullable=True)  # null = system
    recipient_id = db.Column(db.Integer, db.ForeignKey('nations.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='player')  # 'system' | 'player'
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    sender = db.relationship('Nation', foreign_keys=[sender_id])
    recipient = db.relationship('Nation', foreign_keys=[recipient_id], overlaps='messages_received,recipient_nation')


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
