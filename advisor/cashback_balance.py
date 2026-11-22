"""Bank snapshots and confirmed journal cashback for the wallet."""

import json

from catalog import wallet_purchase_table


def owns_card(db, session, card):
    return db.execute(
        '''SELECT 1 FROM manual_cards WHERE session=? AND card_id=?
           UNION SELECT 1 FROM saved WHERE session=? AND cardId=?''',
        (session, card, session, card),
    ).fetchone() is not None


def owns_purchase(db, session, purchase_id):
    return 0 < purchase_id < 2**63 and db.execute(
        f'SELECT 1 FROM {wallet_purchase_table(db)} WHERE session=? AND id=?',
        (session, purchase_id),
    ).fetchone() is not None


def journal_cashback(db, session, month, card=None):
    rows = db.execute(f'''SELECT p.id, p.chosen_card, p.bought_on, p.category_id, p.amount_kopecks, a.amount_kopecks
        FROM {wallet_purchase_table(db)} p
        JOIN wallet_actual_cashback a ON a.session=p.session AND a.purchase_id=p.id
        WHERE p.session=? AND p.bought_on LIKE ? AND (? IS NULL OR p.chosen_card=?)
        ORDER BY p.bought_on DESC, p.id DESC''', (session, month + '%', card, card))
    return [dict(purchaseId=id_, cardId=card_id, date=day, categoryId=category,
                 purchaseAmountKopecks=amount, actualCashbackKopecks=actual)
            for id_, card_id, day, category, amount, actual in rows]


def snapshots(db, session, month, card=None):
    rows = db.execute('''SELECT card_id, bank_remaining_kopecks, reconciled_at, included_ids
        FROM wallet_cashback_reconciliations
        WHERE session=? AND month=? AND (? IS NULL OR card_id=?)''', (session, month, card, card))
    return {card_id: (remaining, reconciled_at, set(json.loads(ids)))
            for card_id, remaining, reconciled_at, ids in rows}


def remaining_after_snapshot(bank_remaining, unaccounted):
    return max(0, bank_remaining - unaccounted)


def card_limit_inputs(db, session, month, card):
    return db.execute('''SELECT l.limit_kopecks, u.used_kopecks
        FROM wallet_monthly_limits l LEFT JOIN wallet_monthly_usage u
        ON u.session=l.session AND u.card_id=l.card_id AND u.month=?
        WHERE l.session=? AND l.card_id=?''', (month, session, card)).fetchone() or (None, None)


def save_card_limits(db, session, month, card, limit, used):
    db.execute('INSERT OR REPLACE INTO wallet_monthly_limits VALUES (?, ?, ?)', (session, card, limit))
    db.execute('INSERT OR REPLACE INTO wallet_monthly_usage VALUES (?, ?, ?, ?)', (session, card, month, used))


def category_caps(db, session, month, card=None):
    return {(card_id, category): (cap, used) for card_id, category, cap, used in db.execute('''
        SELECT l.card_id, l.category_id, l.limit_kopecks, u.used_kopecks
        FROM wallet_category_limits l LEFT JOIN wallet_category_usage u
        ON u.session=l.session AND u.card_id=l.card_id AND u.category_id=l.category_id AND u.month=?
        WHERE l.session=? AND (? IS NULL OR l.card_id=?)''', (month, session, card, card))}


def personal_caps(db, session, month):
    caps = {card: (cap, used) for card, cap, used in db.execute('''
        SELECT l.card_id, l.limit_kopecks, u.used_kopecks FROM wallet_monthly_limits l
        LEFT JOIN wallet_monthly_usage u ON u.session=l.session AND u.card_id=l.card_id AND u.month=?
        WHERE l.session=?''', (month, session))}
    bank = snapshots(db, session, month)
    if bank:
        unaccounted = dict.fromkeys(bank, 0)
        for entry in journal_cashback(db, session, month):
            card = entry['cardId']
            if card in bank and entry['purchaseId'] not in bank[card][2]:
                unaccounted[card] += entry['actualCashbackKopecks']
        for card, (remaining, _, _) in bank.items():
            # Both consumers represent a known remaining balance as cap minus known usage.
            caps[card] = (remaining_after_snapshot(remaining, unaccounted[card]), 0)
    return caps


def reconciliation_view(db, session, month, card):
    remaining, at, included = snapshots(db, session, month, card).get(card, (None, None, set()))
    entries = journal_cashback(db, session, month, card)
    for entry in entries:
        entry['includedInBankBalance'] = entry['purchaseId'] in included
    deduction = None if remaining is None else sum(
        entry['actualCashbackKopecks'] for entry in entries if not entry['includedInBankBalance'])
    return dict(month=month, cardId=card, reconciledAt=at, bankRemainingKopecks=remaining,
                deductedKopecks=deduction, accruals=entries,
                remainingKopecks=None if remaining is None else remaining_after_snapshot(remaining, deduction))
