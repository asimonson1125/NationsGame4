import json
from app import db

def test_convert_to_cleared_land_success(app, auth_client, nation):
    # Set up initial state
    nation.forest = 100
    nation.money = 10000
    nation.cleared_land = 0
    db.session.commit()

    # Convert 10 forest to cleared land (cost: 10 * 100 = 1000)
    resp = auth_client.post('/convert-to-cleared-land', data={
        'land_type': 'forest',
        'convert_amount': '10'
    })

    assert resp.status_code == 200
    db.session.refresh(nation)
    assert nation.forest == 90
    assert nation.cleared_land == 10
    assert nation.money == 9000
    
    # Check trigger
    trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
    assert 'showMessage' in trigger
    assert 'Converted 10 forest tiles' in trigger['showMessage']['message']

def test_convert_to_cleared_land_insufficient_land(app, auth_client, nation):
    nation.forest = 5
    nation.money = 10000
    db.session.commit()

    resp = auth_client.post('/convert-to-cleared-land', data={
        'land_type': 'forest',
        'convert_amount': '10'
    })

    assert resp.status_code == 422
    trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
    assert 'Not enough forest' in trigger['showMessage']['message']

def test_convert_to_cleared_land_insufficient_money(app, auth_client, nation):
    nation.forest = 100
    nation.money = 500
    db.session.commit()

    resp = auth_client.post('/convert-to-cleared-land', data={
        'land_type': 'forest',
        'convert_amount': '10'
    })

    assert resp.status_code == 422
    trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
    assert 'Insufficient money' in trigger['showMessage']['message']

def test_convert_to_cleared_land_invalid_type(app, auth_client, nation):
    resp = auth_client.post('/convert-to-cleared-land', data={
        'land_type': 'invalid_type',
        'convert_amount': '10'
    })

    assert resp.status_code == 422
    trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
    assert 'Invalid land type' in trigger['showMessage']['message']

def test_convert_to_cleared_land_invalid_amount(app, auth_client, nation):
    resp = auth_client.post('/convert-to-cleared-land', data={
        'land_type': 'forest',
        'convert_amount': '-5'
    })

    assert resp.status_code == 422
    trigger = json.loads(resp.headers.get('HX-Trigger', '{}'))
    assert 'Amount must be greater than zero' in trigger['showMessage']['message']
