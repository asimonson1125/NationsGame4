import json
from datetime import datetime, timezone
from flask import render_template, request, current_app, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from .. import db
from ..models import Nation, NaturalResource, TradeOrder, TradeExecution, Message
from ..helpers import error_response, success_response
from ..game.constants import (
    TRADE_FEE_PERCENT, TRADEABLE_COMMODITIES, TRADEABLE_NATURAL_RESOURCES,
)
from . import trade


def _resource_type(key):
    if key in TRADEABLE_COMMODITIES:
        return 'commodity'
    if key in TRADEABLE_NATURAL_RESOURCES:
        return 'natural'
    return None


def _get_natural_resource(nation_id, key):
    return NaturalResource.query.filter_by(
        nation_id=nation_id, resource_key=key
    ).first()


def _add_natural_resource(nation_id, key, amount):
    nr = _get_natural_resource(nation_id, key)
    if nr:
        nr.amount += amount
    else:
        nr = NaturalResource(nation_id=nation_id, resource_key=key, amount=amount)
        db.session.add(nr)


def _get_balance(nation, key, rtype):
    if rtype == 'commodity':
        return nation.get_resource(key)
    nr = _get_natural_resource(nation.id, key)
    return nr.amount if nr else 0


def _add_balance(nation, key, rtype, amount):
    if rtype == 'commodity':
        nation.add_resource(key, amount)
    else:
        _add_natural_resource(nation.id, key, amount)


def _deduct_balance(nation, key, rtype, amount):
    _add_balance(nation, key, rtype, -amount)


def _match_orders(new_order):
    """Match a new order against resting orders on the opposite side."""
    if new_order.order_type == 'buy':
        # Find cheapest sell orders at or below buyer's price
        resting = TradeOrder.query.filter(
            TradeOrder.resource_key == new_order.resource_key,
            TradeOrder.order_type == 'sell',
            TradeOrder.status == 'open',
            TradeOrder.price_per_unit <= new_order.price_per_unit,
        ).order_by(TradeOrder.price_per_unit.asc(), TradeOrder.created_at.asc()).all()
    else:
        # Find highest buy orders at or above seller's price
        resting = TradeOrder.query.filter(
            TradeOrder.resource_key == new_order.resource_key,
            TradeOrder.order_type == 'buy',
            TradeOrder.status == 'open',
            TradeOrder.price_per_unit >= new_order.price_per_unit,
        ).order_by(TradeOrder.price_per_unit.desc(), TradeOrder.created_at.asc()).all()

    for rest in resting:
        if new_order.quantity_filled >= new_order.quantity:
            break

        new_remaining = new_order.quantity - new_order.quantity_filled
        rest_remaining = rest.quantity - rest.quantity_filled
        fill_qty = min(new_remaining, rest_remaining)

        execution_price = rest.price_per_unit
        total_cost = fill_qty * execution_price
        fee = total_cost * TRADE_FEE_PERCENT / 100

        # Determine buyer/seller nations
        if new_order.order_type == 'buy':
            buyer = db.session.get(Nation, new_order.nation_id)
            seller = db.session.get(Nation, rest.nation_id)
            buyer_order = new_order
        else:
            buyer = db.session.get(Nation, rest.nation_id)
            seller = db.session.get(Nation, new_order.nation_id)
            buyer_order = rest

        # Buyer receives resources
        _add_balance(buyer, new_order.resource_key, new_order.resource_type, fill_qty)

        # Seller receives money minus fee
        seller.add_resource('money', total_cost - fee)

        # If buyer escrowed at a higher price, refund the difference
        if new_order.order_type == 'buy' and new_order.price_per_unit > execution_price:
            refund = fill_qty * (new_order.price_per_unit - execution_price)
            buyer.add_resource('money', refund)
        elif new_order.order_type == 'sell' and rest.price_per_unit > execution_price:
            # Resting buy order escrowed at their price; execution is at sell (new) price
            # but execution_price = rest.price_per_unit, so no refund needed
            pass

        # Create execution record
        execution = TradeExecution(
            buyer_nation_id=buyer.id,
            seller_nation_id=seller.id,
            resource_key=new_order.resource_key,
            resource_type=new_order.resource_type,
            quantity=fill_qty,
            price_per_unit=execution_price,
            total_cost=total_cost,
            fee=fee,
        )
        db.session.add(execution)

        # Send system mail to buyer and seller
        res_label = new_order.resource_key.replace('_', ' ').title()
        seller_link = f'<a href="/nation/{seller.id}" class="text-amber-400 hover:text-amber-300">{seller.name}</a>'
        buyer_link = f'<a href="/nation/{buyer.id}" class="text-amber-400 hover:text-amber-300">{buyer.name}</a>'
        db.session.add(Message(
            sender_id=None,
            recipient_id=buyer.id,
            subject=f'Trade Fulfilled \u2014 Bought {res_label}',
            body=(
                f'You bought {fill_qty:,} {res_label} '
                f'at ${execution_price:,.2f}/ea from {seller_link}.\n'
                f'Total cost: ${total_cost:,.2f}.'
            ),
            message_type='system',
        ))
        db.session.add(Message(
            sender_id=None,
            recipient_id=seller.id,
            subject=f'Trade Fulfilled \u2014 Sold {res_label}',
            body=(
                f'You sold {fill_qty:,} {res_label} '
                f'at ${execution_price:,.2f}/ea to {buyer_link}.\n'
                f'Revenue: ${total_cost - fee:,.2f} (fee: ${fee:,.2f}).'
            ),
            message_type='system',
        ))

        # Update fill quantities
        new_order.quantity_filled += fill_qty
        rest.quantity_filled += fill_qty

        if rest.quantity_filled >= rest.quantity:
            rest.status = 'filled'

    if new_order.quantity_filled >= new_order.quantity:
        new_order.status = 'filled'


# ── Page routes ──────────────────────────────────────────────────────────

@trade.route('/trade')
@login_required
def trade_page():
    nation = current_user.nation
    resource = request.args.get('resource', 'food')

    # Build balances dictionary for all tradeable items
    balances = {'money': nation.get_resource('money')}
    for c in TRADEABLE_COMMODITIES:
        balances[c] = nation.get_resource(c)
    
    # Get all natural resources for this nation in one query
    nrs = NaturalResource.query.filter_by(nation_id=nation.id).all()
    nr_map = {nr.resource_key: nr.amount for nr in nrs}
    for nr_key in TRADEABLE_NATURAL_RESOURCES:
        balances[nr_key] = nr_map.get(nr_key, 0)

    return render_template(
        'trade/trade.html',
        nation=nation,
        commodities=TRADEABLE_COMMODITIES,
        natural_resources=TRADEABLE_NATURAL_RESOURCES,
        selected_resource=resource,
        fee_pct=TRADE_FEE_PERCENT,
        balances=balances,
    )


@trade.route('/trade/order-book')
@login_required
def order_book():
    resource = request.args.get('resource', 'food')

    # Get top 10 buy orders (highest price first)
    buy_orders = TradeOrder.query.filter(
        TradeOrder.resource_key == resource,
        TradeOrder.order_type == 'buy',
        TradeOrder.status == 'open',
    ).order_by(TradeOrder.price_per_unit.desc(), TradeOrder.created_at.asc())\
     .limit(10).all()

    # Get top 10 sell orders (lowest price first)
    sell_orders = TradeOrder.query.filter(
        TradeOrder.resource_key == resource,
        TradeOrder.order_type == 'sell',
        TradeOrder.status == 'open',
    ).order_by(TradeOrder.price_per_unit.asc(), TradeOrder.created_at.asc())\
     .limit(10).all()

    return render_template(
        'trade/partials/order_book.html',
        buy_orders=buy_orders,
        sell_orders=sell_orders,
        resource=resource,
    )


@trade.route('/trade/place-order', methods=['POST'])
@login_required
def place_order():
    nation = current_user.nation
    if not nation:
        return error_response('No nation found.')

    resource = request.form.get('resource', '').strip()
    order_type = request.form.get('order_type', '').strip()
    rtype = _resource_type(resource)

    if not rtype:
        return error_response('Invalid resource.')
    if order_type not in ('buy', 'sell'):
        return error_response('Invalid order type.')

    try:
        quantity = int(request.form.get('quantity', 0))
        price = float(request.form.get('price', 0))
    except (ValueError, TypeError):
        return error_response('Invalid quantity or price.')

    if quantity <= 0:
        return error_response('Quantity must be greater than zero.')
    if price <= 0:
        return error_response('Price must be greater than zero.')

    # Escrow
    if order_type == 'buy':
        total_money = quantity * price
        if nation.get_resource('money') < total_money:
            return error_response(f'Insufficient money. Need {total_money:,.0f}.')
        nation.add_resource('money', -total_money)
    else:
        balance = _get_balance(nation, resource, rtype)
        if balance < quantity:
            return error_response(f'Insufficient {resource.replace("_", " ")}. Have {balance:,}, need {quantity:,}.')
        _deduct_balance(nation, resource, rtype, quantity)

    order = TradeOrder(
        nation_id=nation.id,
        resource_key=resource,
        resource_type=rtype,
        order_type=order_type,
        price_per_unit=price,
        quantity=quantity,
    )
    db.session.add(order)
    db.session.flush()  # get order.id before matching

    _match_orders(order)
    db.session.commit()

    if order.status == 'filled':
        msg = f'{order_type.title()} order fully filled! ({quantity:,} {resource.replace("_", " ")})'
    elif order.quantity_filled > 0:
        msg = f'{order_type.title()} order partially filled ({order.quantity_filled:,}/{quantity:,}). Remainder on book.'
    else:
        msg = f'{order_type.title()} order placed for {quantity:,} {resource.replace("_", " ")} @ {price:,.2f}/ea.'

    # Return refreshed order book
    buy_orders = TradeOrder.query.filter(
        TradeOrder.resource_key == resource,
        TradeOrder.order_type == 'buy',
        TradeOrder.status == 'open',
    ).order_by(TradeOrder.price_per_unit.desc(), TradeOrder.created_at.asc())\
     .limit(10).all()

    sell_orders = TradeOrder.query.filter(
        TradeOrder.resource_key == resource,
        TradeOrder.order_type == 'sell',
        TradeOrder.status == 'open',
    ).order_by(TradeOrder.price_per_unit.asc(), TradeOrder.created_at.asc())\
     .limit(10).all()

    html = render_template(
        'trade/partials/order_book.html',
        buy_orders=buy_orders,
        sell_orders=sell_orders,
        resource=resource,
    )
    resp = current_app.response_class(html, status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': msg, 'type': 'success'},
        'refreshResourceFooter': True,
        'refreshMyOrders': True,
        'refreshRecentTrades': True,
    })
    return resp


@trade.route('/trade/cancel-order/<int:order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    nation = current_user.nation
    if not nation:
        return error_response('No nation found.')

    order = db.session.get(TradeOrder, (order_id, nation.id))
    if not order or order.nation_id != nation.id:
        return error_response('Order not found.')
    if order.status != 'open':
        return error_response('Order is not open.')

    remaining = order.quantity - order.quantity_filled

    # Refund escrowed resources
    if order.order_type == 'buy':
        nation.add_resource('money', remaining * order.price_per_unit)
    else:
        _add_balance(nation, order.resource_key, order.resource_type, remaining)

    order.status = 'cancelled'
    db.session.commit()

    # Return refreshed my-orders partial
    orders = TradeOrder.query.filter_by(nation_id=nation.id)\
        .order_by(TradeOrder.created_at.desc()).limit(50).all()

    html = render_template(
        'trade/partials/my_orders.html',
        orders=orders,
    )
    resp = current_app.response_class(html, status=200, mimetype='text/html')
    resp.headers['HX-Trigger'] = json.dumps({
        'showMessage': {'message': 'Order cancelled. Resources refunded.', 'type': 'success'},
        'refreshResourceFooter': True,
        'refreshOrderBook': True,
    })
    return resp


@trade.route('/trade/my-orders')
@login_required
def my_orders():
    nation = current_user.nation
    orders = TradeOrder.query.filter_by(nation_id=nation.id)\
        .order_by(TradeOrder.created_at.desc()).limit(50).all()
    return render_template(
        'trade/partials/my_orders.html',
        orders=orders,
    )


@trade.route('/trade/recent-trades')
@login_required
def recent_trades():
    executions = TradeExecution.query\
        .options(joinedload(TradeExecution.buyer_nation), joinedload(TradeExecution.seller_nation))\
        .order_by(TradeExecution.executed_at.desc()).limit(20).all()
    return render_template(
        'trade/partials/recent_trades.html',
        executions=executions,
    )


# ── Analytics ────────────────────────────────────────────────────────────

@trade.route('/trade/analytics')
@login_required
def analytics():
    resource = request.args.get('resource', 'food')
    from flask import redirect, url_for
    return redirect(url_for('trade.trade_page', resource=resource, view='analytics'))


@trade.route('/trade/analytics/data')
@login_required
def analytics_data():
    resource = request.args.get('resource', 'food')
    days = int(request.args.get('days', 30))

    cutoff = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    from datetime import timedelta
    cutoff = cutoff - timedelta(days=days)

    executions = TradeExecution.query.filter(
        TradeExecution.resource_key == resource,
        TradeExecution.executed_at >= cutoff,
    ).order_by(TradeExecution.executed_at.asc()).all()

    # Build daily aggregates
    daily = {}
    for ex in executions:
        day = ex.executed_at.strftime('%Y-%m-%d')
        if day not in daily:
            daily[day] = {'volume': 0, 'total_value': 0, 'high': 0, 'low': float('inf'), 'last_price': 0}
        d = daily[day]
        d['volume'] += ex.quantity
        d['total_value'] += ex.total_cost
        d['high'] = max(d['high'], ex.price_per_unit)
        d['low'] = min(d['low'], ex.price_per_unit)
        d['last_price'] = ex.price_per_unit

    labels = sorted(daily.keys())
    prices = [daily[d]['last_price'] for d in labels]
    volumes = [daily[d]['volume'] for d in labels]
    highs = [daily[d]['high'] for d in labels]
    lows = [daily[d]['low'] if daily[d]['low'] != float('inf') else 0 for d in labels]

    # Current best bid/ask
    best_bid = db.session.query(func.max(TradeOrder.price_per_unit)).filter(
        TradeOrder.resource_key == resource,
        TradeOrder.order_type == 'buy',
        TradeOrder.status == 'open',
    ).scalar() or 0

    best_ask = db.session.query(func.min(TradeOrder.price_per_unit)).filter(
        TradeOrder.resource_key == resource,
        TradeOrder.order_type == 'sell',
        TradeOrder.status == 'open',
    ).scalar() or 0

    # 24h stats
    from datetime import timedelta
    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = TradeExecution.query.filter(
        TradeExecution.resource_key == resource,
        TradeExecution.executed_at >= cutoff_24h,
    ).all()

    vol_24h = sum(e.quantity for e in recent)
    high_24h = max((e.price_per_unit for e in recent), default=0)
    low_24h = min((e.price_per_unit for e in recent), default=0)

    return jsonify({
        'labels': labels,
        'prices': prices,
        'volumes': volumes,
        'highs': highs,
        'lows': lows,
        'best_bid': best_bid,
        'best_ask': best_ask,
        'volume_24h': vol_24h,
        'high_24h': high_24h,
        'low_24h': low_24h,
    })
