"""Monthly private cashback rules shared by wallet and planner (no images stored)."""
import hashlib
import json
import re
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation

from catalog import CATEGORIES, bank_names

MAX_AMOUNT = 10**12
MAX_ROWS = 128
_TILE_SUBTITLE = re.compile(
    r'^(для молод(ё|е)жи|дополняет\b.+|подходит\b.+|только для\b.+|в рамках\b.+)$',
    re.I,
)
_TILE_SUBTITLE_PREFIX = re.compile(r'^(Для|Дополняет|Подходит|Только|В рамках)\b', re.I)


class Invalid(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def text(value, limit=80):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit or not value.strip().isprintable():
        raise Invalid('Проверьте название категории или идентификатор')
    return value.strip()


def month_ok(month):
    return isinstance(month, str) and re.fullmatch(r'(?!0000)[0-9]{4}-(0[1-9]|1[0-2])', month) and month < '9999-12'


def period(month):
    year, number = map(int, month.split('-'))
    return month + '-01', date(year + (number == 12), number % 12 + 1, 1).isoformat()


def category(label, proposed=None):
    # Only exact dictionary names/IDs (and the explicit all-purchases wording)
    # map to public categories. Taxi is not transport; cinema is not theatre.
    key = label.casefold()
    for cid, name in CATEGORIES.items():
        if key in (cid, name.casefold()):
            return cid
    if key in ('на все покупки', 'на всё', 'все покупки'):
        return 'all'
    return label if not proposed or proposed in CATEGORIES else proposed


def scaled(value, percent=False):
    if value is None:
        return None
    raw = str(value).strip().replace('\u00a0', '').replace(' ', '').replace(',', '.')
    if percent:
        raw = raw.removesuffix('%')
    if not re.fullmatch(r'\d{1,13}(?:\.\d{1,2})?', raw):
        raise ValueError('invalid number')
    return int(Decimal(raw) * 100)


def omit_tile_subtitle_lines(rules):
    """Drop second-line hints OCR often splits off the same bank tile (e.g. «Для молодёжи»)."""
    kept = []
    for rule in rules:
        label = (rule.get('label') or '').strip()
        if rule.get('rateBps') is None and _TILE_SUBTITLE.match(label):
            continue
        if (rule.get('rateBps') is None and len(label) <= 48
                and _TILE_SUBTITLE_PREFIX.match(label)):
            continue
        kept.append(rule)
    if not kept:
        raise ValueError('no rules')
    return kept


def parse_draft(content):
    if not isinstance(content, str):
        raise ValueError('empty')
    start = min((p for p in (content.find('{'), content.find('[')) if p >= 0), default=-1)
    if start < 0:
        raise ValueError('empty')
    data = json.JSONDecoder().raw_decode(content[start:])[0]
    items = data.get('rules') if isinstance(data, dict) else data
    if not isinstance(items, list) or len(items) > MAX_ROWS:
        raise ValueError('shape')
    rules = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            label = text(item.get('label') or item.get('categoryId'))
        except Invalid:
            continue
        selection = item.get('selected')
        selection = selection if type(selection) is bool else None
        uncertain = item.get('uncertain', False) is not False or selection is None
        def number(field, printed, maximum, missing):
            nonlocal uncertain
            try:
                if field in item:
                    n = item[field]
                elif item.get(printed) is not None:
                    n = scaled(item[printed], field == 'rateBps')
                else:
                    n = missing
                if n is not None and (type(n) is not int or not 0 <= n <= maximum):
                    raise ValueError
                return n
            except (ValueError, InvalidOperation):
                uncertain = True
                return None
        rate = number('rateBps', 'ratePercent', 10000, None)
        cap = number('limitKopecks', 'limitRub', MAX_AMOUNT, None)
        minimum = number('minAmountKopecks', 'minAmountRub', MAX_AMOUNT, 1)
        rules.append(dict(label=label, categoryId=category(label), rateBps=rate,
                          limitKopecks=cap, minAmountKopecks=minimum, selected=selection,
                          uncertain=uncertain or rate is None or minimum is None))
    if not rules:
        raise ValueError('no rules')
    rules = omit_tile_subtitle_lines(rules)
    month = data.get('month') if isinstance(data, dict) else None
    return {'rules': rules, **({'month': month} if month_ok(month) else {})}


def rule_dates(fields, *, existing=None, month=None):
    keys = ('validFrom', 'validThrough')
    existing = existing or {}
    bounds = {key: fields.get(key, existing.get(key)) for key in keys}
    for value in bounds.values():
        if value is None:
            continue
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError
        except (TypeError, ValueError):
            raise Invalid('Проверьте даты действия категории') from None
        if month is not None and not value.startswith(month + '-'):
            raise Invalid('Укажите даты в пределах месяца действия категории')
    start, finish = bounds.values()
    if start is not None and finish is not None and start > finish:
        raise Invalid('Дата окончания должна быть не раньше даты начала')
    return {key: bounds[key] for key in keys if key in fields}


def clean_rules(items, month=None):
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ROWS:
        raise Invalid('Добавьте хотя бы одну категорию')
    cleaned = {}
    for row in items:
        if not isinstance(row, dict) or not {'selected','uncertain','label','categoryId','rateBps','limitKopecks','minAmountKopecks'} <= row.keys():
            raise Invalid('Заполните условия категории')
        selected = row['selected']
        if selected is not None and type(selected) is not bool:
            raise Invalid('Проверьте выбор категории')
        if selected is not True:
            continue
        label = text(row['label'])
        cid = category(label, text(row['categoryId']))
        rate, cap, minimum = row['rateBps'], row['limitKopecks'], row['minAmountKopecks']
        if (type(rate) is not int or not 0 <= rate <= 10000 or type(minimum) is not int or not 0 <= minimum <= MAX_AMOUNT
                or cap is not None and (type(cap) is not int or not 0 <= cap <= MAX_AMOUNT)
                or type(row['uncertain']) is not bool or label in cleaned):
            raise Invalid('Проверьте ставку, лимит и минимальную сумму выбранной категории')
        cleaned[label] = dict(label=label, categoryId=cid, rateBps=rate, limitKopecks=cap,
                              minAmountKopecks=minimum, selected=True, uncertain=row['uncertain'],
                              **rule_dates(row, month=month))
    if not cleaned:
        raise Invalid('Отметьте категории для сохранения')
    return list(cleaned.values())


def validate_bank(bank):
    if not isinstance(bank, str) or bank not in bank_names():
        raise Invalid('Выберите банк из списка')


def target_card(db, session, bank, card):
    validate_bank(bank)
    name = bank_names()[bank]
    if card is not None:
        card = text(card)
        owned = db.execute('SELECT name FROM manual_cards WHERE session=? AND card_id=?', (session, card)).fetchone()
        if not owned:
            raise Invalid('Карта не найдена', 404)
        other_bank = db.execute('SELECT 1 FROM cashback_sets WHERE session=? AND card_id=? AND bank_id<>? LIMIT 1',
                                (session, card, bank)).fetchone()
        if other_bank or (owned[0] in bank_names().values() and owned[0] != name):
            raise Invalid('Карта другого банка', 409)
        return card, owned[0]
    options = db.execute('''SELECT m.card_id, m.name FROM manual_cards m WHERE m.session=? AND
        (m.name=? OR EXISTS (SELECT 1 FROM cashback_sets s WHERE s.session=m.session AND s.card_id=m.card_id AND s.bank_id=?))
        LIMIT 2''', (session, name, bank)).fetchall()
    if len(options) > 1:
        raise Invalid('У этого банка несколько карт. Выберите нужную карту', 409)
    return options[0] if options else (None, name)


def previous(db, session, op, key, data):
    key = text(key, 128)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    found = db.execute('SELECT digest,response_json FROM wallet_requests WHERE session=? AND operation=? AND request_id=?',
                       (session, op, key)).fetchone()
    if found and digest != found[0]:
        raise Invalid('Запрос с этим идентификатором уже выполнен с другими данными',409)
    return digest, json.loads(found[1]) if found else None


def remember(db, session, op, key, digest, response):
    db.execute('INSERT INTO wallet_requests VALUES(?,?,?,?,?)',(session,op,key.strip(),digest,json.dumps(response)))


def confirm(db, session, body, today):
    bank, requested, month, mode, slots, key = (body.get(k) for k in ('bankId','cardId','month','mode','slots','requestId'))
    validate_bank(bank)
    if not month_ok(month) or mode not in ('active','offer'):
        raise Invalid('Проверьте месяц и вид условий')
    if ('slots' not in body or slots is not None and (type(slots) is not int or not 0 <= slots <= MAX_ROWS)):
        raise Invalid('Проверьте число доступных мест')
    rules = clean_rules(body.get('rules'), month if mode == 'active' else None)
    digest, replay = previous(db, session, 'confirm',key, [bank,requested,month,mode,slots,rules])
    if replay:
        return replay
    card, name = target_card(db,session,bank,requested)
    if card is None:
        card = 'manual-' + secrets.token_hex(12)
        db.execute('INSERT INTO manual_cards(session,card_id,name,updated_on,rules_json) VALUES(?,?,?,?,?)',
                   (session,card,name,today,'[]'))
    old = db.execute('SELECT rules_json FROM cashback_sets WHERE session=? AND card_id=? AND month=? AND mode=?',
                     (session,card,month,mode)).fetchone()
    merged = {r['label']:r for r in json.loads(old[0])} if old else {}
    merged.update({r['label']: {**r, 'updatedOn': today} for r in rules})
    if mode == 'active' and slots is not None and len(merged) > slots:
        raise Invalid('Подключённых категорий больше, чем разрешает банк')
    if len(merged) > MAX_ROWS:
        raise Invalid('Слишком много категорий для одной карты')
    merged = list(merged.values())
    db.execute('''INSERT INTO cashback_sets VALUES(?,?,?,?,?,?,?) ON CONFLICT(session,card_id,month,mode)
               DO UPDATE SET slots=excluded.slots, rules_json=excluded.rules_json''',
               (session,card,bank,month,mode,slots,json.dumps(merged,ensure_ascii=False)))
    result = dict(cardId=card,bankId=bank,name=name,month=month,mode=mode,slots=slots,rules=merged)
    remember(db,session,'confirm',key,digest,result)
    return result
