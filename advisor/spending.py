import hashlib
import json
import re
import secrets

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from accounts import account
from catalog import connect


def compare_purchase(card, estimates):
    best = min((item for item in estimates if item['cashbackKopecks'] > 0),
               key=lambda item: (-item['cashbackKopecks'], item['cardId']), default=None)
    used = next((item['cashbackKopecks'] for item in estimates if item['cardId'] == card['id']), None) if card else None
    return dict(
        usedCardCashbackKopecks=used,
        bestCardName=best['name'] if best else None,
        bestCashbackKopecks=best['cashbackKopecks'] if best else None,
        differenceKopecks=best['cashbackKopecks'] - used if best and used is not None else None,
    )


def summarize(month, records):
    purchases, totals, caps = [], {}, {}
    groups = {'byCategory': {}, 'byMerchant': {}, 'byUsedCard': {}}
    for id_, day, category, merchant, amount, used, estimates, actual in records:
        card = json.loads(used) if used else None
        options = json.loads(estimates)
        purchases.append(dict(id=id_, date=day, categoryName=category, merchant=merchant,
                              amountKopecks=amount, cardName=card['name'] if card else None,
                              cashbackComparison=compare_purchase(card, options), actualCashbackKopecks=actual))
        for group, key, label in [('byCategory', category.casefold(), category),
                                  ('byMerchant', merchant.casefold(), merchant),
                                  ('byUsedCard', card['id'] if card else None, card['name'] if card else '')]:
            if label:
                entry = groups[group].setdefault(key, dict(name=label, amountKopecks=0))
                entry['amountKopecks'] += amount
        for estimate in options:
            if estimate['cashbackKopecks'] <= 0:
                continue
            key = estimate['cardId']
            entry = totals.setdefault(key, dict(cardId=key, name=estimate['name'], estimatedKopecks=0))
            entry['estimatedKopecks'] += estimate['cashbackKopecks']
            cap = estimate['monthlyCapKopecks']
            if cap is not None:
                caps[key] = min(caps.get(key, cap), cap)
    for key, cap in caps.items():
        totals[key]['estimatedKopecks'] = min(totals[key]['estimatedKopecks'], cap)
    ordered = lambda items, field: sorted(items, key=lambda item: (-item[field], item['name'].casefold()))
    confirmed = [p["actualCashbackKopecks"] for p in purchases if p["actualCashbackKopecks"] is not None]
    return dict(month=month, count=len(purchases), actualCashbackKopecks=sum(confirmed), actualCashbackCount=len(confirmed), totalKopecks=sum(p['amountKopecks'] for p in purchases),
                largestPurchase=max(purchases, key=lambda p: p['amountKopecks'], default=None), purchases=purchases,
                cardRanking=ordered((x for x in totals.values() if x['estimatedKopecks'] > 0), 'estimatedKopecks'),
                **{key:ordered(group.values(), 'amountKopecks') for key, group in groups.items()})


def mount_spending(app, db_path, today, normalize_label, iso_day, estimate_cards):
    @app.post('/api/me/purchases', status_code=201)
    def record(body: dict, request: Request):
        day, amount, card = body.get('date'), body.get('amountKopecks'), body.get('cardId')
        request_key = request.headers.get('Idempotency-Key')
        if request_key is not None and not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', request_key):
            return JSONResponse({'code':'invalid_idempotency_key'}, 422)
        category = normalize_label(body.get('categoryName'))
        raw_merchant = body.get('merchant', '')
        merchant = normalize_label(raw_merchant)
        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            user = account(db, request)
            if not user:
                return JSONResponse({'code':'login_required'}, 401)
            if (not iso_day(day) or day > today().isoformat() or type(amount) is not int or not 0 < amount <= 10**12
                    or not 1 <= len(category) <= 80 or len(merchant) > 120 or not isinstance(raw_merchant, str)
                    or (raw_merchant.strip() and not merchant) or (card is not None and not isinstance(card, str))):
                return JSONResponse({'code':'invalid_purchase'}, 422)
            if request_key is not None:
                payload = json.dumps([day, amount, card, category, merchant], ensure_ascii=False)
                digest = hashlib.sha256(payload.encode()).hexdigest()
                existing = db.execute('''SELECT payload_digest, purchase_id FROM purchase_requests
                    WHERE account_id=? AND request_key=?''', (user[0], request_key)).fetchone()
                if existing:
                    if digest != existing[0]:
                        return JSONResponse({'code':'idempotency_key_conflict'}, 409)
                    return {'id':existing[1]}
            day_value = today().fromisoformat(day)
            names, estimates = estimate_cards(db, request, day_value, category, amount)
            if card is not None and card not in names:
                return JSONResponse({'code':'unknown_card'}, 422)
            used = json.dumps({'id':card, 'name':names[card]}) if card is not None else None
            id_ = secrets.token_hex(16)
            db.execute('INSERT INTO purchases VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                       (id_, user[0], day, category, merchant, amount, used, json.dumps(estimates)))
            if request_key is not None:
                db.execute('INSERT INTO purchase_requests VALUES (?, ?, ?, ?)',
                           (user[0], request_key, digest, id_))
        return {'id':id_}

    @app.get('/api/me/spending')
    def report(request: Request, month: str | None = None):
        current = today().isoformat()[:7]
        month = current if month is None else month
        with connect(db_path) as db:
            user = account(db, request)
            if not user:
                return JSONResponse({'code':'login_required'}, 401)
            if not iso_day(month + '-01') or month > current:
                return JSONResponse({'code':'invalid_month'}, 422)
            records = db.execute('''SELECT p.id, p.day, p.category, p.merchant, p.amount, p.used_card, p.estimates, c.amount
                FROM purchases p LEFT JOIN purchase_cashback c ON c.purchase_id=p.id
                WHERE p.account_id=? AND p.day BETWEEN ? AND ? ORDER BY p.day DESC, p.rowid DESC''',
                (user[0], month + '-01', month + '-31')).fetchall()
        return summarize(month, records)

    @app.put('/api/me/purchases/{purchase_id}/cashback', status_code=204)
    def update_cashback(purchase_id: str, body: dict, request: Request):
        value = body.get('amountKopecks')
        if 'amountKopecks' not in body or (value is not None and (type(value) is not int or not 0 <= value <= 10**12)):
            return JSONResponse({'code':'invalid_cashback'}, 422)
        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            user = account(db, request)
            if not user:
                return JSONResponse({'code':'login_required'}, 401)
            if not db.execute('SELECT 1 FROM purchases WHERE account_id=? AND id=?', (user[0], purchase_id)).fetchone():
                return JSONResponse({'code':'unknown_purchase'}, 404)
            if value is None:
                db.execute('DELETE FROM purchase_cashback WHERE purchase_id=?', (purchase_id,))
            else:
                db.execute('''INSERT INTO purchase_cashback (purchase_id, amount) VALUES (?, ?)
                    ON CONFLICT(purchase_id) DO UPDATE SET amount=excluded.amount''', (purchase_id, value))
        return Response(status_code=204)

    @app.delete('/api/me/purchases/{purchase_id}', status_code=204)
    def remove(purchase_id: str, request: Request):
        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            user = account(db, request)
            if not user:
                return JSONResponse({'code':'login_required'}, 401)
            changed = db.execute('DELETE FROM purchases WHERE account_id=? AND id=?', (user[0], purchase_id))
            if not changed.rowcount:
                return JSONResponse({'code':'unknown_purchase'}, 404)
        return Response(status_code=204)
