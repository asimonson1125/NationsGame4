"""
Delete a nation and its user account, removing all related records.
Usage: python3 adhoc/delete_nation.py <nation_name>
"""
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from run import app
from app.models import (
    Nation, User, NaturalResource, NationFactory, Division, Unit,
    RecruitmentQueue, FactoryBuildQueue, Equipment, TradeOrder, TradeExecution,
    Message, NationBuilding, BuildingUpgradeQueue, MissionOffer, MissionRecord,
    AllianceApplication, Alliance, War, WarBattle, WarDeploymentQueue,
    Battle, CombatReport
)
from app import db
from sqlalchemy import text

name = sys.argv[1] if len(sys.argv) > 1 else None
if not name:
    print("Usage: python3 adhoc/delete_nation.py <nation_name>")
    sys.exit(1)

with app.app_context():
    nation = Nation.query.filter_by(name=name).first()
    if not nation:
        print("Nation not found.")
        sys.exit(1)

    nid = nation.id
    uid = nation.user_id
    print(f"Deleting nation '{name}' (id={nid}, user_id={uid})...")

    # Wars (delete child rows first, then the wars)
    war_ids = [w.id for w in War.query.filter(
        (War.attacker_nation_id == nid) | (War.defender_nation_id == nid)
    ).all()]
    if war_ids:
        WarDeploymentQueue.query.filter(WarDeploymentQueue.war_id.in_(war_ids)).delete(synchronize_session=False)
        WarBattle.query.filter(WarBattle.war_id.in_(war_ids)).delete(synchronize_session=False)
    WarDeploymentQueue.query.filter_by(deploying_nation_id=nid).delete(synchronize_session=False)
    War.query.filter(
        (War.attacker_nation_id == nid) | (War.defender_nation_id == nid)
    ).delete(synchronize_session=False)

    # Old battle system — use raw SQL for partitioned tables
    battle_ids = db.session.execute(
        text("SELECT id FROM battles WHERE attacker_nation_id = :n OR defender_nation_id = :n"),
        {'n': nid}
    ).scalars().all()
    if battle_ids:
        db.session.execute(
            text("DELETE FROM combat_reports WHERE battle_id = ANY(:ids)"),
            {'ids': list(battle_ids)}
        )
    db.session.execute(
        text("DELETE FROM battles WHERE attacker_nation_id = :n OR defender_nation_id = :n"),
        {'n': nid}
    )

    # Units — null equipment FKs before deleting equipment
    Unit.query.filter_by(nation_id=nid).update(
        {'weapon_id': None, 'accessory_id': None, 'armour_eq_id': None},
        synchronize_session=False
    )
    Unit.query.filter_by(nation_id=nid).delete(synchronize_session=False)
    Division.query.filter_by(nation_id=nid).delete(synchronize_session=False)
    Equipment.query.filter_by(nation_id=nid).delete(synchronize_session=False)

    RecruitmentQueue.query.filter_by(nation_id=nid).delete(synchronize_session=False)
    FactoryBuildQueue.query.filter_by(nation_id=nid).delete(synchronize_session=False)
    NationFactory.query.filter_by(nation_id=nid).delete(synchronize_session=False)
    NaturalResource.query.filter_by(nation_id=nid).delete(synchronize_session=False)
    NationBuilding.query.filter_by(nation_id=nid).delete(synchronize_session=False)
    BuildingUpgradeQueue.query.filter_by(nation_id=nid).delete(synchronize_session=False)

    TradeOrder.query.filter_by(nation_id=nid).delete(synchronize_session=False)
    TradeExecution.query.filter(
        (TradeExecution.buyer_nation_id == nid) | (TradeExecution.seller_nation_id == nid)
    ).delete(synchronize_session=False)
    Message.query.filter(
        (Message.recipient_id == nid) | (Message.sender_id == nid)
    ).delete(synchronize_session=False)

    MissionOffer.query.filter_by(nation_id=nid).delete(synchronize_session=False)
    MissionRecord.query.filter_by(nation_id=nid).delete(synchronize_session=False)
    AllianceApplication.query.filter_by(nation_id=nid).delete(synchronize_session=False)

    # Null alliance founder reference if this nation founded one
    Alliance.query.filter_by(founder_id=nid).update({'founder_id': None}, synchronize_session=False)

    db.session.delete(nation)
    User.query.filter_by(id=uid).delete(synchronize_session=False)
    db.session.commit()
    print("Done.")
