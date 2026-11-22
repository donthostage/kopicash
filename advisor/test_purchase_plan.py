from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from advisor import create_app


class PurchasePlanTests(TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.app = create_app(Path(directory) / 'plan.sqlite3')
        self.client = self.enterContext(TestClient(self.app))
        self.purchases = [
            dict(categoryId='supermarkets', amountKopecks=100_000),
            dict(categoryId='transport', amountKopecks=100_000),
        ]

    def add_card(self, name, supermarket, transport):
        response = self.client.post('/api/me/manual-cards', json=dict(name=name, rules=[
            dict(categoryId='supermarkets', rateBps=supermarket),
            dict(categoryId='transport', rateBps=transport),
        ]))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['cardId']

    def test_reserves_the_shared_cap_for_the_purchase_that_benefits_most(self):
        response = self.client.post('/api/auth/register', json=dict(login='plan_user', password='test-long-password'))
        self.assertEqual(response.status_code, 201, response.text)
        first = self.add_card('А', 1000, 1000)
        second = self.add_card('Б', 800, 100)
        limit = f'/api/me/cards/{first}/monthly'
        response = self.client.put(limit, json=dict(limitKopecks=30_000, usedKopecks=20_000))
        self.assertEqual(response.status_code, 200, response.text)

        response = self.client.post('/api/me/purchase-plan', json=dict(purchases=self.purchases))
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['optimized']['totalKopecks'], 18_000)
        self.assertEqual(result['sequential']['totalKopecks'], 11_000)
        self.assertEqual(result['gainKopecks'], 7_000)
        reason = result['explanation']
        self.assertEqual(reason['code'], 'shared_limit')
        self.assertEqual(reason['cardId'], first)
        self.assertEqual((reason['reserveFromPurchaseIndex'], reason['useAtPurchaseIndex']), (0, 1))
        self.assertEqual([change['deltaKopecks'] for change in reason['changes']], [-2_000, 9_000])
        self.assertEqual([row['cardId'] for row in result['optimized']['purchases']], [second, first])
        self.assertEqual(self.client.get(limit).json()['usedKopecks'], 20_000)
        self.assertEqual(self.client.get('/api/me/stats').json()['count'], 0)

        response = self.client.put(limit, json=dict(limitKopecks=10_000, usedKopecks=None))
        self.assertEqual(response.status_code, 200, response.text)
        result = self.client.post('/api/me/purchase-plan', json=dict(purchases=self.purchases)).json()
        self.assertEqual(result['assumedFullCardIds'], [first])
        self.assertEqual(result['assumedFullCards'], [dict(cardId=first, cardName='А')])

        with TestClient(self.app) as other:
            result = other.post('/api/me/purchase-plan', json=dict(purchases=self.purchases)).json()
            self.assertEqual(result['optimized']['totalKopecks'], 0)
            self.assertEqual(result['explanation'], dict(code='same_total', changes=[]))
            self.assertEqual([entry['cardId'] for entry in result['optimized']['purchases']], [None, None])

    def test_validates_count_category_and_amount(self):
        for purchases in [[], self.purchases[:1], self.purchases * 5,
                          [self.purchases[0], dict(categoryId='missing', amountKopecks=1)],
                          [self.purchases[0], dict(categoryId='cafe', amountKopecks=True)]]:
            with self.subTest(purchases=purchases):
                response = self.client.post('/api/me/purchase-plan', json=dict(purchases=purchases))
                self.assertEqual(response.status_code, 422, response.text)

    def test_card_and_category_balances_are_shared_and_roll_over(self):
        clock = self.enterContext(patch('advisor.datetime'))
        clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
        credentials = dict(login='monthly_user', password='test-long-password')
        self.assertEqual(self.client.post('/api/auth/register', json=credentials).status_code, 201)
        response = self.client.post('/api/me/manual-cards', json=dict(name='Тестовая карта', rules=[
            dict(categoryId='all', rateBps=1000, limitKopecks=150_000),
            dict(categoryId='fuel', rateBps=1000),
        ]))
        self.assertEqual(response.status_code, 201, response.text)
        card = response.json()['cardId']
        endpoint = f'/api/me/cards/{card}/cashback-limits'
        category = dict(categoryId='all', limitKopecks=300_000, usedKopecks=10_000)
        body = dict(month='2026-11', card=dict(limitKopecks=400_000, usedKopecks=100_000),
                    categories=[category])
        response = self.client.put(endpoint, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json()
        self.assertEqual(saved['card']['remainingKopecks'], 300_000)
        self.assertEqual(next(item for item in saved['categories'] if item['categoryId'] == 'all')
                         ['remainingKopecks'], 290_000)
        bad = dict(body, card=dict(limitKopecks=0, usedKopecks=0), categories=[category, category])
        self.assertEqual(self.client.put(endpoint, json=bad).status_code, 422)

        with TestClient(self.app) as other:
            other.post('/api/auth/register', json=dict(credentials, login='other_monthly_user'))
            self.assertEqual(other.get(endpoint).status_code, 404)
        self.assertEqual(self.client.post('/api/auth/login', json=credentials).status_code, 200)
        self.assertEqual(self.client.get(endpoint).json(), saved)

        purchases = [dict(item, amountKopecks=2_000_000) for item in self.purchases]
        purchases.append(dict(categoryId='fuel', amountKopecks=2_000_000))
        quote = self.client.post('/api/recommendations', json=dict(purchases[0], scope='mine')).json()['top3'][0]
        self.assertEqual(quote['cashbackKopecks'], 150_000)
        self.assertEqual(quote['calculation']['monthlyCategoryRemainingKopecks'], 290_000)
        result = self.client.post('/api/me/purchase-plan', json=dict(purchases=purchases)).json()
        self.assertEqual([item['cashbackKopecks'] for item in result['optimized']['purchases']],
                         [150_000, 140_000, 10_000])
        self.assertEqual(self.client.get(endpoint).json(), saved)
        self.assertEqual(self.client.get('/api/me/stats').json()['count'], 0)

        clock.now.return_value = datetime(2026, 12, 1, tzinfo=UTC)
        self.assertEqual(self.client.put(endpoint, json=body).status_code, 409)
        current = self.client.get(endpoint).json()
        self.assertEqual(current['card']['remainingKopecks'], 400_000)
        matching = next(item for item in current['categories'] if item['categoryId'] == 'all')
        self.assertIsNone(matching['usedKopecks'])
        self.assertEqual(matching['remainingKopecks'], 300_000)
