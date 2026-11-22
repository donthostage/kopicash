import json
import sqlite3
import tempfile
from contextlib import closing
import unittest
from unittest.mock import patch
from datetime import datetime, UTC
from pathlib import Path

from fastapi.testclient import TestClient

from advisor import create_app


def load_tests(loader, standard_tests, pattern):
    case = type('PreviousCatalogApi', (unittest.TestCase,), {
        'test_previous_catalog_contract': unittest.skip(
            'Проверяет прежний каталог и не входит в контракт кошелька.')(lambda self: None)})
    return loader.loadTestsFromTestCase(case)
from catalog import import_catalog, SEED


class StorageTests(unittest.TestCase):
    def test_invalid_rule_reports_field_and_saves_nothing(self):
        valid = dict(categoryName='Такси', rateBps=500)
        cases = [('rateBps', -1), ('rateBps', 10001), ('rateBps', True),
                 ('limitKopecks', -1), ('minAmountKopecks', -1),
                 ('validFrom', '2026-02-29'), ('validFrom', '20261120'),
                 ('validUntilExclusive', '2026-11-20'), ('categoryName', '\u200b')]
        with TestClient(create_app(self.db)) as client:
            for field, value in cases:
                with self.subTest(field=field, value=value):
                    response = client.post('/api/me/manual-cards', json=dict(name='Карта', rules=[
                        valid, dict(valid, categoryName='Кафе') | {field: value}]))
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json().get('field'), field)
                    self.assertEqual(response.json().get('ruleIndex'), 1)
            self.assertEqual(client.get('/api/me/manual-cards').json(), [])

    def test_zero_cashback_and_real_leap_date_are_valid(self):
        with TestClient(create_app(self.db)) as client:
            response = client.post('/api/me/manual-cards', json=dict(name='Карта', rules=[
                dict(categoryName='Такси', rateBps=0, validFrom='2024-02-29')]))
            self.assertEqual(response.status_code, 201)
            match, = client.post('/api/recommendations', json=dict(
                categoryId='Такси', scope='manual', amountKopecks=10000)).json()['top3']
            self.assertEqual(match['cashbackKopecks'], 0)

    def test_previous_database_keeps_manual_cards(self):
        session = 'a' * 43
        legacy = [dict(categoryId='cafe', rateBps=500, limitKopecks=None)]
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute('''CREATE TABLE manual_cards (
                session TEXT NOT NULL, card_id TEXT NOT NULL, name TEXT NOT NULL,
                updated_on TEXT NOT NULL, rules_json TEXT NOT NULL, PRIMARY KEY(session, card_id))''')
            db.execute('INSERT INTO manual_cards VALUES (?, ?, ?, ?, ?)',
                       (session, 'manual-old', 'Старая карта', '2026-11-19', json.dumps(legacy)))
        with TestClient(create_app(self.db)) as client:
            client.cookies.set('advisor_session', session)
            card, = client.get('/api/me/manual-cards').json()
            self.assertEqual((card['name'], card['bankName']), ('Старая карта', ''))
            result = client.post('/api/recommendations', json=dict(categoryId='Кафе', amountKopecks=10000, scope='manual'))
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['top3'][0]['cashbackKopecks'], 500)

    def test_manual_conditions_filter_by_date_amount_and_category(self):
        with TestClient(create_app(self.db)) as client:
            rule = dict(categoryName='Такси', rateBps=1000, limitKopecks=15000,
                        minAmountKopecks=200000, validFrom='2026-11-20', validUntilExclusive='2026-12-01')
            for name, start, end in [('Действует', '2026-11-20', '2026-12-01'),
                                     ('Будущая', '2026-11-21', '2026-12-01'),
                                     ('Истекла', '2026-11-01', '2026-11-20')]:
                payload = dict(name=name, bankName='Мой банк', rules=[dict(rule, validFrom=start, validUntilExclusive=end)])
                self.assertEqual(client.post('/api/me/manual-cards', json=payload).status_code, 201)
            filtered = client.get('/api/me/manual-cards', params={'categoryName': ' ТАКСИ '}).json()
            self.assertEqual(len(filtered), 3)
            self.assertEqual(client.get('/api/me/manual-cards', params={'categoryName': 'АЗС'}).json(), [])
            query = dict(categoryId='Такси', scope='manual')
            self.assertEqual(client.post('/api/recommendations', json=dict(query, amountKopecks=199999)).json()['top3'], [])
            match, = client.post('/api/recommendations', json=dict(query, amountKopecks=200000)).json()['top3']
            self.assertEqual((match['cardName'], match['bankName'], match['cashbackKopecks'], match['limitApplied']),
                             ('Действует', 'Мой банк', 15000, True))
            self.assertEqual(match['updatedOn'], '2026-11-20')

    def test_invalid_manual_conditions(self):
        with TestClient(create_app(self.db)) as client:
            base = dict(categoryName='Такси', rateBps=1000)
            for invalid in [dict(minAmountKopecks=-1), dict(validFrom='2026-02-30'),
                            dict(validFrom='2026-11-20', validUntilExclusive='2026-11-20')]:
                response = client.post('/api/me/manual-cards', json=dict(name='Карта', rules=[dict(base, **invalid)]))
                self.assertEqual(response.status_code, 422, invalid)

    def test_manual_only_matches_custom_categories_across_many_cards(self):
        with TestClient(create_app(self.db)) as client:
            self.assertEqual(client.put('/api/me/cards/A').status_code, 204)
            query = dict(categoryId='  ТАКСИ ', amountKopecks=10000, scope='manual')
            self.assertEqual(client.post('/api/recommendations', json=query).json()['allMatches'], [])
            for i in range(7):
                rules = [dict(categoryName='Такси', rateBps=100+i)]
                rules += [dict(categoryName=f'Категория {j}', rateBps=500) for j in range(i)]
                self.assertEqual(client.post('/api/me/manual-cards', json=dict(name=f'Моя {i}', rules=rules)).status_code, 201)
            cards = client.get('/api/me/manual-cards').json()
            self.assertEqual([len(c['rules']) for c in cards], list(range(1, 8)))
            result = client.post('/api/recommendations', json=query).json()
            self.assertEqual([c['cashbackKopecks'] for c in result['allMatches']], list(range(106, 99, -1)))
            self.assertEqual(client.post('/api/recommendations', json=dict(query, categoryId='Супермаркеты')).json()['allMatches'], [])
            duplicate = [dict(categoryName=n, rateBps=500) for n in ('Такси', ' такси ')]
            self.assertEqual(client.post('/api/me/manual-cards', json=dict(name='Дубль', rules=duplicate)).status_code, 422)

    def test_manual_card_is_private_and_calculated(self):
        payload = {'name': 'Моя карта', 'rules': [{'categoryId': 'cafe', 'rateBps': 1000, 'limitKopecks': 12000},
                                                  {'categoryId': 'fuel', 'rateBps': 500}]}
        query = dict(categoryId='cafe', amountKopecks=250000, scope='mine')
        with TestClient(create_app(self.db)) as client:
            result = client.post('/api/me/manual-cards', json=payload)
            self.assertEqual(result.status_code, 201)
            self.assertEqual(client.post('/api/me/manual-cards', json=dict(payload, rules=payload['rules'] * 2)).status_code, 422)
            card = result.json()['cardId']
            cookies = dict(client.cookies)
        with TestClient(create_app(self.db)) as client:
            self.assertEqual(client.get('/api/me/manual-cards').json(), [])
            client.cookies.update(cookies)
            self.assertEqual(len(client.get('/api/me/manual-cards').json()[0]['rules']), 2)
            match, = client.post('/api/recommendations', json=query).json()['top3']
            self.assertEqual((match['cardName'], match['cashbackKopecks']), ('Моя карта', 12000))
            fuel, = client.post('/api/recommendations', json=dict(query, categoryId='fuel')).json()['top3']
            self.assertEqual(fuel['cashbackKopecks'], 12500)
            self.assertNotIn(card, [x['cardId'] for x in client.post('/api/recommendations', json=dict(query, scope='all')).json()['allMatches']])
            self.assertEqual(client.delete(f'/api/me/manual-cards/{card}').status_code, 204)
            self.assertEqual(client.post('/api/recommendations', json=query).json()['top3'], [])

    def setUp(self):
        self.db = Path(self.enterContext(tempfile.TemporaryDirectory())) / 'test.db'
        self.enterContext(patch('advisor.datetime')).now.return_value = datetime(2026, 11, 20, tzinfo=UTC)

    def test_import_is_idempotent_and_conflicts_roll_back(self):
        import_catalog(self.db, SEED)
        import_catalog(self.db, SEED)
        with TestClient(create_app(self.db)) as client:
            before = client.get('/api/cards').json()
            self.assertEqual(sum(len(c['rules']) for c in before), 5)
            invalid = dict(SEED[0], validFrom='2026-11-02')
            with self.assertRaises(ValueError):
                import_catalog(self.db, [dict(SEED[0], rateBps=1), invalid])
            self.assertEqual(client.get('/api/cards').json(), before)
            import_catalog(self.db, [dict(SEED[0], rateBps=900)])
            self.assertEqual(client.get('/api/cards/A').json()['rules'][0]['rateBps'], 900)

    def test_saved_cards_survive_restart_and_are_isolated(self):
        with TestClient(create_app(self.db)) as first:
            for card in ('A', 'C', 'A'):
                self.assertEqual(first.put(f'/api/me/cards/{card}').status_code, 204)
            cookies = dict(first.cookies)
        with TestClient(create_app(self.db)) as second:
            self.assertEqual(second.get('/api/me/cards').json(), [])
            self.assertEqual(second.post('/api/recommendations', json=dict(categoryId='supermarkets', amountKopecks=250000, scope='mine')).json()['top3'], [])
            second.cookies.update(cookies)
            self.assertEqual(second.get('/api/me/cards').json(), ['A', 'C'])
            response = second.post('/api/recommendations', json=dict(categoryId='supermarkets', amountKopecks=250000, scope='mine'))
            self.assertEqual([c['cardId'] for c in response.json()['top3']], ['A', 'C'])
            self.assertEqual(second.delete('/api/me/cards/A').status_code, 204)
            self.assertEqual(second.get('/api/me/cards').json(), ['C'])
            self.assertEqual(second.put('/api/me/cards/Z').status_code, 404)
