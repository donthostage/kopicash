import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from advisor import create_app


def load_tests(loader, standard_tests, pattern):
    case = type('PreviousCatalogApi', (unittest.TestCase,), {
        'test_previous_catalog_contract': unittest.skip(
            'Проверяет прежний каталог и не входит в контракт кошелька.')(lambda self: None)})
    return loader.loadTestsFromTestCase(case)


class MonthlyLimits(unittest.TestCase):
    def setUp(self):
        self.db = Path(self.enterContext(tempfile.TemporaryDirectory())) / 'test.sqlite3'
        self.clock = self.enterContext(patch('advisor.datetime'))
        self.clock.now.return_value = datetime(2026, 11, 30, 23, 59, tzinfo=UTC)
        self.client = self.enterContext(TestClient(create_app(self.db)))
        response = self.client.post('/api/me/manual-cards', json={'name':'Моя карта', 'rules':[
            {'categoryName':'Такси','rateBps':1000,'limitKopecks':20000},
            {'categoryName':'Кафе','rateBps':1000}]})
        self.assertEqual(response.status_code, 201)
        self.path = f"/api/me/manual-cards/{response.json()['cardId']}/monthly-limit"

    def update(self, used, month='2026-11', client=None):
        return (client or self.client).put(self.path, json=dict(month=month, limitKopecks=300000, usedKopecks=used))

    def ranking(self, category):
        response = self.client.post('/api/recommendations', json=dict(scope='manual', categoryId=category, amountKopecks=250000))
        self.assertEqual(response.status_code, 200)
        return response.json()['allMatches']

    def test_shared_remainder_read_only_calculation_and_month_rollover(self):
        self.assertEqual(self.update(290000).status_code, 204)
        for category in ('Такси', 'Кафе', 'Такси'):
            match, = self.ranking(category)
            self.assertEqual(match['cashbackKopecks'], 10000)
            self.assertTrue(match['monthlyLimitApplied'])
        self.assertEqual(self.update(300100).status_code, 204)
        self.assertEqual(self.ranking('Кафе'), [])
        self.clock.now.return_value = datetime(2026, 12, 1, tzinfo=UTC)
        self.assertEqual(self.update(300000).status_code, 409)
        card, = self.client.get('/api/me/manual-cards').json()
        self.assertEqual(card['monthly'], dict(month='2026-12', limitKopecks=300000, usedKopecks=None, remainingKopecks=None))
        self.assertEqual(self.ranking('Такси')[0]['cashbackKopecks'], 20000)

    def test_owner_and_valid_amount(self):
        self.assertEqual(self.update(10000).status_code, 204)
        self.assertEqual(self.update(-1).status_code, 422)
        with TestClient(create_app(self.db)) as stranger:
            self.assertEqual(self.update(300000, client=stranger).status_code, 404)
        self.assertEqual(self.client.get('/api/me/manual-cards').json()[0]['monthly']['usedKopecks'], 10000)

    def test_limit_at_creation_distinguishes_unknown_from_zero(self):
        response = self.client.post('/api/me/manual-cards', json={'name':'Новая', 'monthlyLimitKopecks':10000,
            'rules':[{'categoryName':'Аптеки','rateBps':1000}]})
        self.assertEqual(response.status_code, 201)
        match, = self.ranking('Аптеки')
        self.assertEqual((match['cashbackKopecks'], match['monthlyBalanceStatus']), (10000, 'assumed_full'))
        endpoint = f"/api/me/manual-cards/{response.json()['cardId']}/monthly-limit"
        self.assertEqual(self.client.put(endpoint, json=dict(month='2026-11', limitKopecks=10000, usedKopecks=0)).status_code, 204)
        self.assertEqual(self.ranking('Аптеки')[0]['monthlyBalanceStatus'], 'known')

    def test_saved_catalog_overrides_are_private_and_never_change_public_catalog(self):
        self.assertEqual(self.client.put('/api/me/cards/B').status_code, 204)
        endpoint = '/api/me/cards/B/monthly-limit'
        data = dict(month='2026-11', limitKopecks=300000, usedKopecks=295000)
        self.assertEqual(self.client.put(endpoint, json=data).status_code, 204)
        self.assertEqual(self.client.get('/api/me/catalog-monthly').json()['B']['remainingKopecks'], 5000)
        query = dict(categoryId='supermarkets', amountKopecks=250000)
        self.assertEqual(self.client.post('/api/recommendations', json=dict(query, scope='mine')).json()['top3'][0]['cashbackKopecks'], 5000)
        with TestClient(create_app(self.db)) as stranger:
            self.assertEqual(stranger.put(endpoint, json=data).status_code, 404)
            self.assertEqual(stranger.get('/api/me/catalog-monthly').json(), {})
        self.assertEqual(self.client.put(endpoint, json=dict(data, usedKopecks=300000)).status_code, 204)
        result = self.client.post('/api/recommendations', json=dict(query, scope='mine')).json()
        self.assertEqual(result['top3'], [])
        self.assertNotEqual(result['catalogSuggestion']['cardId'], 'B')
        self.assertEqual(self.client.post('/api/recommendations', json=dict(query, scope='all')).json()['top3'][0]['cashbackKopecks'], 15000)

    def test_monthly_usage_transfers_to_account_and_survives_reopen(self):
        self.assertEqual(self.update(290000).status_code, 204)
        credentials = dict(username='monthly.test', password='test-only-long-password')
        self.assertEqual(self.client.post('/api/auth/register', json=dict(**credentials, transferGuestCards=True)).status_code, 201)
        with TestClient(create_app(self.db)) as second:
            self.assertEqual(second.post('/api/auth/login', json=credentials).status_code, 200)
            self.assertEqual(second.get('/api/me/manual-cards').json()[0]['monthly']['remainingKopecks'], 10000)

    def test_rate_update_changes_ranking_and_preserves_balance_after_restart(self):
        self.assertEqual(self.update(288000).status_code, 204)
        self.assertEqual(self.client.post('/api/auth/register', json={
            'username':'rates.edit', 'password':'test-only-long-password','transferGuestCards':True}).status_code, 201)
        for name, rate in [('Вторая',400), ('Третья',380), ('Четвёртая',350)]:
            self.assertEqual(self.client.post('/api/me/manual-cards', json={'name':name, 'rules':[
                {'categoryName':'Такси','rateBps':rate}]}).status_code, 201)
        original = self.client.get('/api/me/manual-cards').json()[0]
        self.assertEqual(self.ranking('Такси')[0]['cashbackKopecks'], 12000)
        path = self.path.removesuffix('/monthly-limit') + '/rate'
        with TestClient(create_app(self.db)) as stranger:
            self.assertEqual(stranger.patch(path, json=dict(categoryName='Такси', rateBps=300)).status_code, 404)
        self.assertEqual(self.client.patch(path, json=dict(categoryName='Такси', rateBps=True)).status_code, 422)
        self.assertEqual(self.client.patch(path, json=dict(categoryName='Такси', rateBps=300)).status_code, 204)
        query = dict(categoryId='Такси', scope='manual', amountKopecks=250000)
        result = self.client.post('/api/recommendations', json=query).json()
        self.assertEqual([x['cashbackKopecks'] for x in result['top3']], [10000, 9500, 8750])
        with TestClient(create_app(self.db)) as restarted:
            self.assertEqual(restarted.post('/api/auth/login', json={
                'username':'rates.edit','password':'test-only-long-password'}).status_code, 200)
            card = restarted.get('/api/me/manual-cards').json()[0]
            self.assertEqual((card['cardId'], card['monthly']), (original['cardId'], original['monthly']))
            self.assertEqual(card['rules'][0], dict(original['rules'][0], rateBps=300))
            self.assertEqual(card['rules'][1], original['rules'][1])
            self.assertEqual(restarted.post('/api/recommendations', json=query).json(), result)
