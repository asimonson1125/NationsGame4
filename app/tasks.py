from datetime import datetime, timezone
from flask_apscheduler import APScheduler
scheduler = APScheduler()


def increment_production_capacity():
    from .models import NationFactory
    from . import db
    with scheduler.app.app_context():
        NationFactory.query.filter(
            NationFactory.count > 0,
            NationFactory.production_capacity < 24
        ).update({'production_capacity': NationFactory.production_capacity + 1})
        db.session.commit()


def process_recruitment_queue():
    """Runs every 60s. Completes recruitment entries whose timer has expired."""
    from .models import RecruitmentQueue, Unit, Nation
    from .game.units import UNIT_DEFS
    from . import db
    with scheduler.app.app_context():
        now = datetime.now(timezone.utc)
        ready = RecruitmentQueue.query.filter(RecruitmentQueue.completes_at <= now).all()
        for entry in ready:
            udef = UNIT_DEFS.get(entry.unit_key)
            if not udef:
                db.session.delete(entry)
                continue
            unit = Unit.create_from_def(entry.nation_id, entry.unit_key)
            db.session.add(unit)
            # Add military GP
            nation = db.session.get(Nation, entry.nation_id)
            if nation:
                nation.military_gp = (nation.military_gp or 0) + udef.gp_value
            db.session.delete(entry)
        if ready:
            db.session.commit()


def process_combat_rounds():
    """Runs every 10s. Processes one combat round for each active battle."""
    from .models import Battle
    from .game.combat import process_battle_round
    from . import db
    with scheduler.app.app_context():
        active_battles = Battle.query.filter_by(status='active').all()
        for battle in active_battles:
            process_battle_round(battle, db.session)
        if active_battles:
            db.session.commit()


def process_population_tick():
    """Runs hourly. Applies population tax income and resource consumption."""
    from .models import Nation
    from .game.population import get_population_effects
    from . import db
    with scheduler.app.app_context():
        nations = Nation.query.all()
        for nation in nations:
            effects = get_population_effects(nation.population)
            for res, amount in effects.items():
                new_val = nation.get_resource(res) + amount
                setattr(nation, res, max(0, new_val))
        db.session.commit()


def deduct_military_upkeep():
    """Runs hourly. Deducts upkeep for all units. Units lose HP if nation can't afford."""
    from .models import Nation, Unit, User
    from .helpers import compute_total_upkeep
    from . import db
    with scheduler.app.app_context():
        # Exclude the system NPC nation — its divisions are disposable PvE opponents
        npc_user = User.query.filter_by(username='_system_npc').first()
        npc_nation_id = npc_user.nation.id if npc_user and npc_user.nation else None
        nations = Nation.query.filter(Nation.id != npc_nation_id).all() if npc_nation_id else Nation.query.all()
        for nation in nations:
            units = Unit.query.filter_by(nation_id=nation.id).filter(Unit.hp > 0).all()
            if not units:
                continue

            total_upkeep = compute_total_upkeep(nation.id)

            # Check if nation can afford
            can_afford = True
            for res, amount in total_upkeep.items():
                if nation.get_resource(res) < amount:
                    can_afford = False
                    break

            if can_afford:
                for res, amount in total_upkeep.items():
                    nation.add_resource(res, -amount)
            else:
                # Attrition: each unit loses 10% max HP
                for unit in units:
                    attrition = max(1, unit.max_hp // 10)
                    floor = unit.max_hp // 5  # 20% of max HP
                    if unit.hp > floor:
                        unit.hp = max(floor, unit.hp - attrition)

        db.session.commit()


def process_factory_queue():
    """Runs every 60s. Completes factory build entries whose timer has expired."""
    from .models import FactoryBuildQueue, NationFactory, Nation
    from .game.factories import FACTORY_DEFS
    from . import db
    with scheduler.app.app_context():
        now = datetime.utcnow()
        ready = FactoryBuildQueue.query.filter(FactoryBuildQueue.completes_at <= now).all()
        for entry in ready:
            fdef = FACTORY_DEFS.get(entry.factory_key)
            if not fdef:
                db.session.delete(entry)
                continue
            # Upsert NationFactory
            nf = NationFactory.query.filter_by(
                nation_id=entry.nation_id, factory_key=entry.factory_key
            ).first()
            if nf:
                nf.count += entry.quantity
            else:
                nf = NationFactory(
                    nation_id=entry.nation_id,
                    factory_key=entry.factory_key,
                    count=entry.quantity,
                    production_capacity=0,
                )
                db.session.add(nf)
            # Add factory GP
            nation = db.session.get(Nation, entry.nation_id)
            if nation:
                nation.factory_gp = (nation.factory_gp or 0) + entry.quantity * fdef.gp_value
            db.session.delete(entry)
        if ready:
            db.session.commit()


def cleanup_pve_battles():
    """Runs daily. Deletes PvE battles (and NPC divisions/units) older than 2 weeks."""
    from .models import Battle, CombatReport, Division, Unit
    from . import db
    from datetime import timedelta
    with scheduler.app.app_context():
        cutoff = datetime.now(timezone.utc) - timedelta(weeks=2)
        old_pve = Battle.query.filter(
            Battle.battle_type == 'pve',
            Battle.status == 'finished',
            Battle.finished_at <= cutoff,
        ).all()

        for battle in old_pve:
            # Delete combat reports
            CombatReport.query.filter_by(battle_id=battle.id).delete()

            # Delete NPC division and its units (defender side for peacekeeping)
            npc_div_id = battle.defender_division_id
            Unit.query.filter_by(division_id=npc_div_id).delete()
            Division.query.filter_by(id=npc_div_id).delete()

            db.session.delete(battle)

        if old_pve:
            db.session.commit()


def register_tasks(app):
    scheduler.init_app(app)

    # ── Hourly tasks (every hour at :00 UTC) ──
    scheduler.add_job(id='incr_prod_cap', func=increment_production_capacity,
                      trigger='cron', minute=0)
    scheduler.add_job(id='population_tick', func=process_population_tick,
                      trigger='cron', minute=0)
    scheduler.add_job(id='military_upkeep', func=deduct_military_upkeep,
                      trigger='cron', minute=0)

    # ── Frequent tasks (keep as interval) ──
    scheduler.add_job(id='process_recruitment', func=process_recruitment_queue,
                      trigger='interval', seconds=60)
    scheduler.add_job(id='process_factory_build', func=process_factory_queue,
                      trigger='interval', seconds=60)
    scheduler.add_job(id='process_combat', func=process_combat_rounds,
                      trigger='interval', seconds=10)

    # ── Daily tasks (midnight UTC) ──
    scheduler.add_job(id='cleanup_pve', func=cleanup_pve_battles,
                      trigger='cron', hour=0, minute=0)

    scheduler.start()
