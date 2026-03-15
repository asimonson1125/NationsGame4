"""Tests for the missions system — definitions, rolling logic, routes, and reward resolution."""
import json
import random
from datetime import datetime, timezone, timedelta

import pytest

from app import db
from app.game.missions import (
    MISSION_DEFS, get_eligible_missions, roll_two_missions, RARITY_WEIGHTS,
)
from app.game.units import UNIT_DEFS
from app.models import (
    Battle, Division, MissionOffer, MissionRecord, Nation, Unit, User,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def npc_nation(app):
    """Create the _system_npc user and nation used as mission opponent."""
    u = User(username='_system_npc', is_admin=False, is_system=True, vacation_mode=True)
    u.set_password('irrelevant')
    db.session.add(u)
    db.session.flush()
    n = Nation(user_id=u.id, name='NPC')
    db.session.add(n)
    db.session.commit()
    return n


@pytest.fixture()
def mobilized_div(app, nation):
    """A mobilized division with one alive infantry unit."""
    div = Division(nation_id=nation.id, name='Alpha', mobilization_state='mobilized')
    db.session.add(div)
    db.session.flush()
    unit = Unit(
        nation_id=nation.id, division_id=div.id, unit_key='infantry',
        firepower=3, armour=1, maneuver=2, hp=50, max_hp=50,
    )
    db.session.add(unit)
    db.session.commit()
    return div


@pytest.fixture()
def available_offer(app, nation):
    """An 'available' MissionOffer for slot 1 using a simple common mission."""
    offer = MissionOffer(
        nation_id=nation.id,
        slot=1,
        mission_key='riot_control',
        status='available',
    )
    db.session.add(offer)
    db.session.commit()
    return offer


# ── Mission Definition integrity ──────────────────────────────────────────────

class TestMissionDefs:
    def test_exactly_24_missions(self):
        assert len(MISSION_DEFS) == 24

    def test_all_rarities_represented(self):
        rarities = {m.rarity for m in MISSION_DEFS.values()}
        assert rarities == {'common', 'uncommon', 'rare', 'epic', 'legendary'}

    def test_rarity_counts(self):
        counts = {}
        for m in MISSION_DEFS.values():
            counts[m.rarity] = counts.get(m.rarity, 0) + 1
        assert counts['common'] == 5
        assert counts['uncommon'] == 9
        assert counts['rare'] == 4
        assert counts['epic'] == 4
        assert counts['legendary'] == 2

    def test_all_compositions_sum_to_100(self):
        bad = [
            (k, sum(v.enemy_composition.values()))
            for k, v in MISSION_DEFS.items()
            if sum(v.enemy_composition.values()) != 100
        ]
        assert bad == [], f"Compositions not summing to 100: {bad}"

    def test_all_enemy_unit_keys_in_unit_defs(self):
        missing = []
        for mkey, mdef in MISSION_DEFS.items():
            for ukey in mdef.enemy_composition:
                if ukey not in UNIT_DEFS:
                    missing.append((mkey, ukey))
        assert missing == [], f"Unknown unit keys in mission compositions: {missing}"

    def test_chapter_requires_keys_exist(self):
        for mdef in MISSION_DEFS.values():
            if mdef.chapter_requires:
                assert mdef.chapter_requires in MISSION_DEFS, (
                    f"{mdef.key}.chapter_requires='{mdef.chapter_requires}' not in MISSION_DEFS"
                )

    def test_chapter_chain_is_linear(self):
        """Verify the chapter chain: 1→2→3→4→5 with no cycles."""
        chapter_keys = ['chapter_1', 'chapter_2', 'chapter_3', 'chapter_4', 'chapter_5']
        for k in chapter_keys:
            assert k in MISSION_DEFS
        assert MISSION_DEFS['chapter_1'].chapter_requires is None
        assert MISSION_DEFS['chapter_2'].chapter_requires == 'chapter_1'
        assert MISSION_DEFS['chapter_3'].chapter_requires == 'chapter_2'
        assert MISSION_DEFS['chapter_4'].chapter_requires == 'chapter_3'
        assert MISSION_DEFS['chapter_5'].chapter_requires == 'chapter_4'

    def test_all_cooldown_hours_positive(self):
        for mdef in MISSION_DEFS.values():
            assert mdef.cooldown_hours > 0, f"{mdef.key} has cooldown <= 0"

    def test_all_enemy_counts_valid(self):
        for mdef in MISSION_DEFS.values():
            lo, hi = mdef.enemy_count
            assert lo >= 1, f"{mdef.key} min count < 1"
            assert hi >= lo, f"{mdef.key} max < min"

    def test_all_rewards_non_empty(self):
        for mdef in MISSION_DEFS.values():
            assert mdef.rewards, f"{mdef.key} has no rewards"

    def test_legendary_higher_cooldown_than_common(self):
        common = next(m for m in MISSION_DEFS.values() if m.rarity == 'common')
        legendary = next(m for m in MISSION_DEFS.values() if m.rarity == 'legendary')
        assert legendary.cooldown_hours > common.cooldown_hours

    def test_mission_keys_match_dict_keys(self):
        for key, mdef in MISSION_DEFS.items():
            assert mdef.key == key, f"Dict key '{key}' != MissionDef.key '{mdef.key}'"

    def test_all_missions_have_enemy_names(self):
        for key, mdef in MISSION_DEFS.items():
            assert mdef.enemy_name, f"{key} missing enemy_name"
            assert mdef.enemy_division_name, f"{key} missing enemy_division_name"

    def test_sector_missions_in_correct_location(self):
        assert MISSION_DEFS['thats_not_a_meteorite'].location == 'Westberg'
        assert MISSION_DEFS['jungle_fever'].location == 'Amarino'
        assert MISSION_DEFS['riot_control'].location == 'Westberg'


# ── NPC unit definitions ──────────────────────────────────────────────────────

class TestNpcUnitDefs:
    NPC_KEYS = [
        'rpg_infantry', 'mg_infantry', 'rioter', 'secret_agent', 'fsk',
        'navy_seals', 'black_horns', 'mobster', 'francisco_ace_of_spades',
        'desert_fox_bodyguard', 'leopard_2', 'gearhound_prototype',
        'sectoid', 'sectopod',
    ]
    PLAYER_KEYS = ['infantry', 'medic', 'national_guard', 'm1a1_abrahms',
                   'f_35_lightning_ii', 'sectoid']  # sectoid is NPC, not player

    def test_npc_keys_are_npc_only(self):
        for key in self.NPC_KEYS:
            assert key in UNIT_DEFS, f"'{key}' missing from UNIT_DEFS"
            assert UNIT_DEFS[key].npc_only, f"'{key}' should have npc_only=True"

    def test_player_units_not_npc_only(self):
        player_keys = ['infantry', 'medic', 'national_guard', 'm1a1_abrahms',
                       'f_35_lightning_ii']
        for key in player_keys:
            assert not UNIT_DEFS[key].npc_only, f"'{key}' should not be npc_only"

    def test_npc_units_have_zero_recruit_cost(self):
        for key in self.NPC_KEYS:
            udef = UNIT_DEFS[key]
            assert udef.recruit_cost == {}, f"'{key}' recruit_cost should be empty"

    def test_npc_units_have_unreachable_tier(self):
        for key in self.NPC_KEYS:
            assert UNIT_DEFS[key].tier > 10, f"'{key}' should have unreachable tier"

    def test_npc_unit_stats_are_positive(self):
        for key in self.NPC_KEYS:
            udef = UNIT_DEFS[key]
            assert udef.firepower >= 0
            assert udef.armour >= 0
            assert udef.maneuver >= 0
            assert udef.max_hp > 0

    def test_sectoid_stats_from_reference(self):
        """Sectoid: 8 FP, 8 ARM, 9 MAN, 50 HP — per MISSIONS_DATA.md."""
        u = UNIT_DEFS['sectoid']
        assert u.firepower == 8
        assert u.armour == 8
        assert u.maneuver == 9
        assert u.max_hp == 50

    def test_sectopod_stats_from_reference(self):
        """Sectopod: 10 FP, 10 ARM, 11 MAN, 300 HP — per MISSIONS_DATA.md."""
        u = UNIT_DEFS['sectopod']
        assert u.firepower == 10
        assert u.armour == 10
        assert u.maneuver == 11
        assert u.max_hp == 300

    def test_francisco_stats_from_reference(self):
        """Francesco: 6 FP, 1 ARM, 5 MAN, 300 HP — per MISSIONS_DATA.md."""
        u = UNIT_DEFS['francisco_ace_of_spades']
        assert u.firepower == 6
        assert u.armour == 1
        assert u.maneuver == 5
        assert u.max_hp == 300

    def test_total_unit_count_matches(self):
        """Regression: 39 player units + 14 NPC units."""
        npc = sum(1 for v in UNIT_DEFS.values() if v.npc_only)
        player = sum(1 for v in UNIT_DEFS.values() if not v.npc_only)
        assert npc == 14
        assert player == 39


# ── get_eligible_missions ─────────────────────────────────────────────────────

class TestGetEligibleMissions:
    def test_tier_1_excludes_chapter_1(self):
        """Chapter 1 requires tier 6 — should be excluded at tier 1."""
        eligible = get_eligible_missions(nation_tier=1, completed_keys=set())
        keys = {m.key for m in eligible}
        assert 'chapter_1' not in keys

    def test_tier_6_includes_chapter_1(self):
        eligible = get_eligible_missions(nation_tier=6, completed_keys=set())
        keys = {m.key for m in eligible}
        assert 'chapter_1' in keys

    def test_chapter_2_requires_chapter_1_complete(self):
        eligible = get_eligible_missions(nation_tier=6, completed_keys=set())
        keys = {m.key for m in eligible}
        assert 'chapter_2' not in keys

    def test_chapter_2_available_after_chapter_1(self):
        eligible = get_eligible_missions(
            nation_tier=6, completed_keys={'chapter_1'}
        )
        keys = {m.key for m in eligible}
        assert 'chapter_2' in keys

    def test_chapter_chain_gates_correctly(self):
        """chapter_5 only accessible after completing chapters 1–4."""
        for completed in [
            set(), {'chapter_1'}, {'chapter_1', 'chapter_2'},
            {'chapter_1', 'chapter_2', 'chapter_3'},
        ]:
            eligible = get_eligible_missions(nation_tier=10, completed_keys=completed)
            assert 'chapter_5' not in {m.key for m in eligible}

        all_four = {'chapter_1', 'chapter_2', 'chapter_3', 'chapter_4'}
        eligible = get_eligible_missions(nation_tier=10, completed_keys=all_four)
        assert 'chapter_5' in {m.key for m in eligible}

    def test_all_common_eligible_at_tier_1(self):
        """All common missions (except chapter_1) should be available at tier 1."""
        eligible = get_eligible_missions(nation_tier=1, completed_keys=set())
        common_eligible = [m for m in eligible if m.rarity == 'common']
        assert len(common_eligible) == 4  # 5 common minus chapter_1 (tier 6)


# ── roll_two_missions ─────────────────────────────────────────────────────────

class TestRollTwoMissions:
    def test_returns_two_for_eligible_pool(self):
        results = roll_two_missions(nation_tier=1, completed_keys=set(), exclude_keys=set())
        assert len(results) == 2

    def test_returns_distinct_missions(self):
        random.seed(42)
        for _ in range(20):
            results = roll_two_missions(nation_tier=1, completed_keys=set(), exclude_keys=set())
            keys = [m.key for m in results]
            assert len(keys) == len(set(keys)), "roll_two_missions returned duplicate missions"

    def test_excludes_specified_keys(self):
        random.seed(0)
        # Exclude all common missions — result should not contain any of them
        common_keys = {k for k, m in MISSION_DEFS.items() if m.rarity == 'common'}
        for _ in range(30):
            results = roll_two_missions(
                nation_tier=1, completed_keys=set(), exclude_keys=common_keys
            )
            for m in results:
                assert m.key not in common_keys

    def test_fallback_when_all_excluded(self):
        """If all missions are excluded, should still return something."""
        all_keys = set(MISSION_DEFS.keys())
        results = roll_two_missions(nation_tier=1, completed_keys=set(), exclude_keys=all_keys)
        # Fallback ignores exclusions
        assert len(results) >= 1

    def test_empty_pool_returns_empty(self):
        """Tier 1 with no eligible (impossible normally, but tier=0 simulates it)."""
        # tier=0 means tier_required=1 fails — nothing eligible
        results = roll_two_missions(nation_tier=0, completed_keys=set(), exclude_keys=set())
        assert results == []

    def test_rarity_weighting_favours_common(self):
        """Over many rolls at tier 1, common missions should appear most."""
        random.seed(123)
        rarity_counts: dict = {}
        for _ in range(500):
            results = roll_two_missions(nation_tier=10, completed_keys=set(), exclude_keys=set())
            for m in results:
                rarity_counts[m.rarity] = rarity_counts.get(m.rarity, 0) + 1
        assert rarity_counts.get('common', 0) > rarity_counts.get('legendary', 0)
        assert rarity_counts.get('common', 0) > rarity_counts.get('epic', 0)

    def test_result_missions_are_eligible(self):
        """All rolled missions should pass tier/chapter requirements."""
        random.seed(7)
        completed = {'chapter_1', 'chapter_2'}
        for _ in range(50):
            results = roll_two_missions(
                nation_tier=5, completed_keys=completed, exclude_keys=set()
            )
            for m in results:
                assert m.tier_required <= 5
                if m.chapter_requires:
                    assert m.chapter_requires in completed


# ── Missions tab route ────────────────────────────────────────────────────────

class TestMissionsTabRoute:
    def test_requires_login(self, app, client):
        resp = client.get('/military/missions')
        assert resp.status_code == 302

    def test_returns_html(self, app, auth_client, nation):
        resp = auth_client.get('/military/missions')
        assert resp.status_code == 200
        assert b'Enemy Forces' in resp.data

    def test_creates_two_offers_on_first_visit(self, app, auth_client, nation):
        auth_client.get('/military/missions')
        offers = MissionOffer.query.filter_by(nation_id=nation.id).all()
        assert len(offers) == 2

    def test_offers_have_slots_1_and_2(self, app, auth_client, nation):
        auth_client.get('/military/missions')
        slots = {o.slot for o in MissionOffer.query.filter_by(nation_id=nation.id).all()}
        assert slots == {1, 2}

    def test_repeated_visit_does_not_duplicate_offers(self, app, auth_client, nation):
        auth_client.get('/military/missions')
        auth_client.get('/military/missions')
        assert MissionOffer.query.filter_by(nation_id=nation.id).count() == 2

    def test_active_offer_not_replaced(self, app, auth_client, nation):
        """A slot with status='active' should never be overwritten."""
        offer = MissionOffer(nation_id=nation.id, slot=1, mission_key='riot_control',
                             status='active')
        db.session.add(offer)
        db.session.commit()
        auth_client.get('/military/missions')
        db.session.refresh(offer)
        assert offer.status == 'active'
        assert offer.mission_key == 'riot_control'

    def test_completed_offer_stays_until_collected(self, app, auth_client, nation):
        """A completed offer stays as-is on page visit — refreshed only on collect."""
        offer = MissionOffer(
            nation_id=nation.id, slot=1, mission_key='riot_control',
            status='completed',
            completed_at=datetime.now(timezone.utc) - timedelta(hours=999),
        )
        db.session.add(offer)
        db.session.commit()

        auth_client.get('/military/missions')

        db.session.refresh(offer)
        # completed offers wait for explicit collect/acknowledge
        assert offer.status == 'completed'

    def test_completed_offer_within_cooldown_not_refreshed(self, app, auth_client, nation):
        """A recently completed offer should stay as-is during cooldown."""
        offer = MissionOffer(
            nation_id=nation.id, slot=1, mission_key='riot_control',
            status='completed',
            completed_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db.session.add(offer)
        db.session.commit()

        auth_client.get('/military/missions')
        db.session.refresh(offer)
        assert offer.status == 'completed'  # unchanged


# ── Deploy mission route ──────────────────────────────────────────────────────

class TestDeployMission:
    def test_deploy_creates_battle(self, app, auth_client, nation, available_offer,
                                   mobilized_div, npc_nation):
        resp = auth_client.post(
            f'/military/mission/{available_offer.id}/deploy',
            data={'division_id': str(mobilized_div.id)},
        )
        assert resp.status_code == 200
        battle = Battle.query.filter_by(
            attacker_nation_id=nation.id, battle_type='pve_mission'
        ).first()
        assert battle is not None
        assert battle.mission_offer_id == available_offer.id

    def test_deploy_sets_offer_active(self, app, auth_client, nation, available_offer,
                                      mobilized_div, npc_nation):
        auth_client.post(
            f'/military/mission/{available_offer.id}/deploy',
            data={'division_id': str(mobilized_div.id)},
        )
        db.session.refresh(available_offer)
        assert available_offer.status == 'active'

    def test_deploy_sets_division_in_combat(self, app, auth_client, nation,
                                             available_offer, mobilized_div, npc_nation):
        auth_client.post(
            f'/military/mission/{available_offer.id}/deploy',
            data={'division_id': str(mobilized_div.id)},
        )
        db.session.refresh(mobilized_div)
        assert mobilized_div.in_combat is True

    def test_deploy_triggers_refresh_events(self, app, auth_client, nation,
                                             available_offer, mobilized_div, npc_nation):
        resp = auth_client.post(
            f'/military/mission/{available_offer.id}/deploy',
            data={'division_id': str(mobilized_div.id)},
        )
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert 'refreshMissions' in trigger
        assert 'refreshDivisionContent' in trigger

    def test_deploy_rejects_demobilized_division(self, app, auth_client, nation,
                                                  available_offer, npc_nation):
        demob = Division(nation_id=nation.id, name='Demob', mobilization_state='demobilized')
        db.session.add(demob)
        db.session.flush()
        unit = Unit(nation_id=nation.id, division_id=demob.id, unit_key='infantry',
                    firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(unit)
        db.session.commit()

        resp = auth_client.post(
            f'/military/mission/{available_offer.id}/deploy',
            data={'division_id': str(demob.id)},
        )
        assert resp.status_code == 422

    def test_deploy_rejects_division_already_in_combat(self, app, auth_client, nation,
                                                         available_offer, npc_nation):
        div = Division(nation_id=nation.id, name='Busy', mobilization_state='mobilized',
                       in_combat=True)
        db.session.add(div)
        db.session.flush()
        unit = Unit(nation_id=nation.id, division_id=div.id, unit_key='infantry',
                    firepower=3, armour=1, maneuver=2, hp=50, max_hp=50)
        db.session.add(unit)
        db.session.commit()

        resp = auth_client.post(
            f'/military/mission/{available_offer.id}/deploy',
            data={'division_id': str(div.id)},
        )
        assert resp.status_code == 422

    def test_deploy_rejects_empty_division(self, app, auth_client, nation,
                                            available_offer, npc_nation):
        empty = Division(nation_id=nation.id, name='Empty', mobilization_state='mobilized')
        db.session.add(empty)
        db.session.commit()

        resp = auth_client.post(
            f'/military/mission/{available_offer.id}/deploy',
            data={'division_id': str(empty.id)},
        )
        assert resp.status_code == 422

    def test_deploy_rejects_active_offer(self, app, auth_client, nation, mobilized_div, npc_nation):
        offer = MissionOffer(nation_id=nation.id, slot=1, mission_key='riot_control',
                             status='active')
        db.session.add(offer)
        db.session.commit()

        resp = auth_client.post(
            f'/military/mission/{offer.id}/deploy',
            data={'division_id': str(mobilized_div.id)},
        )
        assert resp.status_code == 422

    def test_deploy_rejects_wrong_nation_offer(self, app, auth_client):
        """Cannot deploy on another nation's mission offer."""
        u2 = User(username='other', email='other@test.com')
        u2.set_password('pw')
        db.session.add(u2)
        db.session.flush()
        n2 = Nation(user_id=u2.id, name='OtherNation', continent='Tind')
        db.session.add(n2)
        db.session.flush()
        offer = MissionOffer(nation_id=n2.id, slot=1, mission_key='riot_control')
        db.session.add(offer)
        db.session.commit()

        resp = auth_client.post(
            f'/military/mission/{offer.id}/deploy',
            data={'division_id': '1'},
        )
        assert resp.status_code == 422

    def test_deploy_spawns_npc_enemies(self, app, auth_client, nation, available_offer,
                                        mobilized_div, npc_nation):
        auth_client.post(
            f'/military/mission/{available_offer.id}/deploy',
            data={'division_id': str(mobilized_div.id)},
        )
        battle = Battle.query.filter_by(
            attacker_nation_id=nation.id, battle_type='pve_mission'
        ).first()
        assert battle is not None
        mdef = MISSION_DEFS['riot_control']
        npc_units = Unit.query.filter_by(
            division_id=battle.defender_division_id,
            nation_id=battle.defender_nation_id,
        ).all()
        assert mdef.enemy_count[0] <= len(npc_units) <= mdef.enemy_count[1]

    def test_deploy_npc_units_have_correct_keys(self, app, auth_client, nation,
                                                  available_offer, mobilized_div, npc_nation):
        """All spawned NPC units should have unit keys from the mission composition."""
        auth_client.post(
            f'/military/mission/{available_offer.id}/deploy',
            data={'division_id': str(mobilized_div.id)},
        )
        battle = Battle.query.filter_by(
            attacker_nation_id=nation.id, battle_type='pve_mission'
        ).first()
        mdef = MISSION_DEFS['riot_control']
        npc_units = Unit.query.filter_by(
            division_id=battle.defender_division_id,
            nation_id=battle.defender_nation_id,
        ).all()
        valid_keys = set(mdef.enemy_composition.keys())
        for u in npc_units:
            assert u.unit_key in valid_keys, f"Unexpected unit key '{u.unit_key}'"


# ── Skip mission route ────────────────────────────────────────────────────────

class TestSkipMission:
    def test_skip_replaces_offer(self, app, auth_client, nation, available_offer):
        original_key = available_offer.mission_key
        auth_client.post(f'/military/mission/{available_offer.id}/skip')
        db.session.refresh(available_offer)
        # Slot row is updated in-place
        assert available_offer.status == 'available'
        # Mission might or might not change (small pool) — just check it's still valid
        assert available_offer.mission_key in MISSION_DEFS

    def test_skip_triggers_refresh_missions(self, app, auth_client, nation, available_offer):
        resp = auth_client.post(f'/military/mission/{available_offer.id}/skip')
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert 'refreshMissions' in trigger

    def test_skip_rejects_active_offer(self, app, auth_client, nation):
        offer = MissionOffer(nation_id=nation.id, slot=1, mission_key='riot_control',
                             status='active')
        db.session.add(offer)
        db.session.commit()
        resp = auth_client.post(f'/military/mission/{offer.id}/skip')
        assert resp.status_code == 422

    def test_skip_rejects_wrong_nation(self, app, auth_client):
        u2 = User(username='other2', email='o2@test.com')
        u2.set_password('pw')
        db.session.add(u2)
        db.session.flush()
        n2 = Nation(user_id=u2.id, name='Other2', continent='Tind')
        db.session.add(n2)
        db.session.flush()
        offer = MissionOffer(nation_id=n2.id, slot=1, mission_key='riot_control')
        db.session.add(offer)
        db.session.commit()
        resp = auth_client.post(f'/military/mission/{offer.id}/skip')
        assert resp.status_code == 422


# ── _resolve_mission (reward distribution) ───────────────────────────────────

class TestResolveMission:
    def _make_battle_and_offer(self, nation, npc_nation, mission_key='riot_control'):
        """Create a finished pve_mission Battle with a linked MissionOffer."""
        offer = MissionOffer(
            nation_id=nation.id, slot=1, mission_key=mission_key, status='active',
        )
        db.session.add(offer)
        db.session.flush()

        npc_div = Division(nation_id=npc_nation.id, name='NPC', mobilization_state='mobilized')
        player_div = Division(nation_id=nation.id, name='Alpha', mobilization_state='mobilized')
        db.session.add_all([npc_div, player_div])
        db.session.flush()

        battle = Battle(
            attacker_nation_id=nation.id,
            defender_nation_id=npc_nation.id,
            attacker_division_id=player_div.id,
            defender_division_id=npc_div.id,
            attacker_division_name=player_div.name,
            defender_division_name=npc_div.name,
            battle_type='pve_mission',
            mission_offer_id=offer.id,
            status='finished',
            attacker_snapshot='[]',
            defender_snapshot='[]',
        )
        db.session.add(battle)
        db.session.flush()
        offer.battle_id = battle.id
        db.session.commit()
        return battle, offer

    def test_win_distributes_rewards(self, app, auth_client, nation, npc_nation):
        """Rewards are granted on collect, not on resolve."""
        from app.game.combat import _resolve_mission

        battle, offer = self._make_battle_and_offer(nation, npc_nation, 'riot_control')
        battle.winner = 'attacker'

        mdef = MISSION_DEFS['riot_control']
        money_before = nation.money

        _resolve_mission(battle, db.session)
        db.session.commit()
        db.session.refresh(nation)
        # _resolve_mission only sets status — no rewards yet
        assert nation.money == money_before

        # Collect step grants the rewards
        auth_client.post(f'/military/mission/{offer.id}/collect')
        db.session.refresh(nation)
        assert nation.money == money_before + mdef.rewards['money']

    def test_win_sets_offer_completed(self, app, nation, npc_nation):
        from app.game.combat import _resolve_mission

        battle, offer = self._make_battle_and_offer(nation, npc_nation)
        battle.winner = 'attacker'
        _resolve_mission(battle, db.session)
        db.session.commit()
        db.session.refresh(offer)
        assert offer.status == 'completed'
        assert offer.completed_at is not None

    def test_win_creates_mission_record(self, app, auth_client, nation, npc_nation):
        """MissionRecord is created on collect, not on resolve."""
        from app.game.combat import _resolve_mission

        battle, offer = self._make_battle_and_offer(nation, npc_nation, 'riot_control')
        battle.winner = 'attacker'
        _resolve_mission(battle, db.session)
        db.session.commit()

        # No record yet — only after collect
        assert MissionRecord.query.filter_by(nation_id=nation.id, mission_key='riot_control').first() is None

        auth_client.post(f'/military/mission/{offer.id}/collect')
        record = MissionRecord.query.filter_by(
            nation_id=nation.id, mission_key='riot_control'
        ).first()
        assert record is not None
        assert record.completed_at is not None

    def test_win_sets_offer_completed_not_rewards(self, app, nation, npc_nation):
        """_resolve_mission only marks the offer — no system message or rewards."""
        from app.game.combat import _resolve_mission
        from app.models import Message

        battle, offer = self._make_battle_and_offer(nation, npc_nation, 'riot_control')
        battle.winner = 'attacker'
        _resolve_mission(battle, db.session)
        db.session.commit()

        db.session.refresh(offer)
        assert offer.status == 'completed'
        # No system message from _resolve_mission alone (messages come from _end_battle)
        # No rewards until collect
        assert MissionRecord.query.filter_by(nation_id=nation.id).count() == 0

    def test_loss_sets_offer_failed(self, app, nation, npc_nation):
        from app.game.combat import _resolve_mission

        battle, offer = self._make_battle_and_offer(nation, npc_nation)
        battle.winner = 'defender'
        _resolve_mission(battle, db.session)
        db.session.commit()
        db.session.refresh(offer)
        assert offer.status == 'failed'

    def test_loss_grants_no_rewards(self, app, nation, npc_nation):
        from app.game.combat import _resolve_mission

        battle, offer = self._make_battle_and_offer(nation, npc_nation, 'riot_control')
        battle.winner = 'defender'
        mdef = MISSION_DEFS['riot_control']
        money_before = nation.money
        _resolve_mission(battle, db.session)
        db.session.commit()
        db.session.refresh(nation)
        assert nation.money == money_before  # no reward on loss

    def test_loss_creates_no_mission_record(self, app, nation, npc_nation):
        from app.game.combat import _resolve_mission

        battle, offer = self._make_battle_and_offer(nation, npc_nation, 'riot_control')
        battle.winner = 'defender'
        _resolve_mission(battle, db.session)
        db.session.commit()

        record = MissionRecord.query.filter_by(
            nation_id=nation.id, mission_key='riot_control'
        ).first()
        assert record is None

    def test_duplicate_collect_does_not_create_duplicate_record(self, app, auth_client, nation, npc_nation):
        from app.game.combat import _resolve_mission

        # First win + collect
        battle1, offer1 = self._make_battle_and_offer(nation, npc_nation, 'riot_control')
        battle1.winner = 'attacker'
        _resolve_mission(battle1, db.session)
        db.session.commit()
        auth_client.post(f'/military/mission/{offer1.id}/collect')

        # Second win on same mission key
        offer2 = MissionOffer(nation_id=nation.id, slot=2, mission_key='riot_control',
                              status='active')
        db.session.add(offer2)
        db.session.flush()
        npc_div2 = Division(nation_id=npc_nation.id, name='NPC2', mobilization_state='mobilized')
        player_div2 = Division(nation_id=nation.id, name='Beta', mobilization_state='mobilized')
        db.session.add_all([npc_div2, player_div2])
        db.session.flush()
        battle2 = Battle(
            attacker_nation_id=nation.id,
            defender_nation_id=npc_nation.id,
            attacker_division_id=player_div2.id,
            defender_division_id=npc_div2.id,
            attacker_division_name='Beta',
            defender_division_name='NPC2',
            battle_type='pve_mission',
            mission_offer_id=offer2.id,
            status='finished',
            winner='attacker',
            attacker_snapshot='[]',
            defender_snapshot='[]',
        )
        db.session.add(battle2)
        db.session.flush()
        offer2.battle_id = battle2.id
        _resolve_mission(battle2, db.session)
        db.session.commit()

        auth_client.post(f'/military/mission/{offer2.id}/collect')

        count = MissionRecord.query.filter_by(
            nation_id=nation.id, mission_key='riot_control'
        ).count()
        assert count == 1  # unique constraint — no duplicate

    def test_multi_resource_rewards_all_granted(self, app, auth_client, nation, npc_nation):
        """supply_raid rewards metal + ammunition + fuel — all granted on collect."""
        from app.game.combat import _resolve_mission

        battle, offer = self._make_battle_and_offer(nation, npc_nation, 'supply_raid')
        battle.winner = 'attacker'

        mdef = MISSION_DEFS['supply_raid']
        before = {res: nation.get_resource(res) for res in mdef.rewards}

        _resolve_mission(battle, db.session)
        db.session.commit()

        auth_client.post(f'/military/mission/{offer.id}/collect')
        db.session.refresh(nation)

        for res, amount in mdef.rewards.items():
            assert nation.get_resource(res) == before[res] + amount, (
                f"Reward '{res}' not granted correctly"
            )

    def test_missing_offer_id_is_noop(self, app, nation, npc_nation):
        """Battle without mission_offer_id should not crash."""
        from app.game.combat import _resolve_mission

        npc_div = Division(nation_id=npc_nation.id, name='NPC3', mobilization_state='mobilized')
        player_div = Division(nation_id=nation.id, name='Gamma', mobilization_state='mobilized')
        db.session.add_all([npc_div, player_div])
        db.session.flush()
        battle = Battle(
            attacker_nation_id=nation.id,
            defender_nation_id=npc_nation.id,
            attacker_division_id=player_div.id,
            defender_division_id=npc_div.id,
            attacker_division_name='Gamma',
            defender_division_name='NPC3',
            battle_type='pve_mission',
            mission_offer_id=None,
            status='finished',
            winner='attacker',
            attacker_snapshot='[]',
            defender_snapshot='[]',
        )
        db.session.add(battle)
        db.session.commit()

        # Should not raise
        _resolve_mission(battle, db.session)


# ── _generate_mission_opponent ────────────────────────────────────────────────

class TestGenerateMissionOpponent:
    def test_spawns_within_enemy_count_range(self, app, nation, npc_nation):
        from app.military.routes import _generate_mission_opponent

        mdef = MISSION_DEFS['riot_control']
        with app.app_context():
            npc_div = _generate_mission_opponent(mdef, npc_nation.id)
            db.session.flush()
            unit_count = Unit.query.filter_by(division_id=npc_div.id,
                                              nation_id=npc_nation.id).count()
        assert mdef.enemy_count[0] <= unit_count <= mdef.enemy_count[1]

    def test_spawned_units_have_valid_stats(self, app, nation, npc_nation):
        from app.military.routes import _generate_mission_opponent

        mdef = MISSION_DEFS['foreign_affairs']  # secret_agent: 100%
        npc_div = _generate_mission_opponent(mdef, npc_nation.id)
        db.session.flush()
        units = Unit.query.filter_by(division_id=npc_div.id, nation_id=npc_nation.id).all()
        for u in units:
            assert u.hp > 0
            assert u.max_hp > 0
            assert u.firepower >= 0

    def test_division_is_mobilized(self, app, nation, npc_nation):
        from app.military.routes import _generate_mission_opponent

        mdef = MISSION_DEFS['riot_control']
        npc_div = _generate_mission_opponent(mdef, npc_nation.id)
        db.session.flush()
        assert npc_div.mobilization_state == 'mobilized'

    def test_mixed_composition_produces_variety(self, app, nation, npc_nation):
        """arctic_drill (fsk/infantry/m2_bradley) should spawn multiple unit types."""
        from app.military.routes import _generate_mission_opponent

        mdef = MISSION_DEFS['arctic_drill']
        keys_seen = set()
        for seed in range(20):
            random.seed(seed)
            npc_div = _generate_mission_opponent(mdef, npc_nation.id)
            db.session.flush()
            units = Unit.query.filter_by(division_id=npc_div.id,
                                         nation_id=npc_nation.id).all()
            keys_seen.update(u.unit_key for u in units)
            # Clean up for next iteration
            for u in units:
                db.session.delete(u)
            db.session.delete(npc_div)
            db.session.flush()

        # Over 20 iterations we should see at least 2 different unit types
        assert len(keys_seen) >= 2


# ── Recruitment grid does not show NPC units ──────────────────────────────────

class TestRecruitmentGridExcludesNpc:
    def test_military_overview_hides_npc_units(self, app, auth_client):
        resp = auth_client.get('/military')
        # NPC-only unit names should not appear in recruitment grid
        assert b'Secret Agent' not in resp.data
        assert b'FSK' not in resp.data
        assert b'Sectoid' not in resp.data

    def test_military_overview_shows_player_units(self, app, auth_client):
        resp = auth_client.get('/military')
        # Player-recruitable units should still appear
        assert b'Infantry' in resp.data
        assert b'Medic' in resp.data
