import argparse
import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from functools import lru_cache
from pathlib import Path

CATEGORIES = {
    'supermarkets': 'Супермаркеты', 'cafe': 'Кафе', 'fuel': 'АЗС',
    'pharmacy': 'Аптеки', 'transport': 'Транспорт', 'clothing': 'Одежда',
    'electronics': 'Электроника', 'marketplace': 'Маркетплейсы',
    'entertainment': 'Развлечения', 'utilities': 'Связь и ЖКХ',
    'travel': 'Путешествия', 'all': 'Все покупки',
}
BANKS = (
    ('sber', 'СберБанк', '#0C8C50', '#FFFFFF', ''),
    ('vtb', 'ВТБ', '#0050D8', '#FFFFFF', ''),
    ('gazprombank', 'Газпромбанк', '#122C68', '#FFFFFF', ''),
    ('alfabank', 'Альфа-Банк', '#E52030', '#FFFFFF', ''),
    ('rshb', 'Россельхозбанк', '#225735', '#FFFFFF', ''),
    ('domrf', 'Банк ДОМ.РФ', '#24282C', '#FFFFFF', ''),
    ('tbank', 'Т-Банк', '#191919', '#FFFFFF', '#FFDD2D'),
    ('mkb', 'Московский Кредитный Банк (МКБ)', '#8B2142', '#FFFFFF', ''),
    ('sovcombank', 'Совкомбанк', '#007CB5', '#FFFFFF', ''),
    ('raiffeisen', 'Райффайзенбанк', '#FEE600', '#161616', ''),
    ('novikom', 'Новиком', '#40377C', '#FFFFFF', ''),
    ('rossiya', 'Банк «Россия»', '#84252E', '#FFFFFF', ''),
    ('rencap', 'РенКап Банк', '#642B65', '#FFFFFF', ''),
    ('bspb', 'Банк «Санкт-Петербург»', '#BF2350', '#FFFFFF', ''),
    ('akbars', 'Ак Барс Банк', '#007D6A', '#FFFFFF', ''),
    ('ozon', 'Ozon Банк', '#005BFF', '#FFFFFF', ''),
    ('otp', 'ОТП Банк', '#A8D500', '#161616', ''),
    ('uralsib', 'Уралсиб', '#2846A0', '#FFFFFF', ''),
    ('mts', 'МТС Банк', '#E30613', '#FFFFFF', ''),
    ('unicredit', 'ЮниКредит Банк', '#D8DCE3', '#161616', ''),
)

_BANK_LOGO_DIR = Path(__file__).parent / 'static' / 'banks'
REGISTRY_LOGO_BY_NUMBER = {
    '101': 'bcs',
    '1927': 'modulbank',
    '3251': 'psb',
    '3354': 'rencap',
    '3027': 'yandex',
}


def bank_logo_url(logo_id):
    if not logo_id:
        return None
    for suffix in ('.png', '.svg', '.webp'):
        if (_BANK_LOGO_DIR / f'{logo_id}{suffix}').is_file():
            return f'/static/banks/{logo_id}{suffix}'
    return None


@lru_cache(maxsize=1)
def registry_banks():
    return json.loads(Path(__file__).with_name('banks_ru.json').read_text(encoding='utf-8'))['banks']


BRANDED_REGISTRATION_NUMBERS = {
    '1481', '1000', '354', '1326', '3349', '2312', '2673', '1978', '963', '3292',
    '2546', '328', '2557', '436', '2590', '3542', '2766', '2275', '2268', '1',
}


def bank_names():
    return {bank['id']: bank['name'] for bank in bank_public()}


def bank_public():
    featured = []
    for bank in BANKS:
        row = {'id': bank[0], 'name': bank[1], 'color': bank[2], 'ink': bank[3], 'accent': bank[4]}
        logo = bank_logo_url(bank[0])
        if logo:
            row['logo'] = logo
        featured.append(row)
    registry = []
    for bank in registry_banks():
        if bank['registrationNumber'] in BRANDED_REGISTRATION_NUMBERS:
            continue
        row = {'id': 'cbr-' + bank['registrationNumber'], 'name': bank['name'],
               'registrationNumber': bank['registrationNumber']}
        logo_id = REGISTRY_LOGO_BY_NUMBER.get(bank['registrationNumber'])
        logo = bank_logo_url(logo_id)
        if logo:
            row['logo'] = logo
        registry.append(row)
    return featured + registry
SEED = [dict(cardId=c, categoryId=k, rateBps=r, limitKopecks=l, minAmountKopecks=m,
             validFrom='2026-11-01', validUntilExclusive='2027-11-01', updatedOn='2026-11-01')
        for c,k,r,l,m in [('A','supermarkets',1000,10000,1), ('B','supermarkets',600,30000,1),
                          ('C','supermarkets',400,20000,1), ('D','supermarkets',200,10000,1),
                          ('D','cafe',800,30000,10000)]]
FIELDS = tuple(SEED[0])


@contextmanager
def connect(path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


def wallet_purchase_table(db):
    # Keep the classic journal and its foreign keys intact on staging and rollback.
    columns = {row[1] for row in db.execute('PRAGMA table_info(purchases)')}
    return 'wallet_purchases' if 'account_id' in columns else 'purchases'


def setup(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS rules (
          cardId TEXT, categoryId TEXT, rateBps INTEGER, limitKopecks INTEGER,
          minAmountKopecks INTEGER, validFrom TEXT, validUntilExclusive TEXT, updatedOn TEXT,
          PRIMARY KEY (cardId, categoryId, validFrom)
        );
        CREATE TABLE IF NOT EXISTS saved (
          session TEXT, cardId TEXT, PRIMARY KEY(session, cardId)
        );
        CREATE TABLE IF NOT EXISTS users (
          session TEXT PRIMARY KEY, login TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL, created_on TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS manual_cards (
          session TEXT NOT NULL, card_id TEXT NOT NULL, name TEXT NOT NULL,
          updated_on TEXT NOT NULL, rules_json TEXT NOT NULL,
          PRIMARY KEY(session, card_id)
        );
        CREATE TABLE IF NOT EXISTS cashback_sets (
          session TEXT NOT NULL, card_id TEXT NOT NULL, bank_id TEXT NOT NULL,
          month TEXT NOT NULL, mode TEXT NOT NULL, slots INTEGER, rules_json TEXT NOT NULL,
          PRIMARY KEY(session, card_id, month, mode)
        );
        CREATE TABLE IF NOT EXISTS wallet_requests (
          session TEXT NOT NULL, operation TEXT NOT NULL, request_id TEXT NOT NULL,
          digest TEXT NOT NULL, response_json TEXT NOT NULL,
          PRIMARY KEY(session, operation, request_id)
        );
        CREATE TABLE IF NOT EXISTS usual_card (
          session TEXT PRIMARY KEY, card_id TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS wallet_monthly_limits (
          session TEXT NOT NULL, card_id TEXT NOT NULL, limit_kopecks INTEGER,
          PRIMARY KEY(session, card_id)
        );
        CREATE TABLE IF NOT EXISTS wallet_monthly_usage (
          session TEXT NOT NULL, card_id TEXT NOT NULL, month TEXT NOT NULL, used_kopecks INTEGER,
          PRIMARY KEY(session, card_id, month)
        );
        CREATE TABLE IF NOT EXISTS wallet_category_limits (
          session TEXT NOT NULL, card_id TEXT NOT NULL, category_id TEXT NOT NULL, limit_kopecks INTEGER,
          PRIMARY KEY(session, card_id, category_id)
        );
        CREATE TABLE IF NOT EXISTS wallet_category_usage (
          session TEXT NOT NULL, card_id TEXT NOT NULL, category_id TEXT NOT NULL, month TEXT NOT NULL, used_kopecks INTEGER,
          PRIMARY KEY(session, card_id, category_id, month)
        );
        CREATE TABLE IF NOT EXISTS purchase_cashback (
          purchase_id INTEGER PRIMARY KEY,
          amount INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS wallet_actual_cashback (
          session TEXT NOT NULL, purchase_id INTEGER NOT NULL, amount_kopecks INTEGER NOT NULL,
          PRIMARY KEY(session, purchase_id)
        );
        CREATE TABLE IF NOT EXISTS wallet_cashback_reconciliations (
          session TEXT NOT NULL, card_id TEXT NOT NULL, month TEXT NOT NULL,
          bank_remaining_kopecks INTEGER NOT NULL, reconciled_at TEXT NOT NULL, included_ids TEXT NOT NULL,
          PRIMARY KEY(session, card_id, month)
        );
    ''')
    db.execute(f'''
        CREATE TABLE IF NOT EXISTS {wallet_purchase_table(db)} (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session TEXT NOT NULL, bought_on TEXT NOT NULL, category_id TEXT NOT NULL,
          amount_kopecks INTEGER NOT NULL,
          recommended_card TEXT NOT NULL, recommended_name TEXT NOT NULL, recommended_kopecks INTEGER NOT NULL,
          chosen_card TEXT NOT NULL, chosen_name TEXT NOT NULL, chosen_kopecks INTEGER NOT NULL,
          usual_kopecks INTEGER, catalog_version TEXT NOT NULL
        );
    ''')


    columns = {row[1] for row in db.execute('PRAGMA table_info(users)')}
    if 'password_hash' not in columns:
        # Old sessions and their wallet rows must survive an upgrade. An empty
        # hash cannot authenticate via password and does not invent credentials.
        db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''")
    if 'login' not in columns:
        db.execute('ALTER TABLE users ADD COLUMN login TEXT')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS users_login ON users(login)')
    if 'created_on' not in columns:
        db.execute("ALTER TABLE users ADD COLUMN created_on TEXT NOT NULL DEFAULT ''")
    db.execute('''CREATE TABLE IF NOT EXISTS catalog_cards (
        id TEXT PRIMARY KEY, bank_name TEXT NOT NULL, name TEXT NOT NULL)''')


def rows(db):
    return [dict(zip(FIELDS, row)) for row in db.execute('SELECT * FROM rules ORDER BY cardId, categoryId, validFrom')]


def apply_rules(db, items):
    seen, names = set(), {}
    for rule in items:
        if not isinstance(rule, dict) or set(rule) - {'bankName', 'cardName'} != set(FIELDS):
            raise ValueError('Неверные поля условия')
        c, k, r, l, m, start, end, updated = (rule[f] for f in FIELDS)
        if (not isinstance(c, str) or not c.isascii() or not c.isalnum() or len(c) > 32
                or not isinstance(k, str) or k not in CATEGORIES
                or any(type(n) is not int for n in (r, m)) or not (0 <= r <= 10000 and 1 <= m <= 10**12)
                or (l is not None and (type(l) is not int or not 0 <= l <= 10**12))):
            raise ValueError('Неверные значения условия')
        if 'bankName' in rule or 'cardName' in rule:
            labels = rule.get('bankName'), rule.get('cardName')
            if any(not isinstance(label, str) or not 1 <= len(label.strip()) <= 100 for label in labels):
                raise ValueError('Укажите банк и название карты')
            labels = tuple(label.strip() for label in labels)
            if names.setdefault(c, labels) != labels:
                raise ValueError(f'Разные названия для карты {c}')
        for d in (start, end, updated):
            if not isinstance(d, str) or date.fromisoformat(d).isoformat() != d:
                raise ValueError('Ожидается дата YYYY-MM-DD')
        if start >= end or (c, k, start) in seen:
            raise ValueError('Пустой период или повтор правила в пакете')
        seen.add((c, k, start))
        db.execute('INSERT OR REPLACE INTO rules VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (c,k,r,l,m,start,end,updated))
    previous = None
    for rule in rows(db):
        key = rule['cardId'], rule['categoryId']
        if previous and previous[0] == key and rule['validFrom'] < previous[1]:
            raise ValueError(f'Пересекающиеся периоды: {key}')
        previous = key, rule['validUntilExclusive']
    db.executemany('INSERT OR REPLACE INTO catalog_cards VALUES (?, ?, ?)',
                   ((card, *labels) for card, labels in names.items()))


def import_catalog(path, items):
    with connect(path) as db:
        setup(db)
        db.execute('BEGIN IMMEDIATE')
        apply_rules(db, items)


def initialize(path):
    with connect(path) as db:
        setup(db)
        db.execute('BEGIN IMMEDIATE')
        db.execute(f'''INSERT OR IGNORE INTO wallet_actual_cashback
            SELECT p.session, c.purchase_id, c.amount
            FROM purchase_cashback c JOIN {wallet_purchase_table(db)} p ON p.id = c.purchase_id''')
        if not db.execute('SELECT 1 FROM rules LIMIT 1').fetchone():
            apply_rules(db, SEED)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Импорт учебных условий (JSON-массив правил)')
    parser.add_argument('file', type=Path)
    parser.add_argument('--db', type=Path, default=Path('advisor.sqlite3'))
    args = parser.parse_args()
    try:
        items = json.loads(args.file.read_text(encoding='utf-8'))
        if not isinstance(items, list) or not items:
            raise ValueError('Нужен непустой JSON-массив')
        import_catalog(args.db, items)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f'Импорт не выполнен: {exc}\n')
    print(f'Импортировано правил: {len(items)}')
