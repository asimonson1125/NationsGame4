import threading
from datetime import datetime, timezone
from flask_apscheduler import APScheduler

scheduler = APScheduler()
_register_lock = threading.Lock()
_registered = False


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


def tick_nation(nation, *, skip_military=False):
    """Apply one hourly tick to a single nation.

    1. Population resource effects (tax income, power/CG consumption)
    2. Food priority — population eats first; scaled starvation on deficit
    3. Population growth (only when food is sufficient)
    4. Tier update
    5. Military upkeep — deducted from post-population resources
    6. Attrition (can't afford) or healing (non-combat, upkeep met)

    Returns (grown, starved) citizen counts.
    """
    from .models import Unit
    from .game.population import (get_population_effects, process_growth,
                                  process_starvation, compute_tier,
                                  compute_population_gp)
    from .helpers import compute_total_upkeep
    from . import db

    effects = get_population_effects(nation.population)

    # 1. Non-food resource effects
    for res, amount in effects.items():
        if res == 'food':
            continue
        new_val = nation.get_resource(res) + amount
        setattr(nation, res, max(0, new_val))

    # 2. Food priority: population eats first
    food_needed = abs(effects.get('food', 0))
    food_available = nation.food or 0
    grown = 0
    starved = 0

    if food_needed > 0 and food_available < food_needed:
        deficit_fraction = (food_needed - food_available) / food_needed
        nation.food = 0
        starved = process_starvation(nation, deficit_fraction)
    else:
        nation.food = max(0, food_available - food_needed)
        grown = process_growth(nation)

    # 3. Tier update
    nation.tier = compute_tier(nation.population)
    nation.population_gp = compute_population_gp(nation.population)

    if skip_military:
        return grown, starved

    # 4. Military upkeep
    total_upkeep = compute_total_upkeep(nation.id)
    if not total_upkeep:
        _heal_non_combat_units(nation.id, db)
        return grown, starved

    can_afford = all(
        nation.get_resource(res) >= amount
        for res, amount in total_upkeep.items()
    )

    if can_afford:
        for res, amount in total_upkeep.items():
            nation.add_resource(res, -amount)
        _heal_non_combat_units(nation.id, db)
    else:
        units = Unit.query.filter_by(nation_id=nation.id).filter(Unit.hp > 0).all()
        for unit in units:
            eff_max = unit.effective_max_hp
            attrition = max(1, eff_max // 10)
            floor = eff_max // 5
            if unit.hp > floor:
                unit.hp = max(floor, unit.hp - attrition)

    return grown, starved


def process_hourly_tick():
    """Runs hourly. Increments factory capacity then ticks all nations."""
    from .models import Nation, NationFactory, User
    from . import db
    with scheduler.app.app_context():
        npc_user = User.query.filter_by(username='_system_npc').first()
        npc_nation_id = npc_user.nation.id if npc_user and npc_user.nation else None

        vacation_nation_ids = (
            db.session.query(Nation.id)
            .join(User, User.id == Nation.user_id)
            .filter(User.vacation_mode == True)
            .subquery()
        )
        vacation_ids = set(
            row[0] for row in
            db.session.query(vacation_nation_ids.c.id).all()
        )

        # Factory capacity increment (bulk UPDATE, excludes vacation nations)
        NationFactory.query.filter(
            NationFactory.count > 0,
            NationFactory.production_capacity < 24,
            ~NationFactory.nation_id.in_(db.session.query(vacation_nation_ids.c.id))
        ).update({'production_capacity': NationFactory.production_capacity + 1})
        db.session.commit()

        # Nation tick loop
        batch_size = 100
        last_id = 0
        while True:
            nations = Nation.query.filter(Nation.id > last_id).order_by(Nation.id).limit(batch_size).all()
            if not nations:
                break
            for nation in nations:
                if nation.id in vacation_ids:
                    last_id = nation.id
                    continue
                tick_nation(nation, skip_military=(nation.id == npc_nation_id))
                last_id = nation.id
            db.session.commit()


def _heal_non_combat_units(nation_id, db):
    """Restore full effective HP to damaged units not currently in combat.

    Uses effective_max_hp (includes equipment buffs) so must load via Python.
    """
    from .models import Unit, Division

    healable = (
        Unit.query
        .outerjoin(Division, db.and_(
            Division.id == Unit.division_id,
            Division.nation_id == Unit.nation_id,
        ))
        .filter(
            Unit.nation_id == nation_id,
            Unit.hp > 0,
            Unit.hp < Unit.max_hp,
            db.or_(Unit.division_id.is_(None), Division.in_combat == False),
        )
        .all()
    )
    for unit in healable:
        unit.hp = unit.effective_max_hp


def process_factory_queue():
    """Runs every 60s. Completes factory build entries whose timer has expired."""
    from .models import FactoryBuildQueue, Nation
    from .helpers import grant_factories
    from . import db
    with scheduler.app.app_context():
        now = datetime.now(timezone.utc)
        ready = FactoryBuildQueue.query.filter(FactoryBuildQueue.completes_at <= now).all()
        for entry in ready:
            nation = db.session.get(Nation, entry.nation_id)
            if nation:
                grant_factories(nation, [(entry.factory_key, entry.quantity)])
            db.session.delete(entry)
        if ready:
            db.session.commit()


def process_war_deployments():
    """Runs every 60s. Fires battles when war deployments arrive."""
    from .models import WarDeploymentQueue, War, Division, Unit, Battle, WarBattle, Message, Nation
    from . import db
    with scheduler.app.app_context():
        now = datetime.now(timezone.utc)
        ready = WarDeploymentQueue.query.filter(
            WarDeploymentQueue.status == 'traveling',
            WarDeploymentQueue.arrives_at <= now,
        ).all()

        for entry in ready:
            war = db.session.get(War, entry.war_id)
            if not war or war.status != 'active':
                entry.status = 'arrived'
                continue

            deploying_id = entry.deploying_nation_id
            side = 'attacker' if deploying_id == war.attacker_nation_id else 'defender'
            opponent_id = (war.defender_nation_id if side == 'attacker'
                           else war.attacker_nation_id)

            atk_div = db.session.get(Division, (entry.division_id, deploying_id))
            if not atk_div:
                entry.status = 'arrived'
                continue

            # Find opponent's defensive division
            def_div = Division.query.filter_by(
                nation_id=opponent_id, is_defensive=True, mobilization_state='mobilized'
            ).filter(Division.in_combat == False).first()

            link = f'<a href="/war/{war.id}" class="text-amber-400 hover:text-amber-300 underline">View War</a>'

            if not def_div:
                # Unopposed — create an instantly-resolved battle for the record
                from .game.war import credit_war_victory
                atk_nation = db.session.get(Nation, deploying_id)
                def_nation = db.session.get(Nation, opponent_id)

                def_name = def_nation.name if def_nation else str(opponent_id)
                battle = Battle(
                    attacker_division_id=atk_div.id,
                    defender_division_id=None,
                    attacker_division_name=atk_div.name,
                    defender_division_name='(Unopposed)',
                    attacker_nation_id=deploying_id,
                    defender_nation_id=opponent_id,
                    attacker_nation_name=atk_nation.name if atk_nation else str(deploying_id),
                    defender_nation_name=def_name,
                    name=f'{war.name} \u2014 Assault on {def_name} (Unopposed)',
                    battle_type='pvp',
                    location=def_nation.continent if def_nation else None,
                    status='finished',
                    winner='attacker',
                    finished_at=now,
                )
                db.session.add(battle)
                db.session.flush()

                war_battle = WarBattle(
                    war_id=war.id,
                    battle_id=battle.id,
                    attacker_nation_id=deploying_id,
                    side=side,
                )
                db.session.add(war_battle)
                db.session.flush()

                credit_war_victory(war, war_battle, 'attacker')

                deploying_name = atk_nation.name if atk_nation else str(deploying_id)
                db.session.add(Message(
                    sender_id=None,
                    recipient_id=deploying_id,
                    subject=f'Unopposed Victory — {war.name}',
                    body=f'Your forces met no resistance and claimed an unopposed victory.\n\n{link}',
                    message_type='system',
                ))
                db.session.add(Message(
                    sender_id=None,
                    recipient_id=opponent_id,
                    subject=f'Overrun — {war.name}',
                    body=f'{deploying_name} attacked our nation while we had no defensive division set to coordinate a response. An unopposed victory was awarded to them.\n\n{link}',
                    message_type='system',
                ))
                entry.status = 'arrived'

                _check_war_settlement_available(war, link)
                continue

            # Create the battle
            atk_nation = db.session.get(Nation, deploying_id)
            def_nation = db.session.get(Nation, opponent_id)
            def_name = def_nation.name if def_nation else str(opponent_id)
            battle = Battle(
                attacker_division_id=atk_div.id,
                defender_division_id=def_div.id,
                attacker_division_name=atk_div.name,
                defender_division_name=def_div.name,
                attacker_nation_id=deploying_id,
                defender_nation_id=opponent_id,
                attacker_nation_name=atk_nation.name if atk_nation else str(deploying_id),
                defender_nation_name=def_name,
                name=f'{war.name} \u2014 Assault on {def_name}',
                battle_type='pvp',
                location=def_nation.continent if def_nation else None,
            )
            db.session.add(battle)
            db.session.flush()

            war_battle = WarBattle(
                war_id=war.id,
                battle_id=battle.id,
                attacker_nation_id=deploying_id,
                side=side,
            )
            db.session.add(war_battle)

            atk_div.in_combat = True
            def_div.in_combat = True
            entry.status = 'arrived'

        if ready:
            db.session.commit()


def _check_war_settlement_available(war, link):
    """Send a notification if the 3-victory threshold has just been crossed."""
    from .models import Message
    from . import db
    from .game.war import compute_war_scores
    scores = compute_war_scores(war)
    if scores['attacker_can_demand']:
        db.session.add(Message(
            sender_id=None,
            recipient_id=war.attacker_nation_id,
            subject=f'Settlement Available — {war.name}',
            body=f'You have a lead of 3+ victories. You may now demand war compensation or annexation.\n\n{link}',
            message_type='system',
        ))
    if scores['defender_can_demand']:
        db.session.add(Message(
            sender_id=None,
            recipient_id=war.defender_nation_id,
            subject=f'Settlement Available — {war.name}',
            body=f'You have a lead of 3+ victories. You may now demand war compensation or annexation.\n\n{link}',
            message_type='system',
        ))


def process_building_upgrades():
    """Runs every 60s. Completes building upgrades whose timer has expired."""
    from .models import BuildingUpgradeQueue, NationBuilding, Nation
    from .game.buildings import BUILDING_DEFS
    from . import db
    with scheduler.app.app_context():
        now = datetime.now(timezone.utc)
        ready = BuildingUpgradeQueue.query.filter(BuildingUpgradeQueue.completes_at <= now).all()
        for entry in ready:
            nb = NationBuilding.query.filter_by(
                nation_id=entry.nation_id, building_key=entry.building_key
            ).first()
            if nb:
                nb.level = entry.target_level
                bdef = BUILDING_DEFS.get(entry.building_key)
                nation = db.session.get(Nation, entry.nation_id)
                if nation and bdef and entry.target_level <= len(bdef.gp_per_level):
                    nation.building_gp = (nation.building_gp or 0) + bdef.gp_per_level[entry.target_level - 1]
            db.session.delete(entry)
        if ready:
            db.session.commit()


def reset_daily_counters():
    """Runs daily at midnight UTC. Resets per-nation daily counters."""
    from .models import Nation
    from . import db
    with scheduler.app.app_context():
        Nation.query.filter(Nation.mission_skips_today > 0).update(
            {'mission_skips_today': 0})
        db.session.commit()


def cleanup_pve_battles():
    """Runs daily. Deletes PvE battles (and NPC divisions/units) older than 2 weeks."""
    from .models import Battle, CombatReport, Division, Unit
    from . import db
    from datetime import timedelta
    with scheduler.app.app_context():
        cutoff = datetime.now(timezone.utc) - timedelta(weeks=2)
        old_pve = Battle.query.filter(
            Battle.battle_type.in_(('peacekeeping', 'pve_mission')),
            Battle.status == 'finished',
            Battle.finished_at <= cutoff,
        ).all()

        for battle in old_pve:
            npc_div_id = battle.defender_division_id
            npc_nation_id = battle.defender_nation_id

            # Delete combat reports and battle first (removes FK references to division)
            CombatReport.query.filter_by(battle_id=battle.id, attacker_nation_id=battle.attacker_nation_id).delete()
            Battle.query.filter_by(id=battle.id, attacker_nation_id=battle.attacker_nation_id).delete()
            db.session.flush()

            # Now safe to delete the NPC division and its units
            Unit.query.filter_by(division_id=npc_div_id, nation_id=npc_nation_id).delete()
            Division.query.filter_by(id=npc_div_id, nation_id=npc_nation_id).delete()

        if old_pve:
            db.session.commit()


def register_tasks(app):
    global _registered
    with _register_lock:
        if _registered:
            return
        _registered = True

    scheduler.init_app(app)

    # ── Hourly tick (factory capacity + nation simulation) ──
    scheduler.add_job(id='hourly_tick', func=process_hourly_tick,
                      trigger='cron', minute=0, replace_existing=True)

    # ── Frequent tasks (keep as interval) ──
    scheduler.add_job(id='process_recruitment', func=process_recruitment_queue,
                      trigger='interval', seconds=60, replace_existing=True)
    scheduler.add_job(id='process_factory_build', func=process_factory_queue,
                      trigger='interval', seconds=60, replace_existing=True)
    scheduler.add_job(id='process_building_upgrades', func=process_building_upgrades,
                      trigger='interval', seconds=60, replace_existing=True)
    scheduler.add_job(id='process_war_deployments', func=process_war_deployments,
                      trigger='interval', seconds=60, replace_existing=True)
    scheduler.add_job(id='process_combat', func=process_combat_rounds,
                      trigger='interval', seconds=10, replace_existing=True,
                      max_instances=1, coalesce=True)

    # ── Daily tasks (midnight UTC) ──
    scheduler.add_job(id='reset_daily', func=reset_daily_counters,
                      trigger='cron', hour=0, minute=0, replace_existing=True)
    scheduler.add_job(id='cleanup_pve', func=cleanup_pve_battles,
                      trigger='cron', hour=0, minute=0, replace_existing=True)

    if not scheduler.running:
        try:
            scheduler.start()
        except Exception:
            # Already started in another context
            pass
