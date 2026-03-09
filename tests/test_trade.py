"""Tests for the trade system — order placement, matching, cancellation, analytics."""
import json
from app import db
from app.models import Nation, NaturalResource, TradeOrder, TradeExecution, User


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_nation(username, password='password', **overrides):
    """Create a user + nation and return the nation."""
    u = User(username=username, email=f'{username}@test.com')
    u.set_password(password)
    db.session.add(u)
    db.session.flush()
    defaults = dict(
        user_id=u.id, name=f'{username.title()}Land', continent='Westberg',
        money=1_000_000, food=100_000, power=100_000,
        building_materials=100_000, consumer_goods=100_000,
        metal=100_000, ammunition=100_000, fuel=100_000,
        uranium=1_000, whz=0,
    )
    defaults.update(overrides)
    n = Nation(**defaults)
    db.session.add(n)
    db.session.commit()
    return n


def _login_route(client, username, password='password'):
    """Log in via the actual login route (reliable user switching)."""
    client.get('/logout')
    client.post('/login', data={'username': username, 'password': password})


def _login(client, nation):
    """Log in by setting the session directly (single-user tests only)."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(nation.user_id)


def _place(client, resource, order_type, quantity, price):
    return client.post('/trade/place-order', data={
        'resource': resource,
        'order_type': order_type,
        'quantity': str(quantity),
        'price': str(price),
    })


def _trigger(resp):
    return json.loads(resp.headers.get('HX-Trigger', '{}'))


def _fresh(nation):
    """Expire and re-read a nation's attributes from DB."""
    db.session.expire(nation)
    # Access an attribute to trigger lazy load
    _ = nation.id
    return nation


# ── Page load tests ──────────────────────────────────────────────────────

class TestTradePages:
    def test_trade_page_loads(self, app, auth_client):
        resp = auth_client.get('/trade')
        assert resp.status_code == 200
        assert b'Global Market' in resp.data

    def test_trade_page_requires_login(self, app, client):
        resp = client.get('/trade')
        assert resp.status_code == 302

    def test_order_book_partial_loads(self, app, auth_client):
        resp = auth_client.get('/trade/order-book?resource=food')
        assert resp.status_code == 200

    def test_my_orders_partial_loads(self, app, auth_client):
        resp = auth_client.get('/trade/my-orders?resource=food')
        assert resp.status_code == 200

    def test_recent_trades_partial_loads(self, app, auth_client):
        resp = auth_client.get('/trade/recent-trades?resource=food')
        assert resp.status_code == 200

    def test_analytics_page_loads(self, app, auth_client):
        resp = auth_client.get('/trade/analytics')
        assert resp.status_code == 200
        assert b'Trade Analytics' in resp.data

    def test_analytics_data_returns_json(self, app, auth_client):
        resp = auth_client.get('/trade/analytics/data?resource=food')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'labels' in data
        assert 'prices' in data
        assert 'best_bid' in data


# ── Order placement tests ────────────────────────────────────────────────

class TestPlaceOrder:
    def test_place_buy_order_escrows_money(self, app, client):
        n = _make_nation('buyer1')
        _login(client, n)
        before = n.money

        resp = _place(client, 'food', 'buy', 100, 10.0)
        assert resp.status_code == 200

        _fresh(n)
        assert n.money == before - 1000

        order = TradeOrder.query.filter_by(nation_id=n.id).first()
        assert order is not None
        assert order.status == 'open'
        assert order.quantity == 100
        assert order.price_per_unit == 10.0
        assert order.order_type == 'buy'

    def test_place_sell_order_escrows_resource(self, app, client):
        n = _make_nation('seller1')
        _login(client, n)
        before = n.food

        resp = _place(client, 'food', 'sell', 500, 5.0)
        assert resp.status_code == 200

        _fresh(n)
        assert n.food == before - 500

        order = TradeOrder.query.filter_by(nation_id=n.id).first()
        assert order.status == 'open'
        assert order.order_type == 'sell'
        assert order.resource_type == 'commodity'

    def test_place_sell_natural_resource(self, app, client):
        n = _make_nation('natseller')
        nr = NaturalResource(nation_id=n.id, resource_key='coal', amount=200)
        db.session.add(nr)
        db.session.commit()
        _login(client, n)

        resp = _place(client, 'coal', 'sell', 50, 20.0)
        assert resp.status_code == 200

        db.session.expire(nr)
        assert nr.amount == 150

        order = TradeOrder.query.filter_by(nation_id=n.id).first()
        assert order.resource_type == 'natural'

    def test_buy_insufficient_money_rejected(self, app, client):
        n = _make_nation('broke', money=100)
        _login(client, n)
        resp = _place(client, 'food', 'buy', 1000, 10.0)
        assert resp.status_code == 422
        assert _trigger(resp)['showMessage']['type'] == 'error'
        assert TradeOrder.query.filter_by(nation_id=n.id).count() == 0

    def test_sell_insufficient_resource_rejected(self, app, client):
        n = _make_nation('emptyseller', food=10)
        _login(client, n)
        resp = _place(client, 'food', 'sell', 100, 5.0)
        assert resp.status_code == 422
        assert _trigger(resp)['showMessage']['type'] == 'error'

    def test_sell_natural_insufficient_rejected(self, app, client):
        n = _make_nation('nopetroleum')
        _login(client, n)
        resp = _place(client, 'petroleum', 'sell', 10, 50.0)
        assert resp.status_code == 422

    def test_invalid_resource_rejected(self, app, client):
        n = _make_nation('badres')
        _login(client, n)
        resp = _place(client, 'unobtanium', 'buy', 10, 1.0)
        assert resp.status_code == 422

    def test_invalid_order_type_rejected(self, app, client):
        n = _make_nation('badtype')
        _login(client, n)
        resp = client.post('/trade/place-order', data={
            'resource': 'food', 'order_type': 'short', 'quantity': '10', 'price': '1',
        })
        assert resp.status_code == 422

    def test_zero_quantity_rejected(self, app, client):
        n = _make_nation('zeroqty')
        _login(client, n)
        resp = _place(client, 'food', 'buy', 0, 10.0)
        assert resp.status_code == 422

    def test_negative_price_rejected(self, app, client):
        n = _make_nation('negprice')
        _login(client, n)
        resp = _place(client, 'food', 'buy', 10, -5)
        assert resp.status_code == 422

    def test_success_message_for_unmatched_order(self, app, client):
        n = _make_nation('msgtest')
        _login(client, n)
        resp = _place(client, 'food', 'buy', 50, 2.0)
        msg = _trigger(resp)['showMessage']['message']
        assert 'placed' in msg.lower()


# ── Order matching tests ─────────────────────────────────────────────────

class TestOrderMatching:
    def test_exact_match_buy_into_sell(self, app, client):
        """A buy order matching an existing sell order fills both instantly."""
        seller = _make_nation('seller_a', password='pw')
        buyer = _make_nation('buyer_a', password='pw')

        _login_route(client, 'seller_a', 'pw')
        _place(client, 'food', 'sell', 100, 5.0)

        _login_route(client, 'buyer_a', 'pw')
        resp = _place(client, 'food', 'buy', 100, 5.0)
        assert resp.status_code == 200

        db.session.expire_all()

        # Buyer: escrowed 500 money, got 100 food
        assert buyer.food == 100_000 + 100
        assert buyer.money == 1_000_000 - 500

        # Seller: escrowed 100 food, got 500 - 5% fee = 475 money
        assert seller.money == 1_000_000 + 475
        assert seller.food == 100_000 - 100

        # Both orders filled
        sell_order = TradeOrder.query.filter_by(nation_id=seller.id).first()
        buy_order = TradeOrder.query.filter_by(nation_id=buyer.id).first()
        assert sell_order.status == 'filled'
        assert buy_order.status == 'filled'

        # One execution record
        ex = TradeExecution.query.first()
        assert ex is not None
        assert ex.quantity == 100
        assert ex.price_per_unit == 5.0
        assert ex.total_cost == 500
        assert ex.fee == 25
        assert ex.buyer_nation_id == buyer.id
        assert ex.seller_nation_id == seller.id

    def test_buyer_price_improvement(self, app, client):
        """When buyer offers 10 but sell rests at 5, execution at 5 and buyer gets refund."""
        seller = _make_nation('seller_pi', password='pw')
        buyer = _make_nation('buyer_pi', password='pw')

        _login_route(client, 'seller_pi', 'pw')
        _place(client, 'food', 'sell', 100, 5.0)

        _login_route(client, 'buyer_pi', 'pw')
        _place(client, 'food', 'buy', 100, 10.0)

        db.session.expire_all()
        # Escrowed 100*10=1000, execution at 5, refund 100*(10-5)=500 → net cost 500
        assert buyer.money == 1_000_000 - 500

        ex = TradeExecution.query.first()
        assert ex.price_per_unit == 5.0

    def test_partial_fill(self, app, client):
        """Partially fills when resting liquidity is insufficient."""
        seller = _make_nation('seller_pf', password='pw')
        buyer = _make_nation('buyer_pf', password='pw')

        _login_route(client, 'seller_pf', 'pw')
        _place(client, 'food', 'sell', 30, 5.0)

        _login_route(client, 'buyer_pf', 'pw')
        resp = _place(client, 'food', 'buy', 100, 5.0)
        msg = _trigger(resp)['showMessage']['message']
        assert 'partially' in msg.lower()

        db.session.expire_all()
        buy_order = TradeOrder.query.filter_by(nation_id=buyer.id).first()
        assert buy_order.quantity_filled == 30
        assert buy_order.status == 'open'

        sell_order = TradeOrder.query.filter_by(nation_id=seller.id).first()
        assert sell_order.status == 'filled'

    def test_no_match_when_prices_dont_cross(self, app, client):
        """A buy at 3 does not match a sell at 5."""
        seller = _make_nation('seller_nm', password='pw')
        buyer = _make_nation('buyer_nm', password='pw')

        _login_route(client, 'seller_nm', 'pw')
        _place(client, 'food', 'sell', 100, 5.0)

        _login_route(client, 'buyer_nm', 'pw')
        _place(client, 'food', 'buy', 100, 3.0)

        assert TradeExecution.query.count() == 0
        assert TradeOrder.query.filter_by(status='open').count() == 2

    def test_sell_matches_resting_buy(self, app, client):
        """A new sell order matches resting buy orders."""
        buyer = _make_nation('buyer_sm', password='pw')
        seller = _make_nation('seller_sm', password='pw')

        _login_route(client, 'buyer_sm', 'pw')
        _place(client, 'food', 'buy', 50, 8.0)

        _login_route(client, 'seller_sm', 'pw')
        _place(client, 'food', 'sell', 50, 6.0)

        db.session.expire_all()

        # Execution at resting order's price (buyer's price = 8.0)
        ex = TradeExecution.query.first()
        assert ex.price_per_unit == 8.0
        assert ex.fee == 50 * 8.0 * 0.05  # 20

        # Buyer got 50 food
        assert buyer.food == 100_000 + 50
        # Seller got money minus fee
        assert seller.money == 1_000_000 + (50 * 8.0) - (50 * 8.0 * 0.05)

    def test_multiple_resting_orders_price_time_priority(self, app, client):
        """When multiple sell orders exist, cheapest is matched first."""
        seller1 = _make_nation('s1', password='pw')
        seller2 = _make_nation('s2', password='pw')
        buyer = _make_nation('b1', password='pw')

        _login_route(client, 's1', 'pw')
        _place(client, 'food', 'sell', 50, 7.0)

        _login_route(client, 's2', 'pw')
        _place(client, 'food', 'sell', 50, 5.0)

        _login_route(client, 'b1', 'pw')
        _place(client, 'food', 'buy', 80, 7.0)

        execs = TradeExecution.query.order_by(TradeExecution.id).all()
        assert len(execs) == 2
        assert execs[0].price_per_unit == 5.0
        assert execs[0].quantity == 50
        assert execs[0].seller_nation_id == seller2.id
        assert execs[1].price_per_unit == 7.0
        assert execs[1].quantity == 30
        assert execs[1].seller_nation_id == seller1.id

    def test_fee_is_five_percent(self, app, client):
        """Verify the 5% fee calculation."""
        seller = _make_nation('feeseller', password='pw')
        buyer = _make_nation('feebuyer', password='pw')

        _login_route(client, 'feeseller', 'pw')
        _place(client, 'food', 'sell', 200, 10.0)

        _login_route(client, 'feebuyer', 'pw')
        _place(client, 'food', 'buy', 200, 10.0)

        ex = TradeExecution.query.first()
        assert ex.total_cost == 2000
        assert ex.fee == 100

    def test_natural_resource_matching(self, app, client):
        """Trade matching works for natural resources."""
        seller = _make_nation('ironseller', password='pw')
        nr = NaturalResource(nation_id=seller.id, resource_key='iron', amount=500)
        db.session.add(nr)
        db.session.commit()

        buyer = _make_nation('ironbuyer', password='pw')

        _login_route(client, 'ironseller', 'pw')
        _place(client, 'iron', 'sell', 100, 20.0)

        _login_route(client, 'ironbuyer', 'pw')
        _place(client, 'iron', 'buy', 100, 20.0)

        db.session.expire_all()
        assert nr.amount == 400  # 500 - 100 escrowed

        buyer_iron = NaturalResource.query.filter_by(
            nation_id=buyer.id, resource_key='iron'
        ).first()
        assert buyer_iron is not None
        assert buyer_iron.amount == 100

        ex = TradeExecution.query.first()
        assert ex.resource_type == 'natural'

    def test_self_trade_works(self, app, client):
        """A nation can fill its own resting order."""
        n = _make_nation('selftrader')
        _login(client, n)

        _place(client, 'food', 'sell', 50, 5.0)
        _place(client, 'food', 'buy', 50, 5.0)

        ex = TradeExecution.query.first()
        assert ex is not None
        assert ex.buyer_nation_id == n.id
        assert ex.seller_nation_id == n.id


# ── Cancel order tests ───────────────────────────────────────────────────

class TestCancelOrder:
    def test_cancel_buy_order_refunds_money(self, app, client):
        n = _make_nation('cancelbuyer')
        _login(client, n)

        _place(client, 'food', 'buy', 100, 10.0)
        _fresh(n)
        money_after_place = n.money

        order = TradeOrder.query.filter_by(nation_id=n.id).first()
        resp = client.post(f'/trade/cancel-order/{order.id}')
        assert resp.status_code == 200

        _fresh(n)
        assert n.money == money_after_place + 1000
        db.session.expire(order)
        assert order.status == 'cancelled'

    def test_cancel_sell_order_refunds_resource(self, app, client):
        n = _make_nation('cancelseller')
        _login(client, n)

        _place(client, 'food', 'sell', 200, 5.0)
        _fresh(n)
        food_after = n.food

        order = TradeOrder.query.filter_by(nation_id=n.id).first()
        client.post(f'/trade/cancel-order/{order.id}')

        _fresh(n)
        assert n.food == food_after + 200

    def test_cancel_natural_sell_refunds_natural_resource(self, app, client):
        n = _make_nation('cancelnat')
        nr = NaturalResource(nation_id=n.id, resource_key='gold', amount=100)
        db.session.add(nr)
        db.session.commit()
        _login(client, n)

        _place(client, 'gold', 'sell', 30, 100.0)
        db.session.expire(nr)
        assert nr.amount == 70

        order = TradeOrder.query.filter_by(nation_id=n.id).first()
        client.post(f'/trade/cancel-order/{order.id}')

        db.session.expire(nr)
        assert nr.amount == 100

    def test_cancel_partially_filled_order(self, app, client):
        """Cancelling a partially filled buy refunds the unfilled portion."""
        seller = _make_nation('partseller', password='pw')
        buyer = _make_nation('partbuyer', password='pw')

        _login_route(client, 'partseller', 'pw')
        _place(client, 'food', 'sell', 30, 5.0)

        _login_route(client, 'partbuyer', 'pw')
        _place(client, 'food', 'buy', 100, 5.0)

        db.session.expire_all()
        money_after_partial = buyer.money

        order = TradeOrder.query.filter_by(nation_id=buyer.id).first()
        assert order.quantity_filled == 30
        assert order.status == 'open'

        resp = client.post(f'/trade/cancel-order/{order.id}')
        assert resp.status_code == 200

        db.session.expire_all()
        refund = 70 * 5.0
        assert buyer.money == money_after_partial + refund

    def test_cancel_other_nations_order_rejected(self, app, client):
        n1 = _make_nation('owner', password='pw')
        n2 = _make_nation('thief', password='pw')

        _login_route(client, 'owner', 'pw')
        _place(client, 'food', 'sell', 50, 5.0)
        order = TradeOrder.query.filter_by(nation_id=n1.id).first()

        _login_route(client, 'thief', 'pw')
        resp = client.post(f'/trade/cancel-order/{order.id}')
        assert resp.status_code == 422

    def test_cancel_nonexistent_order_rejected(self, app, client):
        n = _make_nation('noorder')
        _login(client, n)
        resp = client.post('/trade/cancel-order/99999')
        assert resp.status_code == 422

    def test_cancel_already_filled_rejected(self, app, client):
        seller = _make_nation('filledseller', password='pw')
        buyer = _make_nation('filledbuyer', password='pw')

        _login_route(client, 'filledseller', 'pw')
        _place(client, 'food', 'sell', 50, 5.0)

        _login_route(client, 'filledbuyer', 'pw')
        _place(client, 'food', 'buy', 50, 5.0)

        _login_route(client, 'filledseller', 'pw')
        order = TradeOrder.query.filter_by(nation_id=seller.id).first()
        assert order.status == 'filled'
        resp = client.post(f'/trade/cancel-order/{order.id}')
        assert resp.status_code == 422


# ── Analytics data tests ─────────────────────────────────────────────────

class TestAnalyticsData:
    def test_analytics_data_reflects_executions(self, app, client):
        seller = _make_nation('anaseller', password='pw')
        buyer = _make_nation('anabuyer', password='pw')

        _login_route(client, 'anaseller', 'pw')
        _place(client, 'food', 'sell', 100, 8.0)

        _login_route(client, 'anabuyer', 'pw')
        _place(client, 'food', 'buy', 100, 8.0)

        resp = client.get('/trade/analytics/data?resource=food&days=7')
        data = resp.get_json()

        assert len(data['labels']) == 1
        assert data['volumes'][0] == 100
        assert data['prices'][0] == 8.0
        assert data['volume_24h'] == 100
        assert data['high_24h'] == 8.0
        assert data['low_24h'] == 8.0

    def test_analytics_best_bid_ask(self, app, client):
        n1 = _make_nation('bidder', password='pw')
        n2 = _make_nation('asker', password='pw')

        _login_route(client, 'bidder', 'pw')
        _place(client, 'metal', 'buy', 50, 12.0)

        _login_route(client, 'asker', 'pw')
        _place(client, 'metal', 'sell', 50, 15.0)

        resp = client.get('/trade/analytics/data?resource=metal')
        data = resp.get_json()
        assert data['best_bid'] == 12.0
        assert data['best_ask'] == 15.0

    def test_analytics_empty_returns_zeroes(self, app, auth_client):
        resp = auth_client.get('/trade/analytics/data?resource=whz')
        data = resp.get_json()
        assert data['labels'] == []
        assert data['volume_24h'] == 0
        assert data['best_bid'] == 0
        assert data['best_ask'] == 0


# ── Resource conservation tests ──────────────────────────────────────────

class TestResourceConservation:
    """Ensure no resources are created or destroyed by the trade system."""

    def test_commodity_conservation_on_fill(self, app, client):
        """Total money + food across both nations conserved (minus fee)."""
        seller = _make_nation('conseller', password='pw', money=500_000, food=50_000)
        buyer = _make_nation('conbuyer', password='pw', money=500_000, food=50_000)

        total_money_before = seller.money + buyer.money
        total_food_before = seller.food + buyer.food

        _login_route(client, 'conseller', 'pw')
        _place(client, 'food', 'sell', 1000, 10.0)

        _login_route(client, 'conbuyer', 'pw')
        _place(client, 'food', 'buy', 1000, 10.0)

        db.session.expire_all()

        total_food_after = seller.food + buyer.food
        total_money_after = seller.money + buyer.money

        assert total_food_after == total_food_before
        fee = 1000 * 10.0 * 0.05
        assert abs(total_money_after - (total_money_before - fee)) < 0.01

    def test_money_conservation_on_cancel(self, app, client):
        """Placing and cancelling a buy order returns money exactly."""
        n = _make_nation('moneycon')
        money_start = n.money
        _login(client, n)

        _place(client, 'food', 'buy', 100, 10.0)
        _fresh(n)
        assert n.money == money_start - 1000

        order = TradeOrder.query.filter_by(nation_id=n.id).first()
        client.post(f'/trade/cancel-order/{order.id}')
        _fresh(n)
        assert n.money == money_start

    def test_resource_conservation_on_cancel_sell(self, app, client):
        """Placing and cancelling a sell order returns the resource exactly."""
        n = _make_nation('foodcon')
        food_start = n.food
        _login(client, n)

        _place(client, 'food', 'sell', 500, 5.0)
        _fresh(n)
        assert n.food == food_start - 500

        order = TradeOrder.query.filter_by(nation_id=n.id).first()
        client.post(f'/trade/cancel-order/{order.id}')
        _fresh(n)
        assert n.food == food_start

    def test_buyer_refund_on_price_improvement_conserves_money(self, app, client):
        """Refund + seller proceeds + fee = total escrowed money."""
        seller = _make_nation('refundseller', password='pw', money=100_000, food=10_000)
        buyer = _make_nation('refundbuyer', password='pw', money=100_000, food=10_000)

        total_money_before = seller.money + buyer.money

        _login_route(client, 'refundseller', 'pw')
        _place(client, 'food', 'sell', 100, 5.0)

        _login_route(client, 'refundbuyer', 'pw')
        _place(client, 'food', 'buy', 100, 10.0)

        db.session.expire_all()

        total_money_after = seller.money + buyer.money
        assert abs(total_money_after - (total_money_before - 25)) < 0.01
