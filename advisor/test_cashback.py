import asyncio
import base64
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import httpx

from advisor import create_app, decode_image, parse_rules
from catalog import connect, initialize
from set_advisor_key import save_key


class API:
    def __init__(self, app):
        self.loop = asyncio.new_event_loop()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')
        self.loop.run_until_complete(self.client.__aenter__())

    def _request(self, method, path, body, headers=None):
        return self.loop.run_until_complete(self.client.request(method, path, json=body, headers=headers))

    def get(self, path):
        return self._request('GET', path, None)

    def post(self, path, json=None, headers=None):
        return self._request('POST', path, json, headers)

    def put(self, path, json=None, headers=None):
        return self._request('PUT', path, json, headers)

    def close(self):
        self.loop.run_until_complete(self.client.__aexit__(None, None, None))
        self.loop.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

MONTH = '2026-11'
IMAGE = 'data:image/jpeg;base64,' + base64.b64encode(b'\xff\xd8\xff' + b'x' * 40).decode()


def rule(label='Такси', cid='Такси', rate=500, **extra):
    return dict(dict(label=label, categoryId=cid, rateBps=rate, limitKopecks=None,
                     minAmountKopecks=1, selected=True, uncertain=False), **extra)


class Cashback(unittest.TestCase):
    def setUp(self):
        clock = self.enterContext(patch('advisor.datetime'))
        clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
        self.path = Path(self.enterContext(tempfile.TemporaryDirectory())) / 'test.db'
        initialize(self.path)
        self.app = create_app(self.path)
        self.client = API(self.app)
        self.addCleanup(self.client.close)
        self.login(self.client, 'owner')

    def login(self, client, login):
        self.assertEqual(client.post('/api/auth/register', json={'login': login, 'password': 'demo1234'}).status_code, 201)

    def confirm(self, key='first', rules=None, **fields):
        body = dict(bankId='sber', month=MONTH, mode='active', slots=3, requestId=key,
                    rules=[rule()] if rules is None else rules)
        return self.client.post('/api/me/cashback-confirm', json={**body, **fields})

    def test_draft_strips_second_line_tile_hints(self):
        model = {'rules': [
            {'label': 'За все покупки', 'ratePercent': 2, 'selected': True},
            {'label': 'Вкусно — и точка', 'ratePercent': 15, 'selected': True},
            {'label': 'Для молодёжи', 'selected': True},
            {'label': 'Альфа-Тревел', 'ratePercent': 3, 'selected': True},
            {'label': 'Дополняет сервисный', 'selected': True},
        ]}
        parsed = parse_rules(json.dumps(model))
        self.assertEqual(len(parsed), 3)
        self.assertEqual({r['label'] for r in parsed},
                         {'За все покупки', 'Вкусно — и точка', 'Альфа-Тревел'})

    def test_draft_never_writes_and_keeps_distinct_labels(self):
        model = {'month': MONTH, 'rules': [dict(label=name, categoryId='transport', ratePercent=rate, selected=sel)
                                         for name, rate, sel in [('Такси', 5, True), ('Транспорт', 3, False), ('Метро', 4, None)]]}
        parsed = parse_rules(json.dumps(model))
        self.assertEqual([r['categoryId'] for r in parsed], ['Такси', 'transport', 'Метро'])
        self.assertEqual([r['selected'] for r in parsed], [True, False, None])
        secret_file = self.path.with_name('.advisor-api-key')
        save_key(secret_file, 'test-key', raw=True)
        with patch.dict('os.environ', {'ADVISOR_API_KEY_FILE': str(secret_file)}), patch('advisor.httpx.post') as vision:
            vision.return_value.json.return_value = {'choices': [{'message': {'content': json.dumps(model)}}]}
            resp = self.client.post('/api/me/cashback-screenshot', json={'bankId': 'sber', 'image': IMAGE})
        args, kwargs = vision.call_args
        self.assertEqual(args[0], 'https://api.aitunnel.ru/v1/chat/completions')
        self.assertEqual(kwargs['headers'], {'Authorization': 'Bearer test-key'})
        self.assertEqual(kwargs['json']['messages'][0]['content'][1]['image_url']['url'], IMAGE)
        self.assertEqual(resp.json(), {'rules': parsed, 'month': MONTH})
        self.assertEqual(self.client.get('/api/me/manual-cards').json(), [])
        with self.assertRaises(ValueError):
            decode_image('data:text/plain;base64,YQ==')

    def test_merge_replay_and_rollback(self):
        first = self.confirm()
        self.assertIn(first.status_code, (200, 201), first.text)
        card = first.json()['cardId']
        second = self.confirm('two', [rule('Метро', 'Метро', 800), rule('Кино', 'Кино', selected=False)], cardId=card)
        self.assertIn(second.status_code, (200, 201), second.text)
        self.assertEqual(self.confirm().json(), first.json())
        self.assertEqual(self.confirm(rules=[rule(rate=100)]).status_code, 409)
        self.assertEqual(self.confirm('bad', [rule('Новая', 'Новая'), rule(rate=-1)], cardId=card).status_code, 422)
        with connect(self.path) as db:
            stored = db.execute('SELECT rules_json FROM cashback_sets').fetchall()
            self.assertEqual(len(stored), 1)
            self.assertEqual([r['label'] for r in json.loads(stored[0][0])], ['Такси', 'Метро'])

    def test_rules_current_period_exact_then_fallback_legacy_and_privacy(self):
        created = self.client.post('/api/me/manual-cards', json={'name': 'СберБанк', 'rules':[{'categoryId':'fuel','rateBps':50}]}).json()
        card = created['cardId']
        active = [rule(minAmountKopecks=10000), rule('Все покупки','all',1000)]
        self.assertIn(self.confirm(rules=active, cardId=card).status_code, (200,201))
        self.confirm('future', [rule('Февраль', 'Февраль')], month='2027-02', cardId=card)
        self.confirm('offer', [rule('Опция', 'Опция')], mode='offer', cardId=card)
        def rank(amount, cid):
            return self.client.post('/api/recommendations',json=dict(scope='mine',amountKopecks=amount,categoryId=cid)).json()['allMatches']
        self.assertEqual([r['cashbackKopecks'] for r in rank(10000, 'Такси')], [500])
        self.assertEqual([r['cashbackKopecks'] for r in rank(5000, 'Такси')], [500])
        self.assertEqual([r['cashbackKopecks'] for r in rank(10000, 'fuel')], [50])
        visible = self.client.get('/api/meta').json()['categories']
        self.assertIn('Такси',visible); self.assertNotIn('Опция',visible); self.assertNotIn('Февраль',visible)
        self.assertEqual({r['categoryId'] for r in self.client.get('/api/me/manual-cards').json()[0]['rules']},{'fuel','Такси','all'})
        with API(self.app) as other:
            self.login(other, 'stranger')
            self.assertNotIn('Такси', other.get('/api/meta').json()['categories'])
            with patch('advisor.read_cashback') as model:
                bad = other.post('/api/me/cashback-screenshot',json=dict(bankId='sber',cardId=card,image=IMAGE))
                self.assertEqual(bad.status_code,404); model.assert_not_called()
            self.assertEqual(other.post('/api/me/cashback-confirm',json=dict(bankId='sber',cardId=card,mode='active',month=MONTH,slots=1,requestId='x',rules=[rule()])).status_code,404)
        payload=dict(chosenCardId=card,categoryId='Такси',amountKopecks=10000,requestId='purchase-record-12345')
        for _ in range(2):
            self.assertEqual(self.client.post('/api/me/purchases',json=payload).status_code,201)
        self.assertEqual(self.client.get('/api/me/stats').json()['count'],1)

    def test_rejects_invalid_header_idempotency_key(self):
        response = self.client.post('/api/me/purchases', headers={'Idempotency-Key': 'short'}, json={
            'chosenCardId': 'missing', 'categoryId': 'Такси', 'amountKopecks': 10000,
        })
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['code'], 'invalid_idempotency_key')

    def test_purchase_rejects_card_below_category_threshold(self):
        card = self.client.post('/api/me/manual-cards', json={
            'name': 'Пороговая карта', 'rules': [{'categoryId': 'cafe', 'rateBps': 800, 'minAmountKopecks': 10000}],
        }).json()['cardId']
        response = self.client.post('/api/me/purchases', json={
            'chosenCardId': card, 'categoryId': 'cafe', 'amountKopecks': 9999,
        })
        self.assertEqual(response.status_code, 422)

    def test_usual_card_must_belong_to_current_session_and_can_be_cleared(self):
        response = self.client.put('/api/me/usual-card', json={'cardId': 'missing'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.put('/api/me/usual-card', json={'cardId': ''}).status_code, 204)

    def test_purchase_replay_uses_header_or_legacy_body_and_is_private(self):
        self.client.put('/api/me/cards/A')
        base = dict(chosenCardId='A', categoryId='supermarkets', amountKopecks=10000)
        with API(self.app) as other:
            self.login(other, 'other'); other.put('/api/me/cards/A')
            for fields, headers in [({'requestId': 'short'}, {}), ({'requestId': None}, {'Idempotency-Key': 'header-key-123456'})]:
                for client in [self.client, other]:
                    for _ in range(2):
                        response = client.post('/api/me/purchases', json={**base, **fields}, headers=headers)
                        self.assertEqual(response.status_code, 201, response.text)
                    self.assertEqual(client.post('/api/me/purchases', json={**base, **fields, 'amountKopecks': 20000}, headers=headers).status_code, 409)
            self.assertEqual(other.get('/api/me/stats').json()['count'], 2)
        self.assertEqual(self.client.get('/api/me/stats').json()['count'], 2)
        for invalid in [[], 7, '']:
            self.assertEqual(self.client.post('/api/me/purchases', json={**base, 'requestId': invalid}).status_code, 422)

    def test_unknown_category_cannot_use_all_purchases(self):
        card = self.confirm(rules=[rule('Все покупки', 'all')]).json()['cardId']
        bad = self.client.post('/api/me/purchases', json=dict(chosenCardId=card, categoryId='Несуществующая', amountKopecks=1000))
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(self.client.get('/api/me/stats').json()['count'], 0)

    def test_usual_cleanup_and_logout(self):
        self.client.put('/api/me/cards/A')
        manual = self.confirm().json()['cardId']
        for path, card in [('cards', 'A'), ('manual-cards', manual)]:
            self.assertEqual(self.client.put('/api/me/usual-card', json={'cardId': card}).status_code, 204)
            self.assertEqual(self.client._request('DELETE', f'/api/me/{path}/{card}', None).status_code, 204)
            self.assertIsNone(self.client.get('/api/me/stats').json()['usualCardId'])
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 204)
        self.assertFalse(self.client.get('/api/auth/me').json()['authenticated'])
        self.assertEqual(self.client.get('/api/me/stats').status_code, 401)

    def test_auth_guest(self):
        guest = API(self.app)
        self.addCleanup(guest.close)
        created = guest.post('/api/auth/guest')
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertTrue(body.get('guest'))
        self.assertTrue(body.get('login', '').startswith('g'))
        self.assertTrue(guest.get('/api/auth/me').json()['authenticated'])

    def test_logout_rotates_cookie_without_losing_wallet(self):
        password = 'pilot-test-pass'
        with API(self.app) as wallet, API(self.app) as old_session:
            self.assertEqual(wallet.post('/api/auth/register', json={'login': 'persist_wallet', 'password': password}).status_code, 201)
            self.assertEqual(wallet.put('/api/me/cards/A').status_code, 204)
            purchase = wallet.post('/api/me/purchases', json={
                'categoryId': 'supermarkets', 'amountKopecks': 250_000, 'chosenCardId': 'A',
            })
            self.assertEqual(purchase.status_code, 201, purchase.text)
            cursor = purchase.json()['id']
            self.assertEqual(wallet.put(f'/api/me/purchases/{cursor}/cashback', json={'amountKopecks': 5_000}).status_code, 204)
            before = wallet.get('/api/me/stats').json()
            cookie = wallet.client.cookies.get('advisor_session')
            assert cookie is not None
            old_session.client.cookies.set('advisor_session', cookie)
            self.assertEqual(wallet.post('/api/auth/logout').status_code, 204)
            self.assertEqual(old_session.get('/api/me/stats').status_code, 401)
            self.assertEqual(wallet.post('/api/auth/login', json={'login': 'persist_wallet', 'password': password}).status_code, 200)
            self.assertEqual(wallet.get('/api/me/cards').json(), ['A'])
            self.assertEqual(wallet.get('/api/me/stats').json(), before)

    def test_monthly_provenance_and_slot_cap(self):
        card = self.confirm(slots=1, rules=[rule('Кино', 'Кино')]).json()['cardId']
        self.assertEqual(self.confirm('overflow', [rule('Афиша', 'Афиша')], slots=1, cardId=card).status_code, 422)
        self.assertEqual(self.confirm('both', [rule('Афиша', 'Афиша', 800)], slots=2, cardId=card).status_code, 200)
        self.assertEqual(self.confirm('options', [rule('Кино', 'Кино'), rule('Афиша', 'Афиша')], slots=1, mode='offer', cardId=card).status_code, 200)
        for cid, rate in [('Афиша', 800), ('Кино', 500)]:
            item, = self.client.post('/api/recommendations', json=dict(categoryId=cid, amountKopecks=10000, scope='mine')).json()['allMatches']
            self.assertEqual((item['rateBps'], item['bankName'], item['source'], item['updatedOn']), (rate, 'СберБанк', 'confirmed', '2026-11-20'))

    def test_catalog_suggestion_not_a_wallet_match(self):
        body = dict(categoryId='supermarkets', amountKopecks=250000, scope='mine')
        result = self.client.post('/api/recommendations', json=body).json()
        self.assertEqual((result['top3'], result['allMatches'], result['catalogSuggestion']['cardId']), ([], [], 'B'))
        self.client.put('/api/me/cards/A')
        self.assertNotIn('catalogSuggestion', self.client.post('/api/recommendations', json=body).json())

    def test_concurrent_partial_uploads_preserve_both_rows(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        gate = Barrier(2)
        cookie = self.client.client.cookies.get('advisor_session')
        def upload(label):
            with API(self.app) as peer:
                peer.client.cookies.set('advisor_session', cookie)
                gate.wait(timeout=5)
                return peer.post('/api/me/cashback-confirm', json=dict(
                    bankId='sber', month=MONTH, mode='active', slots=2, requestId=label,
                    rules=[rule(label,label)])).json()['cardId']
        with ThreadPoolExecutor(max_workers=2) as workers:
            ids = list(workers.map(upload, ['Такси', 'Метро']))
        self.assertEqual(ids[0], ids[1])
        with connect(self.path) as db:
            payload, = db.execute('SELECT rules_json FROM cashback_sets').fetchone()
        self.assertEqual({r['label'] for r in json.loads(payload)}, {'Такси', 'Метро'})

    def test_ambiguous_bank_needs_card_id(self):
        for _ in range(2):
            self.client.post('/api/me/manual-cards',json=dict(name='СберБанк',rules=[]))
        self.assertEqual(self.confirm().status_code,409)
        self.assertEqual(len(self.client.get('/api/me/manual-cards').json()),2)

    def test_old_users_not_dropped(self):
        legacy=self.path.with_suffix('.legacy')
        with connect(legacy) as db:
            db.execute('CREATE TABLE users(session TEXT PRIMARY KEY, login TEXT UNIQUE, created_on TEXT)')
            db.execute("INSERT INTO users VALUES('old','old','2026-01-01')")
        initialize(legacy)
        with connect(legacy) as db:
            self.assertEqual(db.execute('SELECT login FROM users').fetchall(), [('old',)])

    def test_edit_rate_preserves_monthly_limit_and_never_changes_public_catalog(self):
        confirmed = self.confirm()
        card = confirmed.json()['cardId']
        limits = f'/api/me/cards/{card}/monthly'
        rates = f'/api/me/manual-cards/{card}/rate'
        config = {'limitKopecks': 5000, 'usedKopecks': 3500}
        rank = dict(scope='mine', amountKopecks=50000, categoryId='Такси')
        public = dict(scope='all', amountKopecks=250000, categoryId='supermarkets')
        old_catalog = self.client.post('/api/recommendations', public).json()
        self.assertEqual(self.client._request('PUT', limits, config).json()['remainingKopecks'], 1500)
        self.assertEqual(self.client.post('/api/recommendations', rank).json()['top3'][0]['cashbackKopecks'], 1500)
        change = {'categoryId': 'Такси', 'label': 'Такси', 'rateBps': 200}
        self.assertEqual(self.client._request('PATCH', rates, change).status_code, 204)
        self.assertEqual(self.client.post('/api/recommendations', rank).json()['top3'][0]['cashbackKopecks'], 1000)
        self.assertEqual(self.client.get(limits).json(), dict(month=MONTH, remainingKopecks=1500, **config))
        self.assertEqual(self.client.post('/api/recommendations', public).json(), old_catalog)
        with API(self.app) as other:
            self.login(other, 'another_owner')
            self.assertEqual(other.get(limits).status_code, 404)
            self.assertEqual(other._request('PATCH', rates, change).status_code, 404)
        self.assertEqual(self.client._request('PUT', limits, {**config, 'usedKopecks':5000}).status_code, 200)
        self.assertEqual(self.client.post('/api/recommendations', rank).json()['top3'][0]['cashbackKopecks'], 0)

    def test_rule_dates_and_limit_apply_to_private_recommendations(self):
        confirmed = self.confirm(rules=[rule(validFrom='2026-11-20', validThrough='2026-11-20', limitKopecks=800)])
        self.assertEqual(confirmed.status_code, 200)
        card = confirmed.json()['cardId']
        path = f'/api/me/manual-cards/{card}/rate'
        rank = dict(scope='mine', amountKopecks=50_000, categoryId='Такси')
        change = dict(categoryId='Такси', label='Такси', source='active', month=MONTH, rateBps=500)
        self.assertEqual(self.client.post('/api/recommendations', rank).json()['top3'][0]['cashbackKopecks'], 800)
        invalid = {**change, 'validFrom': '2026-11-22', 'limitKopecks': 100}
        self.assertEqual(self.client._request('PATCH', path, invalid).status_code, 422)
        self.assertEqual(self.client.post('/api/recommendations', rank).json()['top3'][0]['cashbackKopecks'], 800)

        future = dict(validFrom='2026-11-21', validThrough=None, limitKopecks=1200)
        self.assertEqual(self.client._request('PATCH', path, {**change, **future}).status_code, 204)
        self.assertEqual(self.client.post('/api/recommendations', rank).json()['top3'], [])
        stored = self.client.get('/api/me/manual-cards').json()[0]['rules'][0]
        self.assertEqual({key: stored[key] for key in future}, future)
        self.assertEqual(self.client._request('PATCH', path, {**change, 'validFrom': None}).status_code, 204)
        self.assertEqual(self.client.post('/api/recommendations', rank).json()['top3'][0]['cashbackKopecks'], 1200)

    def test_wallet_journal_on_database_from_previous_release(self):
        legacy = self.path.with_suffix('.staging')
        with connect(legacy) as db:
            db.executescript('''
                CREATE TABLE purchases (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, day TEXT NOT NULL,
                    category TEXT NOT NULL, merchant TEXT NOT NULL, amount INTEGER NOT NULL,
                    used_card TEXT, estimates TEXT NOT NULL
                );
                INSERT INTO purchases VALUES
                    ('classic-1','old-owner','2026-11-10','Еда','Магазин',60000,NULL,'{}');
            ''')
        initialize(legacy)
        with API(create_app(legacy)) as client:
            with connect(legacy) as db:
                db.execute("ALTER TABLE manual_cards ADD COLUMN bank_name TEXT NOT NULL DEFAULT ''")
                db.execute('ALTER TABLE manual_cards ADD COLUMN monthly_limit INTEGER')
                db.execute('ALTER TABLE saved ADD COLUMN monthly_limit INTEGER')
            self.login(client, 'next_wallet')
            self.assertEqual(client._request('PUT', '/api/me/cards/A', None).status_code, 204)
            self.assertEqual(client.get('/api/me/cards').json(), ['A'])
            card = client.post('/api/me/manual-cards', json={
                'name': 'СберБанк', 'rules': [{'categoryId': 'fuel', 'rateBps': 400}],
            }).json()['cardId']
            purchase = client.post('/api/me/purchases', json={
                'chosenCardId': card, 'categoryId': 'fuel', 'amountKopecks': 25_000,
            })
            self.assertEqual(purchase.status_code, 201, purchase.text)
            self.assertEqual(client.get('/api/me/stats').json()['calculatedKopecks'], 1000)
            plan = client.post('/api/me/cashback-plan', json={'month': MONTH, 'spendingMonth': MONTH})
            self.assertEqual(plan.status_code, 200, plan.text)
        initialize(legacy)
        with connect(legacy) as db:
            self.assertEqual(db.execute('SELECT id, amount FROM purchases').fetchall(), [('classic-1', 60_000)])
            self.assertEqual(db.execute('SELECT amount_kopecks FROM wallet_purchases').fetchall(), [(25_000,)])
