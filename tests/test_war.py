"""Tests for war game logic, routes, and deployment task."""
import json
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest

from app import db
from app.models import (
    User, Nation, War, WarBattle, WarDeploymentQueue,
    Division, Unit, Battle, Message,
)
from app.game.war import (
    compute_war_scores, credit_war_victory, count_offensive_victories,
    resolve_war_compensation, resolve_war_annexation, resolve_white_peace,
    get_active_war, get_nation_active_wars,
)


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture()
def enemy(app):
    """A second nation — the defender in most tests."""
    u = User(username='enemy', email='enemy@test.com')
    u.set_password('password')
    db.session.add(u)
    db.session.flush()
    n = Nation(
        user_id=u.id, name='EnemyNation', continent='Westberg',
        money=500_000, food=50_000, power=50_000,
        building_materials=50_000, consumer_goods=50_000,
        metal=50_000, ammunition=50_000, fuel=50_000,
        uranium=500, total_land=1000, cleared_land=200,
    )
    db.session.add(n)
    db.session.commit()
    return n


@pytest.fixture()
def enemy_client(app, enemy):
    """Test client logged in as the enemy nation."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(enemy.user_id)
    return c


@pytest.fixture()
def active_war(app, nation, enemy):
    w = War(
        attacker_nation_id=nation.id,
        defender_nation_id=enemy.id,
        name='Test War',
        casus_belli='They wronged us greatly.',
    )
    db.session.add(w)
    db.session.commit()
    return w


def _make_division(nation_id, *, name='Alpha', state='mobilized',
                   is_defensive=False, in_combat=False):
    d = Division(
        nation_id=nation_id, name=name,
        mobilization_state=state,
        is_defensive=is_defensive,
        in_combat=in_combat,
    )
    db.session.add(d)
    db.session.flush()
    return d


def _make_unit(nation_id, division_id, *, hp=50):
    u = Unit(
        nation_id=nation_id, division_id=division_id,
        unit_key='infantry', firepower=3, armour=1, maneuver=2,
        hp=hp, max_hp=50,
    )
    db.session.add(u)
    db.session.flush()
    return u


# ── compute_war_scores ────────────────────────────────────────────────────────

class TestComputeWarScores:
    def _war(self, atk, dfn):
        return SimpleNamespace(attacker_victories=atk, defender_victories=dfn)

    def test_tied_at_zero(self):
        s = compute_war_scores(self._war(0, 0))
        assert s['attacker_victories'] == 0
        assert s['defender_victories'] == 0
        assert s['attacker_can_demand'] is False
        assert s['defender_can_demand'] is False
        assert s['attacker_lead'] == 0
        assert s['defender_lead'] == 0

    def test_attacker_below_threshold(self):
        s = compute_war_scores(self._war(2, 0))
        assert s['attacker_can_demand'] is False
        assert s['attacker_lead'] == 2

    def test_attacker_at_threshold(self):
        s = compute_war_scores(self._war(3, 0))
        assert s['attacker_can_demand'] is True
        assert s['defender_can_demand'] is False

    def test_defender_at_threshold(self):
        s = compute_war_scores(self._war(1, 4))
        assert s['defender_can_demand'] is True
        assert s['attacker_can_demand'] is False
        assert s['defender_lead'] == 3

    def test_large_lead(self):
        s = compute_war_scores(self._war(10, 2))
        assert s['attacker_can_demand'] is True
        assert s['attacker_lead'] == 8

    def test_equal_nonzero_scores(self):
        s = compute_war_scores(self._war(5, 5))
        assert s['attacker_can_demand'] is False
        assert s['defender_can_demand'] is False


# ── credit_war_victory ────────────────────────────────────────────────────────

class TestCreditWarVictory:
    def _war(self):
        return SimpleNamespace(
            attacker_nation_id=1, defender_nation_id=2,
            attacker_victories=0, defender_victories=0,
        )

    def test_war_attacker_sends_division_and_wins(self):
        war = self._war()
        wb = SimpleNamespace(side='attacker')
        credit_war_victory(war, wb, 'attacker')
        assert war.attacker_victories == 1
        assert war.defender_victories == 0

    def test_war_attacker_sends_division_and_loses(self):
        war = self._war()
        wb = SimpleNamespace(side='attacker')
        credit_war_victory(war, wb, 'defender')
        assert war.defender_victories == 1
        assert war.attacker_victories == 0

    def test_war_defender_counter_deploys_and_wins(self):
        # Defender launched a counter-attack; they were the 'battle attacker'
        war = self._war()
        wb = SimpleNamespace(side='defender')
        credit_war_victory(war, wb, 'attacker')
        assert war.defender_victories == 1
        assert war.attacker_victories == 0

    def test_war_defender_counter_deploys_and_loses(self):
        war = self._war()
        wb = SimpleNamespace(side='defender')
        credit_war_victory(war, wb, 'defender')
        assert war.attacker_victories == 1
        assert war.defender_victories == 0

    def test_cumulative_credits(self):
        war = self._war()
        wb_atk = SimpleNamespace(side='attacker')
        wb_def = SimpleNamespace(side='defender')
        credit_war_victory(war, wb_atk, 'attacker')   # attacker wins → +1 atk
        credit_war_victory(war, wb_atk, 'attacker')   # attacker wins again
        credit_war_victory(war, wb_def, 'attacker')   # defender wins → +1 def
        assert war.attacker_victories == 2
        assert war.defender_victories == 1


# ── resolve_war_compensation ──────────────────────────────────────────────────

class TestResolveWarCompensation:
    def test_attacker_takes_35_percent(self, app, nation, enemy, active_war):
        enemy.money = 100_000
        db.session.flush()

        resolve_war_compensation(active_war, nation.id, db.session)

        assert enemy.money == pytest.approx(65_000)
        assert nation.money == pytest.approx(1_000_000 + 35_000)

    def test_all_resources_transferred(self, app, nation, enemy, active_war):
        enemy.food = 200_000
        enemy.metal = 80_000
        db.session.flush()

        resolve_war_compensation(active_war, nation.id, db.session)

        assert enemy.food == pytest.approx(200_000 * 0.65)
        assert enemy.metal == pytest.approx(80_000 * 0.65)

    def test_defender_can_also_demand(self, app, nation, enemy, active_war):
        nation.ammunition = 60_000
        db.session.flush()

        resolve_war_compensation(active_war, enemy.id, db.session)

        assert nation.ammunition == pytest.approx(60_000 * 0.65)
        assert enemy.ammunition == pytest.approx(50_000 + 60_000 * 0.35)

    def test_war_status_set_to_compensated(self, app, nation, enemy, active_war):
        resolve_war_compensation(active_war, nation.id, db.session)
        assert active_war.status == 'compensated'
        assert active_war.ended_at is not None

    def test_zero_resources_not_negative(self, app, nation, enemy, active_war):
        enemy.money = 0
        db.session.flush()
        resolve_war_compensation(active_war, nation.id, db.session)
        assert enemy.money >= 0


# ── resolve_war_annexation ────────────────────────────────────────────────────

class TestResolveWarAnnexation:
    def test_population_transferred(self, app, nation, enemy, active_war):
        enemy.population = 10_000
        nation.population = 5_000
        db.session.flush()

        resolve_war_annexation(active_war, nation.id, db.session)

        assert enemy.population == 8_000
        assert nation.population == 7_000

    def test_land_transferred(self, app, nation, enemy, active_war):
        enemy.total_land = 1000
        enemy.cleared_land = 200
        db.session.flush()

        resolve_war_annexation(active_war, nation.id, db.session)

        assert enemy.total_land == 800
        assert enemy.cleared_land == 160

    def test_war_status_set_to_annexed(self, app, nation, enemy, active_war):
        resolve_war_annexation(active_war, nation.id, db.session)
        assert active_war.status == 'annexed'
        assert active_war.ended_at is not None


# ── resolve_white_peace ───────────────────────────────────────────────────────

class TestResolveWhitePeace:
    def test_status_and_timestamp(self, app, active_war):
        resolve_white_peace(active_war)
        assert active_war.status == 'peace'
        assert active_war.ended_at is not None

    def test_resources_unchanged(self, app, nation, enemy, active_war):
        before_money = nation.money
        resolve_white_peace(active_war)
        assert nation.money == before_money


# ── get_active_war / get_nation_active_wars ───────────────────────────────────

class TestWarQueries:
    def test_get_active_war_finds_match(self, app, nation, enemy, active_war):
        result = get_active_war(nation.id, enemy.id)
        assert result is not None
        assert result.id == active_war.id

    def test_get_active_war_reversed_ids(self, app, nation, enemy, active_war):
        result = get_active_war(enemy.id, nation.id)
        assert result is not None

    def test_get_active_war_ignores_ended(self, app, nation, enemy, active_war):
        active_war.status = 'peace'
        db.session.commit()
        assert get_active_war(nation.id, enemy.id) is None

    def test_get_active_war_no_war(self, app, nation, enemy):
        assert get_active_war(nation.id, enemy.id) is None

    def test_get_nation_active_wars(self, app, nation, enemy, active_war):
        wars = get_nation_active_wars(nation.id)
        assert len(wars) == 1
        assert wars[0].id == active_war.id

    def test_get_nation_active_wars_as_defender(self, app, nation, enemy, active_war):
        wars = get_nation_active_wars(enemy.id)
        assert len(wars) == 1

    def test_get_nation_active_wars_excludes_ended(self, app, nation, enemy, active_war):
        active_war.status = 'compensated'
        db.session.commit()
        assert get_nation_active_wars(nation.id) == []


# ── count_offensive_victories ─────────────────────────────────────────────────

class TestCountOffensiveVictories:
    def _add_war_battle(self, war, deploying_id, side, winner):
        """Create a finished Battle and link it via WarBattle."""
        b = Battle(
            attacker_nation_id=deploying_id,
            defender_nation_id=(war.defender_nation_id
                                if deploying_id == war.attacker_nation_id
                                else war.attacker_nation_id),
            attacker_division_id=None,
            defender_division_id=None,
            attacker_division_name='Alpha',
            defender_division_name='Beta',
            attacker_nation_name='A',
            defender_nation_name='B',
            battle_type='pvp',
            status='finished',
            winner=winner,
        )
        db.session.add(b)
        db.session.flush()
        wb = WarBattle(
            war_id=war.id,
            battle_id=b.id,
            attacker_nation_id=deploying_id,
            side=side,
        )
        db.session.add(wb)
        db.session.flush()
        return wb

    def test_zero_when_no_battles(self, app, nation, enemy, active_war):
        assert count_offensive_victories(active_war, nation.id) == 0

    def test_counts_attacker_wins(self, app, nation, enemy, active_war):
        self._add_war_battle(active_war, nation.id, 'attacker', 'attacker')
        self._add_war_battle(active_war, nation.id, 'attacker', 'attacker')
        db.session.commit()
        assert count_offensive_victories(active_war, nation.id) == 2

    def test_excludes_losses(self, app, nation, enemy, active_war):
        self._add_war_battle(active_war, nation.id, 'attacker', 'attacker')
        self._add_war_battle(active_war, nation.id, 'attacker', 'defender')
        db.session.commit()
        assert count_offensive_victories(active_war, nation.id) == 1

    def test_excludes_opponent_offensive_wins(self, app, nation, enemy, active_war):
        # Enemy deploys and wins — should NOT count as nation's offensive win
        self._add_war_battle(active_war, enemy.id, 'defender', 'attacker')
        db.session.commit()
        assert count_offensive_victories(active_war, nation.id) == 0

    def test_defender_side_offensive_victories(self, app, nation, enemy, active_war):
        # Enemy (defender in war) sends a counter-attack and wins
        self._add_war_battle(active_war, enemy.id, 'defender', 'attacker')
        db.session.commit()
        assert count_offensive_victories(active_war, enemy.id) == 1


# ── Declare war route ─────────────────────────────────────────────────────────

class TestDeclareWarRoute:
    def test_get_returns_form(self, app, auth_client, enemy):
        resp = auth_client.get(f'/war/declare/{enemy.id}')
        assert resp.status_code == 200
        assert b'casus_belli' in resp.data

    def test_post_creates_war(self, app, auth_client, nation, enemy):
        resp = auth_client.post(f'/war/declare/{enemy.id}', data={
            'war_name': 'Operation Test',
            'casus_belli': 'They crossed the border.',
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert War.query.filter_by(attacker_nation_id=nation.id).count() == 1

    def test_sends_mail_to_both_nations(self, app, auth_client, nation, enemy):
        auth_client.post(f'/war/declare/{enemy.id}', data={
            'war_name': 'Mail Test War',
            'casus_belli': 'Testing mail.',
        })
        assert Message.query.filter_by(recipient_id=nation.id).count() >= 1
        assert Message.query.filter_by(recipient_id=enemy.id).count() >= 1

    def test_blocks_duplicate_active_war(self, app, auth_client, nation, enemy, active_war):
        resp = auth_client.post(f'/war/declare/{enemy.id}', data={
            'war_name': 'Second War',
            'casus_belli': 'Another reason.',
        })
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'
        assert War.query.filter_by(attacker_nation_id=nation.id).count() == 1

    def test_rejects_missing_name(self, app, auth_client, enemy):
        resp = auth_client.post(f'/war/declare/{enemy.id}', data={
            'war_name': '',
            'casus_belli': 'Reason here.',
        })
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'

    def test_rejects_missing_casus_belli(self, app, auth_client, enemy):
        resp = auth_client.post(f'/war/declare/{enemy.id}', data={
            'war_name': 'War Name',
            'casus_belli': '',
        })
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'

    def test_cannot_declare_on_self(self, app, auth_client, nation):
        resp = auth_client.post(f'/war/declare/{nation.id}', data={
            'war_name': 'Self War', 'casus_belli': 'I hate myself.',
        })
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'

    def test_blocked_below_tier_2(self, app, auth_client, nation, enemy):
        nation.tier = 1
        db.session.commit()

        resp = auth_client.post(f'/war/declare/{enemy.id}', data={
            'war_name': 'Tier 1 War', 'casus_belli': 'Too soon.',
        })
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'
        assert War.query.count() == 0

    def test_allowed_at_tier_2(self, app, auth_client, nation, enemy):
        nation.tier = 2
        enemy.tier = 2
        db.session.commit()

        resp = auth_client.post(f'/war/declare/{enemy.id}', data={
            'war_name': 'Tier 2 War', 'casus_belli': 'Fair fight.',
        }, follow_redirects=False)
        assert resp.status_code == 302

    def test_blocked_attacking_lower_tier(self, app, auth_client, nation, enemy):
        nation.tier = 3
        enemy.tier = 2
        db.session.commit()

        resp = auth_client.post(f'/war/declare/{enemy.id}', data={
            'war_name': 'Bully War', 'casus_belli': 'Easy target.',
        })
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'
        assert War.query.count() == 0

    def test_allowed_attacking_equal_tier(self, app, auth_client, nation, enemy):
        nation.tier = 3
        enemy.tier = 3
        db.session.commit()

        resp = auth_client.post(f'/war/declare/{enemy.id}', data={
            'war_name': 'Equal War', 'casus_belli': 'Even odds.',
        }, follow_redirects=False)
        assert resp.status_code == 302

    def test_allowed_attacking_higher_tier(self, app, auth_client, nation, enemy):
        nation.tier = 2
        enemy.tier = 4
        db.session.commit()

        resp = auth_client.post(f'/war/declare/{enemy.id}', data={
            'war_name': 'Brave War', 'casus_belli': 'Punching up.',
        }, follow_redirects=False)
        assert resp.status_code == 302


# ── Deploy attack route ───────────────────────────────────────────────────────

class TestDeployAttackRoute:
    def test_deploy_creates_queue_entry(self, app, auth_client, nation, enemy, active_war):
        div = _make_division(nation.id)
        _make_unit(nation.id, div.id)
        db.session.commit()

        resp = auth_client.post(f'/war/{active_war.id}/deploy',
                                data={'division_id': div.id})
        assert WarDeploymentQueue.query.filter_by(
            war_id=active_war.id, deploying_nation_id=nation.id
        ).count() == 1

    def test_deploy_sets_arrives_at_24h(self, app, auth_client, nation, enemy, active_war):
        div = _make_division(nation.id)
        _make_unit(nation.id, div.id)
        db.session.commit()

        before = datetime.now(timezone.utc)
        auth_client.post(f'/war/{active_war.id}/deploy',
                         data={'division_id': div.id})

        entry = WarDeploymentQueue.query.filter_by(war_id=active_war.id).first()
        assert entry is not None
        arrives = entry.arrives_at
        if arrives.tzinfo is None:
            arrives = arrives.replace(tzinfo=timezone.utc)
        delta = arrives - before
        assert timedelta(hours=23, minutes=59) <= delta <= timedelta(hours=24, minutes=1)

    def test_blocks_demobilized_division(self, app, auth_client, nation, enemy, active_war):
        div = _make_division(nation.id, state='demobilized')
        _make_unit(nation.id, div.id)
        db.session.commit()

        resp = auth_client.post(f'/war/{active_war.id}/deploy',
                                data={'division_id': div.id})
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'
        assert WarDeploymentQueue.query.count() == 0

    def test_blocks_defensive_division(self, app, auth_client, nation, enemy, active_war):
        div = _make_division(nation.id, is_defensive=True)
        _make_unit(nation.id, div.id)
        db.session.commit()

        resp = auth_client.post(f'/war/{active_war.id}/deploy',
                                data={'division_id': div.id})
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'

    def test_blocks_in_combat_division(self, app, auth_client, nation, enemy, active_war):
        div = _make_division(nation.id, in_combat=True)
        _make_unit(nation.id, div.id)
        db.session.commit()

        resp = auth_client.post(f'/war/{active_war.id}/deploy',
                                data={'division_id': div.id})
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'

    def test_blocks_second_simultaneous_deploy(self, app, auth_client, nation, enemy, active_war):
        div1 = _make_division(nation.id, name='Alpha')
        _make_unit(nation.id, div1.id)
        div2 = _make_division(nation.id, name='Beta')
        _make_unit(nation.id, div2.id)
        db.session.add(WarDeploymentQueue(
            war_id=active_war.id,
            deploying_nation_id=nation.id,
            division_id=div1.id,
            arrives_at=datetime.now(timezone.utc) + timedelta(hours=12),
        ))
        db.session.commit()

        resp = auth_client.post(f'/war/{active_war.id}/deploy',
                                data={'division_id': div2.id})
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'
        assert WarDeploymentQueue.query.filter_by(war_id=active_war.id).count() == 1

    def test_blocks_division_with_no_alive_units(self, app, auth_client, nation, enemy, active_war):
        div = _make_division(nation.id)
        _make_unit(nation.id, div.id, hp=0)
        db.session.commit()

        resp = auth_client.post(f'/war/{active_war.id}/deploy',
                                data={'division_id': div.id})
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'


# ── Cancel deploy route ───────────────────────────────────────────────────────

class TestCancelDeployRoute:
    def test_cancel_traveling_deployment(self, app, auth_client, nation, enemy, active_war):
        entry = WarDeploymentQueue(
            war_id=active_war.id,
            deploying_nation_id=nation.id,
            division_id=999,
            arrives_at=datetime.now(timezone.utc) + timedelta(hours=12),
        )
        db.session.add(entry)
        db.session.commit()

        resp = auth_client.post(f'/war/{active_war.id}/cancel-deploy/{entry.id}')
        db.session.refresh(entry)
        assert entry.status == 'cancelled'

    def test_cannot_cancel_arrived(self, app, auth_client, nation, enemy, active_war):
        entry = WarDeploymentQueue(
            war_id=active_war.id,
            deploying_nation_id=nation.id,
            division_id=999,
            arrives_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db.session.add(entry)
        db.session.commit()

        resp = auth_client.post(f'/war/{active_war.id}/cancel-deploy/{entry.id}')
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'
        db.session.refresh(entry)
        assert entry.status == 'traveling'


# ── Peace offer routes ────────────────────────────────────────────────────────

class TestPeaceRoutes:
    def test_offer_peace_sets_field(self, app, auth_client, nation, enemy, active_war):
        auth_client.post(f'/war/{active_war.id}/offer-peace')
        db.session.refresh(active_war)
        assert active_war.peace_offered_by == nation.id

    def test_offer_peace_notifies_opponent(self, app, auth_client, nation, enemy, active_war):
        auth_client.post(f'/war/{active_war.id}/offer-peace')
        assert Message.query.filter_by(recipient_id=enemy.id).count() >= 1

    def test_cancel_peace_clears_field(self, app, auth_client, nation, enemy, active_war):
        active_war.peace_offered_by = nation.id
        db.session.commit()

        auth_client.post(f'/war/{active_war.id}/cancel-peace')
        db.session.refresh(active_war)
        assert active_war.peace_offered_by is None

    def test_cannot_cancel_opponents_offer(self, app, auth_client, nation, enemy, active_war):
        active_war.peace_offered_by = enemy.id
        db.session.commit()

        resp = auth_client.post(f'/war/{active_war.id}/cancel-peace')
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'
        db.session.refresh(active_war)
        assert active_war.peace_offered_by == enemy.id

    def test_accept_peace_ends_war(self, app, enemy_client, nation, enemy, active_war):
        active_war.peace_offered_by = nation.id
        db.session.commit()

        enemy_client.post(f'/war/{active_war.id}/accept-peace')
        db.session.refresh(active_war)
        assert active_war.status == 'peace'

    def test_cannot_accept_own_offer(self, app, auth_client, nation, enemy, active_war):
        active_war.peace_offered_by = nation.id
        db.session.commit()

        resp = auth_client.post(f'/war/{active_war.id}/accept-peace')
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'
        db.session.refresh(active_war)
        assert active_war.status == 'active'

    def test_cannot_accept_when_no_offer(self, app, enemy_client, nation, enemy, active_war):
        resp = enemy_client.post(f'/war/{active_war.id}/accept-peace')
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'

    def test_cancel_peace_sends_rescission_mail(self, app, auth_client, nation, enemy, active_war):
        active_war.peace_offered_by = nation.id
        db.session.commit()
        Message.query.delete()
        db.session.commit()

        auth_client.post(f'/war/{active_war.id}/cancel-peace')
        mail = Message.query.filter_by(recipient_id=enemy.id).first()
        assert mail is not None
        assert 'Rescinded' in mail.subject


# ── Settlement routes ─────────────────────────────────────────────────────────

class TestSettlementRoutes:
    def test_demand_compensation_requires_lead(self, app, auth_client, nation, enemy, active_war):
        active_war.attacker_victories = 2
        active_war.defender_victories = 0
        db.session.commit()

        resp = auth_client.post(f'/war/{active_war.id}/demand-compensation')
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'
        db.session.refresh(active_war)
        assert active_war.status == 'active'

    def test_demand_compensation_succeeds_with_lead(self, app, auth_client, nation, enemy, active_war):
        active_war.attacker_victories = 3
        active_war.defender_victories = 0
        db.session.commit()

        auth_client.post(f'/war/{active_war.id}/demand-compensation')
        db.session.refresh(active_war)
        assert active_war.status == 'compensated'

    def test_demand_annexation_requires_both_conditions(self, app, auth_client, nation, enemy, active_war):
        # 3+ lead but only 2 offensive victories — should fail
        active_war.attacker_victories = 4
        active_war.defender_victories = 0
        db.session.commit()

        div = _make_division(nation.id)
        _make_unit(nation.id, div.id)
        db.session.commit()

        # Add 2 offensive wins
        for _ in range(2):
            b = Battle(
                attacker_nation_id=nation.id, defender_nation_id=enemy.id,
                attacker_division_name='A', defender_division_name='B',
                attacker_nation_name='A', defender_nation_name='B',
                battle_type='pvp', status='finished', winner='attacker',
            )
            db.session.add(b)
            db.session.flush()
            db.session.add(WarBattle(
                war_id=active_war.id, battle_id=b.id,
                attacker_nation_id=nation.id, side='attacker',
            ))
        db.session.commit()

        resp = auth_client.post(f'/war/{active_war.id}/demand-annexation')
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'
        db.session.refresh(active_war)
        assert active_war.status == 'active'

    def test_demand_annexation_succeeds_with_both_conditions(self, app, auth_client, nation, enemy, active_war):
        active_war.attacker_victories = 3
        active_war.defender_victories = 0
        db.session.commit()

        for _ in range(3):
            b = Battle(
                attacker_nation_id=nation.id, defender_nation_id=enemy.id,
                attacker_division_name='A', defender_division_name='B',
                attacker_nation_name='A', defender_nation_name='B',
                battle_type='pvp', status='finished', winner='attacker',
            )
            db.session.add(b)
            db.session.flush()
            db.session.add(WarBattle(
                war_id=active_war.id, battle_id=b.id,
                attacker_nation_id=nation.id, side='attacker',
            ))
        db.session.commit()

        auth_client.post(f'/war/{active_war.id}/demand-annexation')
        db.session.refresh(active_war)
        assert active_war.status == 'annexed'

    def test_settlement_blocked_on_ended_war(self, app, auth_client, nation, enemy, active_war):
        active_war.status = 'peace'
        active_war.attacker_victories = 5
        db.session.commit()

        resp = auth_client.post(f'/war/{active_war.id}/demand-compensation')
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'

    def test_compensation_rescinds_pending_peace_offer(self, app, auth_client, nation, enemy, active_war):
        active_war.attacker_victories = 3
        active_war.peace_offered_by = nation.id
        db.session.commit()
        Message.query.delete()
        db.session.commit()

        auth_client.post(f'/war/{active_war.id}/demand-compensation')
        mail = Message.query.filter_by(recipient_id=enemy.id).first()
        assert mail is not None
        assert 'Rescinded' in mail.subject

    def test_annexation_rescinds_pending_peace_offer(self, app, auth_client, nation, enemy, active_war):
        active_war.attacker_victories = 3
        active_war.peace_offered_by = nation.id
        db.session.commit()
        for _ in range(3):
            b = Battle(
                attacker_nation_id=nation.id, defender_nation_id=enemy.id,
                attacker_division_name='A', defender_division_name='B',
                attacker_nation_name='A', defender_nation_name='B',
                battle_type='pvp', status='finished', winner='attacker',
            )
            db.session.add(b)
            db.session.flush()
            db.session.add(WarBattle(
                war_id=active_war.id, battle_id=b.id,
                attacker_nation_id=nation.id, side='attacker',
            ))
        db.session.commit()
        Message.query.delete()
        db.session.commit()

        auth_client.post(f'/war/{active_war.id}/demand-annexation')
        mail = Message.query.filter_by(recipient_id=enemy.id).first()
        assert mail is not None
        assert 'Rescinded' in mail.subject


# ── process_war_deployments task ──────────────────────────────────────────────

class TestWarDeploymentsTask:
    """Run process_war_deployments logic inline (no scheduler)."""

    def _run(self):
        from app.models import WarDeploymentQueue, War, Division, Unit, Battle, WarBattle, Message, Nation
        from app.game.war import credit_war_victory
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

            atk_div = Division.query.filter_by(
                id=entry.division_id, nation_id=deploying_id
            ).first()
            if not atk_div:
                entry.status = 'arrived'
                continue

            def_div = Division.query.filter_by(
                nation_id=opponent_id, is_defensive=True,
                mobilization_state='mobilized',
            ).filter(Division.in_combat == False).first()

            link = f'<a href="/war/{war.id}">View War</a>'

            if not def_div:
                atk_nation = db.session.get(Nation, deploying_id)
                def_nation = db.session.get(Nation, opponent_id)
                battle = Battle(
                    attacker_division_id=atk_div.id,
                    defender_division_id=None,
                    attacker_division_name=atk_div.name,
                    defender_division_name='(Unopposed)',
                    attacker_nation_id=deploying_id,
                    defender_nation_id=opponent_id,
                    attacker_nation_name=atk_nation.name if atk_nation else '',
                    defender_nation_name=def_nation.name if def_nation else '',
                    battle_type='pvp', location=None,
                    status='finished', winner='attacker', finished_at=now,
                )
                db.session.add(battle)
                db.session.flush()
                wb = WarBattle(
                    war_id=war.id, battle_id=battle.id,
                    attacker_nation_id=deploying_id, side=side,
                )
                db.session.add(wb)
                db.session.flush()
                credit_war_victory(war, wb, 'attacker')
                entry.status = 'arrived'
                continue

            atk_nation = db.session.get(Nation, deploying_id)
            def_nation = db.session.get(Nation, opponent_id)
            battle = Battle(
                attacker_division_id=atk_div.id,
                defender_division_id=def_div.id,
                attacker_division_name=atk_div.name,
                defender_division_name=def_div.name,
                attacker_nation_id=deploying_id,
                defender_nation_id=opponent_id,
                attacker_nation_name=atk_nation.name if atk_nation else '',
                defender_nation_name=def_nation.name if def_nation else '',
                battle_type='pvp', location=None,
            )
            db.session.add(battle)
            db.session.flush()
            db.session.add(WarBattle(
                war_id=war.id, battle_id=battle.id,
                attacker_nation_id=deploying_id, side=side,
            ))
            atk_div.in_combat = True
            def_div.in_combat = True
            entry.status = 'arrived'

        if ready:
            db.session.commit()

    def test_opposed_creates_active_battle(self, app, nation, enemy, active_war):
        atk_div = _make_division(nation.id, name='Wolves')
        def_div = _make_division(enemy.id, name='Guards', is_defensive=True)
        _make_unit(nation.id, atk_div.id)
        entry = WarDeploymentQueue(
            war_id=active_war.id,
            deploying_nation_id=nation.id,
            division_id=atk_div.id,
            arrives_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.session.add(entry)
        db.session.commit()

        self._run()

        battle = Battle.query.filter_by(
            attacker_nation_id=nation.id, defender_nation_id=enemy.id
        ).first()
        assert battle is not None
        assert battle.status == 'active'
        assert battle.winner is None

    def test_opposed_sets_both_divisions_in_combat(self, app, nation, enemy, active_war):
        atk_div = _make_division(nation.id, name='Alpha')
        def_div = _make_division(enemy.id, name='Beta', is_defensive=True)
        _make_unit(nation.id, atk_div.id)
        entry = WarDeploymentQueue(
            war_id=active_war.id,
            deploying_nation_id=nation.id,
            division_id=atk_div.id,
            arrives_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.session.add(entry)
        db.session.commit()

        self._run()

        db.session.refresh(atk_div)
        db.session.refresh(def_div)
        assert atk_div.in_combat is True
        assert def_div.in_combat is True

    def test_opposed_creates_war_battle_link(self, app, nation, enemy, active_war):
        atk_div = _make_division(nation.id, name='Alpha')
        _make_division(enemy.id, name='Defense', is_defensive=True)
        _make_unit(nation.id, atk_div.id)
        entry = WarDeploymentQueue(
            war_id=active_war.id,
            deploying_nation_id=nation.id,
            division_id=atk_div.id,
            arrives_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.session.add(entry)
        db.session.commit()

        self._run()

        assert WarBattle.query.filter_by(war_id=active_war.id).count() == 1

    def test_unopposed_creates_finished_battle(self, app, nation, enemy, active_war):
        atk_div = _make_division(nation.id, name='Wolves')
        _make_unit(nation.id, atk_div.id)
        entry = WarDeploymentQueue(
            war_id=active_war.id,
            deploying_nation_id=nation.id,
            division_id=atk_div.id,
            arrives_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.session.add(entry)
        db.session.commit()

        self._run()

        battle = Battle.query.filter_by(attacker_nation_id=nation.id).first()
        assert battle is not None
        assert battle.status == 'finished'
        assert battle.winner == 'attacker'
        assert battle.defender_division_name == '(Unopposed)'

    def test_unopposed_credits_attacker_victory(self, app, nation, enemy, active_war):
        atk_div = _make_division(nation.id, name='Wolves')
        _make_unit(nation.id, atk_div.id)
        entry = WarDeploymentQueue(
            war_id=active_war.id,
            deploying_nation_id=nation.id,
            division_id=atk_div.id,
            arrives_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.session.add(entry)
        db.session.commit()

        self._run()

        db.session.refresh(active_war)
        assert active_war.attacker_victories == 1
        assert active_war.defender_victories == 0

    def test_unopposed_does_not_set_attacker_in_combat(self, app, nation, enemy, active_war):
        """Instantly-resolved battle should leave the attacking division free."""
        atk_div = _make_division(nation.id, name='Wolves')
        _make_unit(nation.id, atk_div.id)
        entry = WarDeploymentQueue(
            war_id=active_war.id,
            deploying_nation_id=nation.id,
            division_id=atk_div.id,
            arrives_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.session.add(entry)
        db.session.commit()

        self._run()

        db.session.refresh(atk_div)
        assert atk_div.in_combat is False

    def test_future_deployment_not_processed(self, app, nation, enemy, active_war):
        atk_div = _make_division(nation.id, name='Alpha')
        _make_unit(nation.id, atk_div.id)
        entry = WarDeploymentQueue(
            war_id=active_war.id,
            deploying_nation_id=nation.id,
            division_id=atk_div.id,
            arrives_at=datetime.now(timezone.utc) + timedelta(hours=12),
        )
        db.session.add(entry)
        db.session.commit()

        self._run()

        db.session.refresh(entry)
        assert entry.status == 'traveling'
        assert Battle.query.count() == 0

    def test_ended_war_deployment_marked_arrived(self, app, nation, enemy, active_war):
        active_war.status = 'peace'
        atk_div = _make_division(nation.id, name='Alpha')
        entry = WarDeploymentQueue(
            war_id=active_war.id,
            deploying_nation_id=nation.id,
            division_id=atk_div.id,
            arrives_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.session.add(entry)
        db.session.commit()

        self._run()

        db.session.refresh(entry)
        assert entry.status == 'arrived'
        assert Battle.query.count() == 0
