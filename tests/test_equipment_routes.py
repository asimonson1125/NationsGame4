"""Tests for equipment blueprint routes — inventory, loot crates, trade-in, equip/unequip."""
import json
from app import db
from app.models import Equipment, Unit, Nation
from app.game.equipment import (
    EQUIPMENT_SLOTS, RARITY_ORDER, TRADE_IN_VALUES, CRATE_SIZES,
    compute_buff_hash, serialize_buffs,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_equipment(nation, eq_type='Infantry Weapon', rarity='Common', is_foil=False,
                    buffs=None, count=1):
    """Create an equipment item with optional buffs, return the Equipment model."""
    buff_dicts = []
    if buffs:
        for bt, val, desc in buffs:
            buff_dicts.append({'buff_type': bt, 'value': val, 'description': desc})
    eq = Equipment(
        nation_id=nation.id, equipment_type=eq_type, rarity=rarity,
        is_foil=is_foil,
        buff_hash=compute_buff_hash(buff_dicts),
        buff_json=serialize_buffs(buff_dicts),
        count=count,
    )
    db.session.add(eq)
    db.session.commit()
    return eq


def _make_unit(nation, unit_key='infantry'):
    """Create a unit for the nation."""
    from app.game.units import UNIT_DEFS
    udef = UNIT_DEFS[unit_key]
    u = Unit(nation_id=nation.id, unit_key=unit_key,
             firepower=udef.firepower, armour=udef.armour,
             maneuver=udef.maneuver, hp=udef.max_hp, max_hp=udef.max_hp)
    db.session.add(u)
    db.session.commit()
    return u


# ── Inventory page ────────────────────────────────────────────────────────

class TestInventory:
    def test_inventory_page_loads(self, app, auth_client):
        resp = auth_client.get('/equipment')
        assert resp.status_code == 200
        assert b'Equipment' in resp.data

    def test_inventory_requires_login(self, app, client):
        resp = client.get('/equipment')
        assert resp.status_code == 302

    def test_inventory_shows_equipment(self, app, auth_client, nation):
        _make_equipment(nation, rarity='Epic')
        resp = auth_client.get('/equipment')
        assert resp.status_code == 200
        assert b'Epic' in resp.data
        assert b'Infantry Weapon' in resp.data

    def test_inventory_shows_foil_badge(self, app, auth_client, nation):
        _make_equipment(nation, is_foil=True)
        resp = auth_client.get('/equipment')
        assert b'FOIL' in resp.data

    def test_inventory_empty_state(self, app, auth_client, nation):
        resp = auth_client.get('/equipment')
        assert b'No equipment found' in resp.data


# ── Equipment grid (HTMX partial) ────────────────────────────────────────

class TestEquipmentGrid:
    def test_grid_loads(self, app, auth_client, nation):
        _make_equipment(nation)
        resp = auth_client.get('/equipment/grid')
        assert resp.status_code == 200

    def test_filter_by_rarity(self, app, auth_client, nation):
        _make_equipment(nation, rarity='Common')
        _make_equipment(nation, rarity='Epic')
        resp = auth_client.get('/equipment/grid?rarity=Epic')
        assert resp.status_code == 200
        assert b'Epic' in resp.data
        # The Common item shouldn't appear
        # (hard to test negative in HTML, but at least verify it renders)

    def test_filter_by_type(self, app, auth_client, nation):
        _make_equipment(nation, eq_type='Infantry Weapon')
        _make_equipment(nation, eq_type='Body Armour')
        resp = auth_client.get('/equipment/grid?type=Body+Armour')
        assert resp.status_code == 200
        assert b'Body Armour' in resp.data

    def test_filter_foil_yes(self, app, auth_client, nation):
        _make_equipment(nation, is_foil=True)
        _make_equipment(nation, is_foil=False)
        resp = auth_client.get('/equipment/grid?foil=yes')
        assert resp.status_code == 200
        assert b'FOIL' in resp.data

    def test_filter_equipped_no(self, app, auth_client, nation):
        eq = _make_equipment(nation, count=1)
        unit = _make_unit(nation)
        unit.weapon_id = eq.id
        db.session.commit()

        resp = auth_client.get('/equipment/grid?equipped=no')
        assert resp.status_code == 200
        # Should not show the equipped item's "EQUIPPED" badge
        assert b'EQUIPPED' not in resp.data


# ── Loot crate shop ──────────────────────────────────────────────────────

class TestLootCrates:
    def test_loot_crates_tab_loads(self, app, auth_client):
        resp = auth_client.get('/equipment?tab=crates')
        assert resp.status_code == 200
        assert b'Loot Crate Shop' in resp.data

    def test_loot_crates_shows_all_categories(self, app, auth_client):
        resp = auth_client.get('/equipment?tab=crates')
        data = resp.data.decode()
        assert 'Infantry Crates' in data
        assert 'Armour Crates' in data
        assert 'Air Crates' in data
        assert 'Static Crates' in data
        assert 'Special Forces Crates' in data

    def test_loot_crates_shows_token_balance(self, app, auth_client, nation):
        nation.loot_tokens = 42
        db.session.commit()
        resp = auth_client.get('/equipment?tab=crates')
        assert b'42' in resp.data

    def test_loot_crates_redirect(self, app, auth_client):
        resp = auth_client.get('/equipment/loot-crates')
        assert resp.status_code == 302

    def test_loot_crates_requires_login(self, app, client):
        resp = client.get('/equipment')
        assert resp.status_code == 302


# ── Buy crate ─────────────────────────────────────────────────────────────

class TestBuyCrate:
    def test_buy_small_crate_success(self, app, auth_client, nation):
        nation.loot_tokens = 10
        db.session.commit()
        resp = auth_client.post('/equipment/buy-crate',
                                data={'size': 'small', 'category': 'Infantry'})
        assert resp.status_code == 200
        db.session.refresh(nation)
        assert nation.loot_tokens == 9
        # Total item count across all stacks should be 1
        total = sum(e.count for e in Equipment.query.filter_by(nation_id=nation.id).all())
        assert total == 1

    def test_buy_medium_crate_creates_three_items(self, app, auth_client, nation):
        nation.loot_tokens = 100
        db.session.commit()
        auth_client.post('/equipment/buy-crate',
                         data={'size': 'medium', 'category': 'Armour'})
        total = sum(e.count for e in Equipment.query.filter_by(nation_id=nation.id).all())
        assert total == 3

    def test_buy_epic_crate_creates_five_items(self, app, auth_client, nation):
        nation.loot_tokens = 100
        db.session.commit()
        auth_client.post('/equipment/buy-crate',
                         data={'size': 'epic', 'category': 'Air'})
        total = sum(e.count for e in Equipment.query.filter_by(nation_id=nation.id).all())
        assert total == 5

    def test_buy_crate_insufficient_tokens(self, app, auth_client, nation):
        nation.loot_tokens = 0
        db.session.commit()
        resp = auth_client.post('/equipment/buy-crate',
                                data={'size': 'small', 'category': 'Infantry'})
        assert resp.status_code == 422
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert trigger['showMessage']['type'] == 'error'
        assert Equipment.query.filter_by(nation_id=nation.id).count() == 0

    def test_buy_crate_invalid_size(self, app, auth_client, nation):
        nation.loot_tokens = 100
        db.session.commit()
        resp = auth_client.post('/equipment/buy-crate',
                                data={'size': 'mega', 'category': 'Infantry'})
        assert resp.status_code == 422

    def test_buy_crate_invalid_category(self, app, auth_client, nation):
        nation.loot_tokens = 100
        db.session.commit()
        resp = auth_client.post('/equipment/buy-crate',
                                data={'size': 'small', 'category': 'Cavalry'})
        assert resp.status_code == 422

    def test_buy_crate_items_match_category(self, app, auth_client, nation):
        nation.loot_tokens = 50
        db.session.commit()
        auth_client.post('/equipment/buy-crate',
                         data={'size': 'epic', 'category': 'Static'})
        items = Equipment.query.filter_by(nation_id=nation.id).all()
        valid_types = EQUIPMENT_SLOTS['Static']
        for item in items:
            assert item.equipment_type in valid_types

    def test_buy_crate_creates_buffs(self, app, auth_client, nation):
        nation.loot_tokens = 50
        db.session.commit()
        auth_client.post('/equipment/buy-crate',
                         data={'size': 'epic', 'category': 'Infantry'})
        items = Equipment.query.filter_by(nation_id=nation.id).all()
        total_buffs = sum(len(json.loads(item.buff_json)) for item in items)
        assert total_buffs > 0

    def test_buy_crate_deducts_exact_cost(self, app, auth_client, nation):
        nation.loot_tokens = 100
        db.session.commit()
        auth_client.post('/equipment/buy-crate',
                         data={'size': 'medium', 'category': 'Infantry'})
        db.session.refresh(nation)
        assert nation.loot_tokens == 80  # 100 - 20


# ── Trade-in ──────────────────────────────────────────────────────────────

class TestTradeIn:
    def test_trade_in_common_gives_zero_tokens(self, app, auth_client, nation):
        eq = _make_equipment(nation, rarity='Common')
        nation.loot_tokens = 0
        db.session.commit()
        resp = auth_client.post('/equipment/trade-in', data={'ids': str(eq.id)})
        assert resp.status_code == 200
        db.session.refresh(nation)
        assert nation.loot_tokens == 0

    def test_trade_in_rare_gives_five_tokens(self, app, auth_client, nation):
        eq = _make_equipment(nation, rarity='Rare')
        nation.loot_tokens = 0
        db.session.commit()
        auth_client.post('/equipment/trade-in', data={'ids': str(eq.id)})
        db.session.refresh(nation)
        assert nation.loot_tokens == 5

    def test_trade_in_epic_gives_fifteen_tokens(self, app, auth_client, nation):
        eq = _make_equipment(nation, rarity='Epic')
        nation.loot_tokens = 0
        db.session.commit()
        auth_client.post('/equipment/trade-in', data={'ids': str(eq.id)})
        db.session.refresh(nation)
        assert nation.loot_tokens == 15

    def test_trade_in_legendary_gives_forty_tokens(self, app, auth_client, nation):
        eq = _make_equipment(nation, rarity='Legendary')
        nation.loot_tokens = 0
        db.session.commit()
        auth_client.post('/equipment/trade-in', data={'ids': str(eq.id)})
        db.session.refresh(nation)
        assert nation.loot_tokens == 40

    def test_trade_in_multiple(self, app, auth_client, nation):
        eq1 = _make_equipment(nation, rarity='Rare')     # 5
        eq2 = _make_equipment(nation, rarity='Epic')     # 15
        nation.loot_tokens = 0
        db.session.commit()
        auth_client.post('/equipment/trade-in',
                         data={'ids': f'{eq1.id},{eq2.id}'})
        db.session.refresh(nation)
        assert nation.loot_tokens == 20

    def test_trade_in_deletes_equipment(self, app, auth_client, nation):
        eq = _make_equipment(nation, rarity='Uncommon')
        eq_id = eq.id
        auth_client.post('/equipment/trade-in', data={'ids': str(eq_id)})
        assert db.session.get(Equipment, eq_id) is None

    def test_trade_in_stack_decrements_count(self, app, auth_client, nation):
        """Trading a stack with equipped copies should decrement count, not delete."""
        eq = _make_equipment(nation, rarity='Rare',
                             buffs=[('Firepower', 3, '+3 Firepower')], count=3)
        unit = _make_unit(nation)
        unit.weapon_id = eq.id
        db.session.commit()
        auth_client.post('/equipment/trade-in', data={'ids': str(eq.id)})
        db.session.refresh(eq)
        # 1 equipped, 2 available traded, count should now be 1
        assert eq.count == 1

    def test_trade_in_skips_equipped_items(self, app, auth_client, nation):
        eq = _make_equipment(nation, rarity='Legendary')
        unit = _make_unit(nation)
        unit.weapon_id = eq.id
        db.session.commit()

        resp = auth_client.post('/equipment/trade-in', data={'ids': str(eq.id)})
        assert resp.status_code == 422
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert 'equipped' in trigger['showMessage']['message'].lower()
        # Item should still exist
        assert db.session.get(Equipment, eq.id) is not None

    def test_trade_in_empty_selection(self, app, auth_client, nation):
        resp = auth_client.post('/equipment/trade-in', data={'ids': ''})
        assert resp.status_code == 422

    def test_trade_in_invalid_ids(self, app, auth_client, nation):
        resp = auth_client.post('/equipment/trade-in', data={'ids': 'abc'})
        assert resp.status_code == 422

    def test_trade_in_other_nations_equipment_ignored(self, app, auth_client, nation):
        from app.models import User
        u2 = User(username='thief_target', email='t@test.com')
        u2.set_password('password')
        db.session.add(u2)
        db.session.flush()
        n2 = Nation(user_id=u2.id, name='VictimNation', continent='Tind')
        db.session.add(n2)
        db.session.flush()
        eq = _make_equipment(n2, rarity='Legendary')

        nation.loot_tokens = 0
        db.session.commit()
        resp = auth_client.post('/equipment/trade-in', data={'ids': str(eq.id)})
        # No items matched this nation, so nothing traded
        assert resp.status_code == 422
        db.session.refresh(nation)
        assert nation.loot_tokens == 0
        # Other nation's item still exists
        assert db.session.get(Equipment, eq.id) is not None


# ── Equip ─────────────────────────────────────────────────────────────────

class TestEquip:
    def test_equip_weapon_slot(self, app, auth_client, nation):
        eq = _make_equipment(nation, eq_type='Infantry Weapon')
        unit = _make_unit(nation, 'infantry')
        resp = auth_client.post('/equipment/equip',
                                data={'equipment_id': eq.id, 'unit_id': unit.id})
        assert resp.status_code == 200
        db.session.refresh(unit)
        assert unit.weapon_id == eq.id

    def test_equip_accessory_slot(self, app, auth_client, nation):
        eq = _make_equipment(nation, eq_type='Infantry Accessory')
        unit = _make_unit(nation, 'infantry')
        auth_client.post('/equipment/equip',
                         data={'equipment_id': eq.id, 'unit_id': unit.id})
        db.session.refresh(unit)
        assert unit.accessory_id == eq.id

    def test_equip_armour_slot(self, app, auth_client, nation):
        eq = _make_equipment(nation, eq_type='Body Armour')
        unit = _make_unit(nation, 'infantry')
        auth_client.post('/equipment/equip',
                         data={'equipment_id': eq.id, 'unit_id': unit.id})
        db.session.refresh(unit)
        assert unit.armour_eq_id == eq.id

    def test_equip_replaces_existing(self, app, auth_client, nation):
        eq1 = _make_equipment(nation, eq_type='Infantry Weapon',
                              buffs=[('Firepower', 1, '+1 FP')])
        eq2 = _make_equipment(nation, eq_type='Infantry Weapon',
                              buffs=[('Firepower', 2, '+2 FP')])
        unit = _make_unit(nation, 'infantry')
        auth_client.post('/equipment/equip',
                         data={'equipment_id': eq1.id, 'unit_id': unit.id})
        auth_client.post('/equipment/equip',
                         data={'equipment_id': eq2.id, 'unit_id': unit.id})
        db.session.refresh(unit)
        assert unit.weapon_id == eq2.id

    def test_equip_incompatible_type_rejected(self, app, auth_client, nation):
        # Ammunition on Infantry unit (Ammunition is Air/Static only)
        eq = _make_equipment(nation, eq_type='Ammunition')
        unit = _make_unit(nation, 'infantry')
        resp = auth_client.post('/equipment/equip',
                                data={'equipment_id': eq.id, 'unit_id': unit.id})
        assert resp.status_code == 422
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert 'not compatible' in trigger['showMessage']['message'].lower()

    def test_equip_armour_unit_with_armour_equipment(self, app, auth_client, nation):
        eq = _make_equipment(nation, eq_type='Heavy Accessory')
        unit = _make_unit(nation, 'm1a1_abrahms')
        resp = auth_client.post('/equipment/equip',
                                data={'equipment_id': eq.id, 'unit_id': unit.id})
        assert resp.status_code == 200
        db.session.refresh(unit)
        assert unit.weapon_id == eq.id  # Heavy Accessory maps to weapon slot

    def test_equip_missing_equipment_id(self, app, auth_client, nation):
        unit = _make_unit(nation)
        resp = auth_client.post('/equipment/equip', data={'unit_id': unit.id})
        assert resp.status_code == 422

    def test_equip_missing_unit_id(self, app, auth_client, nation):
        eq = _make_equipment(nation)
        resp = auth_client.post('/equipment/equip', data={'equipment_id': eq.id})
        assert resp.status_code == 422

    def test_equip_other_nations_equipment_rejected(self, app, auth_client, nation):
        from app.models import User
        u2 = User(username='other2', email='o2@test.com')
        u2.set_password('password')
        db.session.add(u2)
        db.session.flush()
        n2 = Nation(user_id=u2.id, name='Other2', continent='Tind')
        db.session.add(n2)
        db.session.flush()
        eq = _make_equipment(n2)

        unit = _make_unit(nation)
        resp = auth_client.post('/equipment/equip',
                                data={'equipment_id': eq.id, 'unit_id': unit.id})
        assert resp.status_code == 422


# ── Unequip ───────────────────────────────────────────────────────────────

class TestUnequip:
    def test_unequip_weapon(self, app, auth_client, nation):
        eq = _make_equipment(nation, eq_type='Infantry Weapon')
        unit = _make_unit(nation, 'infantry')
        unit.weapon_id = eq.id
        db.session.commit()

        resp = auth_client.post(f'/equipment/unequip/{unit.id}/weapon')
        assert resp.status_code == 200
        db.session.refresh(unit)
        assert unit.weapon_id is None

    def test_unequip_accessory(self, app, auth_client, nation):
        eq = _make_equipment(nation, eq_type='Infantry Accessory')
        unit = _make_unit(nation, 'infantry')
        unit.accessory_id = eq.id
        db.session.commit()

        resp = auth_client.post(f'/equipment/unequip/{unit.id}/accessory')
        assert resp.status_code == 200
        db.session.refresh(unit)
        assert unit.accessory_id is None

    def test_unequip_armour(self, app, auth_client, nation):
        eq = _make_equipment(nation, eq_type='Body Armour')
        unit = _make_unit(nation, 'infantry')
        unit.armour_eq_id = eq.id
        db.session.commit()

        resp = auth_client.post(f'/equipment/unequip/{unit.id}/armour')
        assert resp.status_code == 200
        db.session.refresh(unit)
        assert unit.armour_eq_id is None

    def test_unequip_invalid_slot(self, app, auth_client, nation):
        unit = _make_unit(nation)
        resp = auth_client.post(f'/equipment/unequip/{unit.id}/invalid')
        assert resp.status_code == 422

    def test_unequip_wrong_nation_rejected(self, app, auth_client, nation):
        resp = auth_client.post('/equipment/unequip/99999/weapon')
        assert resp.status_code == 422

    def test_unequip_preserves_equipment(self, app, auth_client, nation):
        """Unequipping should not delete the equipment item."""
        eq = _make_equipment(nation, eq_type='Infantry Weapon')
        unit = _make_unit(nation, 'infantry')
        unit.weapon_id = eq.id
        db.session.commit()

        auth_client.post(f'/equipment/unequip/{unit.id}/weapon')
        assert db.session.get(Equipment, eq.id) is not None


# ── Stacking ─────────────────────────────────────────────────────────────

class TestStacking:
    def test_equip_checks_available_count(self, app, auth_client, nation):
        """Cannot equip if all copies are already equipped."""
        eq = _make_equipment(nation, eq_type='Infantry Weapon', count=1)
        u1 = _make_unit(nation, 'infantry')
        u2 = _make_unit(nation, 'infantry')
        # Equip first copy
        auth_client.post('/equipment/equip',
                         data={'equipment_id': eq.id, 'unit_id': u1.id})
        # Try to equip second copy — should fail (count=1, 1 equipped)
        resp = auth_client.post('/equipment/equip',
                                data={'equipment_id': eq.id, 'unit_id': u2.id})
        assert resp.status_code == 422
        trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
        assert 'available' in trigger['showMessage']['message'].lower()

    def test_equip_stack_multiple_copies(self, app, auth_client, nation):
        """Can equip multiple units from a stack with count > 1."""
        eq = _make_equipment(nation, eq_type='Infantry Weapon', count=2)
        u1 = _make_unit(nation, 'infantry')
        u2 = _make_unit(nation, 'infantry')
        resp1 = auth_client.post('/equipment/equip',
                                 data={'equipment_id': eq.id, 'unit_id': u1.id})
        assert resp1.status_code == 200
        resp2 = auth_client.post('/equipment/equip',
                                 data={'equipment_id': eq.id, 'unit_id': u2.id})
        assert resp2.status_code == 200

    def test_trade_in_full_stack(self, app, auth_client, nation):
        """Trade-in of a stack with no equipped copies deletes the row."""
        eq = _make_equipment(nation, rarity='Rare', count=3)
        eq_id = eq.id
        nation.loot_tokens = 0
        db.session.commit()
        auth_client.post('/equipment/trade-in', data={'ids': str(eq_id)})
        db.session.refresh(nation)
        assert nation.loot_tokens == 15  # 5 per copy * 3
        assert db.session.get(Equipment, eq_id) is None

    def test_trade_in_partial_stack(self, app, auth_client, nation):
        """Trade-in with some copies equipped decrements count."""
        eq = _make_equipment(nation, rarity='Epic', count=5)
        u1 = _make_unit(nation, 'infantry')
        u2 = _make_unit(nation, 'infantry')
        u1.weapon_id = eq.id
        u2.weapon_id = eq.id
        nation.loot_tokens = 0
        db.session.commit()

        auth_client.post('/equipment/trade-in', data={'ids': str(eq.id)})
        db.session.refresh(eq)
        assert eq.count == 2  # 2 equipped remain
        db.session.refresh(nation)
        assert nation.loot_tokens == 45  # 15 per copy * 3 available
