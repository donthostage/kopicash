"""Read-only forecast over *confirmed monthly sets*, not a statement or a bank action.

Slots are the total for one card/program; active labels are locked and consume slots.
The selected flag on an offer confirms its inclusion, not activation. Missing selected
is supported for storage that already filtered rows during confirmation. Each manual
entry models a single receipt; manual input replaces, rather than augments, history.
A rule cap is shared by receipts in the simulated month, starting at its full value.
No MCC, issuer-wide cap, shared-account data, legacy/catalog rates or real balance
can be inferred from this schema. Small portfolios and small capped receipt routing
are enumerated exactly. On larger inputs return a feasible scenario, never a guarantee.
"""
import calendar
import itertools
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse

from catalog import connect, wallet_purchase_table


MAX_RECEIPTS = 1000
MAX_ROWS = 128
MAX_RULES = 256
UNKNOWN = 'Часть условий не подтверждена или не распознана: прогноз учитывает только известные правила.'
APPROX = 'Перебор ограничен: показан проверенный вариант, а не гарантированный максимум.'
SCOPE = ('Прогноз только по подтверждённым наборам выбранного месяца, не начисление банка. '
         'Общие лимиты счёта, исключения и траты вне расчёта неизвестны.')


@dataclass(frozen=True)
class Rule:
    card: str
    label: str
    category: str
    rate: int
    minimum: int
    cap: int | None


def parse_rule(card, row):
    if not isinstance(row, dict):
        raise ValueError
    if row.get('selected', True) is not True:
        return None
    label, category, rate, minimum, cap = (row.get(k) for k in
        ('label', 'categoryId', 'rateBps', 'minAmountKopecks', 'limitKopecks'))
    if (row.get('uncertain') or not isinstance(label, str) or not label.strip()
            or not isinstance(category, str) or not category.strip() or type(rate) is not int
            or not 0 <= rate <= 10000 or type(minimum) is not int or minimum < 0
            or 'limitKopecks' not in row or cap is not None and (type(cap) is not int or cap < 0)):
        raise ValueError
    return Rule(card, label, category, rate, minimum, cap)


def simulate(rules, receipts, route_budget):
    """One rule per receipt. Eligible exact rows suppress that card's generic rows."""
    index = defaultdict(lambda: defaultdict(list))
    caps = {}
    for i, rule in enumerate(rules):
        index[rule.card][rule.category].append((i, rule))
        if rule.cap is not None:
            caps[i] = rule.cap
    choices = []
    known = 0
    for category, amount in receipts:
        hits = []
        matched = False
        for by_cat in index.values():
            exact = [(i,r) for i,r in by_cat.get(category, ()) if amount >= r.minimum]
            for i,r in exact or by_cat.get('all', ()):
                if amount >= r.minimum:
                    matched = True
                    value = (amount * r.rate + 5000) // 10000
                    if r.cap is not None:
                        value = min(value, r.cap)
                    if value:
                        hits.append((i, value))
        known += matched
        if hits:
            choices.append(hits)
    # Uncapped alternatives only need their highest value, independent of routing.
    balances = dict(caps)
    baseline = 0
    flexible = []
    for hits in choices:
        free = max((v for i,v in hits if i not in caps), default=0)
        baseline += free
        paid = [(i,v) for i,v in hits if i in caps and v > free]
        if paid:
            flexible.append((free, paid))
    if not flexible:
        return baseline, True, known
    # Greedy feasible solution even when exhaustive routing is too expensive.
    best = baseline
    for free, paid in flexible:
        gain, i = max((min(v,balances[i])-free, i) for i,v in paid)
        if gain > 0:
            best += gain
            balances[i] -= gain + free
    # If each constrained receipt only has a single rule and no other payment
    # alternative, total min(sum of rewards, cap) is exact in any order.
    if all(free == 0 and len(paid) == 1 for free,paid in flexible):
        return best, True, known
    nodes = 1
    for _, paid in flexible:
        nodes *= 1 + len(paid)
        if nodes > route_budget:
            return best, False, known
    balances = dict(caps)
    def visit(pos, total):
        nonlocal best
        if pos == len(flexible):
            best = max(best, total)
            return
        free, paid = flexible[pos]
        visit(pos+1,total)
        for i, v in paid:
            value = min(v,balances[i])
            if value <= free:
                continue
            balances[i] -= value
            visit(pos+1,total+value-free)
            balances[i] += value
    visit(0, baseline)
    return best, True, known


def forecast(rows, receipts, manual):
    warnings = [SCOPE]
    if not manual:
        valid = [(category, amount) for category, amount in receipts
                 if isinstance(category, str) and category.strip() and type(amount) is int and 0 < amount <= 10**12]
        if len(valid) != len(receipts):
            warnings.append('Возвраты и некорректные строки истории исключены: их влияние на начисления неизвестно.')
        receipts = valid
    if manual and receipts:
        warnings.append('Каждая ручная строка считается одним чеком. Для порогов и округления разбивайте месячную сумму на покупки.')
    active, offers, banks, slots = defaultdict(dict), defaultdict(dict), {}, {}
    locked = defaultdict(set)
    for card, bank, mode, count, data in rows:
        banks[card] = bank
        if mode == 'offer':
            slots[card] = count
        raw = json.loads(data)
        if not isinstance(raw, list) or len(raw) > MAX_RULES:
            raise ValueError('Слишком много условий для одного расчёта.')
        for item in raw:
            if mode == 'active' and isinstance(item, dict) and item.get('selected',True) is True:
                locked[card].add(item.get('label') if isinstance(item.get('label'),str) else None)
            try:
                rule = parse_rule(card, item)
            except ValueError:
                if UNKNOWN not in warnings:
                    warnings.append(UNKNOWN)
                continue
            if rule is not None:
                (active if mode == 'active' else offers)[card][rule.label] = rule
    fixed = tuple(r for card in active.values() for r in card.values())
    out = dict(baseKopecks=0, projectedKopecks=0, gainKopecks=0, choices=[], warnings=warnings)
    if not receipts:
        warnings.append('Нет расходов для сравнения. Укажите покупки вручную или выберите другой месяц истории.')
        return out
    if not rows:
        warnings.append('Нет подтверждённых условий за месяц плана.')
    elif len(set(banks.values())) == 1:
        warnings.append('В расчёте условия только одного банка; остальные банки не сравнивались.')
    if any(r.cap is not None for portfolio in (active, offers) for pool in portfolio.values() for r in pool.values()):
        warnings.append('Лимит каждой строки считается месячным и полностью доступным в начале расчёта; реальный остаток неизвестен.')
    categories = {c for c,_ in receipts}
    dimensions = []
    for card, pool in sorted(offers.items()):
        if type(slots[card]) is not int or slots[card] < 0:
            warnings.append(f'Неизвестно число мест для карты {card}; варианты не сравнивались.')
            continue
        options = tuple(r for label,r in sorted(pool.items()) if label not in locked[card]
                        and (r.category == 'all' or r.category in categories))
        k = min(len(options), max(0, slots[card]-len(locked[card])))
        if k:
            dimensions.append((options, k))
    rule_count = len(fixed) + sum(len(opt) for opt,_ in dimensions)
    if rule_count > MAX_RULES:
        raise ValueError('Слишком много условий для одного расчёта.')
    budget = max(1, min(2048, 500000 // max(1,len(receipts)*rule_count)))
    count = 1
    for opts,k in dimensions:
        count *= sum(math.comb(len(opts),n) for n in range(k+1))
        if count > budget:
            break
    route_budget = max(16, 80000 // max(1,min(count,budget)))
    base, exact, coverage = simulate(fixed, receipts, route_budget)
    best, chosen, ties = base, (), False
    def consider(selection):
        nonlocal best, chosen, ties, exact, coverage
        value, complete, known = simulate(fixed+selection, receipts, route_budget)
        exact &= complete
        if value > best or value == best and len(selection) < len(chosen):
            best, chosen, ties, coverage = value, selection, False, known
        elif value == best and selection != chosen and len(selection) == len(chosen):
            ties = True
    if count <= budget:
        pools = [list(itertools.chain.from_iterable(itertools.combinations(opts,n) for n in range(k+1)))
                 for opts,k in dimensions]
        for combo in itertools.product(*pools):
            selection = tuple(itertools.chain.from_iterable(combo))
            if selection:
                consider(selection)
    else:
        # Bounded best marginal additions; never replace the baseline with a worse projection.
        exact = False
        for _ in range(sum(k for _,k in dimensions)):
            previous = chosen
            for opts,k in dimensions:
                if sum(r in previous for r in opts) >= k:
                    continue
                for r in opts:
                    if r not in previous:
                        if budget <= 0:
                            break
                        consider(previous+(r,))
                        budget -= 1
            if previous == chosen or budget <= 0:
                break
    if not exact:
        warnings.append(APPROX)
    if not chosen and dimensions:
        warnings.append('У рассмотренных вариантов нет подтверждённого прироста относительно базы.')
    if ties:
        warnings.append('Есть равноценные варианты среди проверенных; показан один из них.')
    if coverage < len(receipts):
        warnings.append(f'Для {len(receipts)-coverage} из {len(receipts)} чеков нет подходящего известного правила: начисление не прогнозируем.')
    grouped = defaultdict(list)
    for r in chosen:
        grouped[r.card].append(r.label)
    out.update(baseKopecks=base, projectedKopecks=best, gainKopecks=best-base,
               choices=[dict(cardId=c, bankId=banks[c], labels=sorted(labels)) for c,labels in sorted(grouped.items())])
    return out


def valid_month(value):
    return isinstance(value,str) and re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])',value) and value[:4] != '0000'


def mount_planner(app, db_path, require_user):
    @app.post('/api/me/cashback-plan')
    def cashback_plan(body: dict, request: Request):
        session = require_user(request)
        if not session:
            return JSONResponse({'message':'Войдите для расчёта плана.'},401)
        month, source = body.get('month'), body.get('spendingMonth')
        if not valid_month(month) or not valid_month(source):
            return JSONResponse({'message':'Укажите месяц плана и месяц трат в формате ГГГГ-ММ.'},422)
        manual = 'spending' in body
        if manual:
            items = body['spending']
            if not isinstance(items,list) or len(items)>MAX_RECEIPTS or any(
                not isinstance(i,dict) or not isinstance(i.get('categoryId'),str) or not i['categoryId'].strip()
                or len(i['categoryId'])>160 or type(i.get('amountKopecks')) is not int
                or not 0<i['amountKopecks']<=10**12 for i in items):
                return JSONResponse({'message':'Укажите не более 1000 чеков с категорией и положительной суммой в копейках.'},422)
            receipts = [(i['categoryId'],i['amountKopecks']) for i in items]
        with connect(db_path) as db:
            db.execute('BEGIN')
            if not manual:
                last = calendar.monthrange(int(source[:4]), int(source[-2:]))[1]
                receipts = db.execute(f'''SELECT category_id,amount_kopecks FROM {wallet_purchase_table(db)}
                    WHERE session=? AND bought_on BETWEEN ? AND ? ORDER BY bought_on,rowid LIMIT ?''',
                    (session,source+'-01',f'{source}-{last}',MAX_RECEIPTS+1)).fetchall()
            rows = db.execute('''SELECT card_id,bank_id,mode,slots,rules_json FROM cashback_sets
                WHERE session=? AND month=? AND mode IN ('active','offer') ORDER BY card_id,mode LIMIT ?''',
                (session,month,MAX_ROWS+1)).fetchall()
        if len(rows)>MAX_ROWS or len(receipts)>MAX_RECEIPTS:
            return JSONResponse({'message':'Слишком большой набор для одного расчёта. Уточните расходы вручную или уменьшите число наборов.'},422)
        try:
            return forecast(rows,receipts,manual)
        except ValueError as exc:
            return JSONResponse({'message':str(exc)},422)
