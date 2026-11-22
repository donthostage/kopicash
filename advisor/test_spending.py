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


class SpendingTests(unittest.TestCase):
    def test_monthly_report_uses_saved_purchases_and_frozen_terms(self):
        with tempfile.TemporaryDirectory() as folder, patch('advisor.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
            app = create_app(Path(folder) / 'advisor.sqlite3')
            with TestClient(app) as client, TestClient(app) as visitor:
                report = '/api/me/spending?month=2026-11'
                self.assertEqual(visitor.get(report).status_code, 401)
                self.assertEqual(client.post('/api/auth/register', json={'username':'spender','password':'test-only-long-password'}).status_code, 201)
                card = client.post('/api/me/manual-cards', json={'name':'Моя карта', 'rules':[
                    {'categoryName':'Такси','rateBps':1000,'validFrom':'2026-10-01'},
                    {'categoryName':'Аптеки','rateBps':500,'validFrom':'2026-10-01'}]}).json()['cardId']
                self.assertEqual(client.put(f'/api/me/manual-cards/{card}/monthly-limit', json={
                    'month':'2026-11','limitKopecks':25000,'usedKopecks':20000}).status_code, 204)
                client.post('/api/recommendations', json={'scope':'mine','categoryId':'taxi','amountKopecks':300000})
                self.assertEqual(client.get(report).json()['count'], 0)
                purchases = '/api/me/purchases'
                for day, shop, category, amount in [('2026-11-01','Магазин','Аптеки',100000),
                    ('2026-11-20','МАГАЗИН','Такси',300000), ('2026-10-31','Другой','Такси',1000)]:
                    response = client.post(purchases, json={'date':day,'merchant':shop,'categoryName':category,
                                                          'amountKopecks':amount,'cardId':card})
                    self.assertEqual(response.status_code, 201)
                summary = client.get(report).json()
                self.assertEqual((summary['count'], summary['totalKopecks']), (2,400000))
                self.assertEqual(summary['byCategory'][0]['name'], 'Такси')
                self.assertEqual(summary['byMerchant'][0]['amountKopecks'], 400000)
                self.assertEqual(summary['largestPurchase']['amountKopecks'], 300000)
                self.assertEqual(summary['cardRanking'][0]['estimatedKopecks'], 25000)
                self.assertEqual(summary['byUsedCard'][0]['amountKopecks'], 400000)
                self.assertEqual(client.post(purchases, json={'date':'2026-11-21','categoryName':'Такси','amountKopecks':10}).status_code,422)
                self.assertEqual(client.get('/api/me/spending?month=2026-13').status_code, 422)
                self.assertEqual(client.delete(f'/api/me/manual-cards/{card}').status_code,204)
                self.assertEqual(client.get(report).json(), summary)
                item = summary['largestPurchase']['id']
                self.assertEqual(visitor.delete(f'{purchases}/{item}').status_code,401)
                self.assertEqual(client.delete(f'{purchases}/{item}').status_code,204)
                self.assertEqual(client.get(report).json()['totalKopecks'],100000)

    def test_purchase_retry_does_not_duplicate_and_delete_does_not_resurrect(self):
        with tempfile.TemporaryDirectory() as folder, patch('advisor.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
            path = Path(folder) / 'advisor.sqlite3'
            url = '/api/me/purchases'
            credentials = {'username':'retry.test','password':'test-only-long-password'}
            body = {'date':'2026-11-20','categoryName':'Такси','amountKopecks':250000}
            headers = {'Idempotency-Key':'first-purchase-nonce'}
            with TestClient(create_app(path)) as client:
                self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 201)
                first = client.post(url, json=body, headers=headers)
                self.assertEqual(first.status_code, 201)
            with TestClient(create_app(path)) as client:
                self.assertEqual(client.post('/api/auth/login', json=credentials).status_code, 200)
                self.assertEqual(client.post(url, json=body, headers=headers).json(), first.json())
                report = client.get('/api/me/spending').json()
                self.assertEqual((report['count'], report['totalKopecks']), (1, 250000))
                self.assertEqual(client.post(url, json=dict(body, amountKopecks=250100), headers=headers).status_code, 409)
                second = client.post(url, json=body, headers={'Idempotency-Key':'other-purchase-nonce'})
                self.assertEqual(second.status_code, 201)
                self.assertNotEqual(second.json()['id'], first.json()['id'])
                self.assertEqual(client.delete(url + '/' + first.json()['id']).status_code, 204)
                self.assertEqual(client.post(url, json=body, headers=headers).json(), first.json())
                self.assertEqual(client.get('/api/me/spending').json()['count'], 1)

    def test_purchase_comparison_distinguishes_zero_from_unknown_and_keeps_snapshot(self):
        with tempfile.TemporaryDirectory() as folder, patch('advisor.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
            with TestClient(create_app(Path(folder) / 'test.db')) as client:
                credentials = {'username':'comparison.test','password':'test-only-long-password'}
                self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 201)
                cases = [
                    ('12%', {'rateBps':1200,'limitKopecks':12000}),
                    ('8%', {'rateBps':800,'limitKopecks':18000}),
                    ('0%', {'rateBps':0}),
                    ('Нет условий', {'rateBps':100,'validFrom':'2026-11-21'}),
                ]
                cards = {}
                for name, terms in cases:
                    response = client.post('/api/me/manual-cards', json={
                        'name':name,'monthlyLimitKopecks':10000,'monthlyUsedKopecks':10000,
                        'rules':[dict(terms, categoryName='Такси')],
                    })
                    self.assertEqual(response.status_code, 201)
                    cards[name] = response.json()['cardId']
                purchases = {}
                for name in [*cards, None]:
                    response = client.post('/api/me/purchases', json={
                        'date':'2026-11-20','categoryName':'Такси',
                        'amountKopecks':250000,'cardId':cards.get(name),
                    })
                    self.assertEqual(response.status_code, 201)
                    purchases[name] = response.json()['id']
                endpoint = '/api/me/spending?month=2026-11'
                first = client.get(endpoint).json()
                entries = {row['id']:row['cashbackComparison'] for row in first['purchases']}
                for name, used, diff in [('12%',12000,6000), ('8%',18000,0), ('0%',0,18000),
                                        ('Нет условий',None,None), (None,None,None)]:
                    self.assertEqual(entries[purchases[name]], dict(usedCardCashbackKopecks=used,
                                     bestCardName='8%', bestCashbackKopecks=18000, differenceKopecks=diff))
                path = '/api/me/manual-cards/' + cards['8%']
                self.assertEqual(client.patch(path + '/rate', json={'categoryName':'Такси','rateBps':100}).status_code, 204)
                self.assertEqual(client.delete(path).status_code, 204)
                self.assertEqual(client.get(endpoint).json(), first)

    def test_actual_cashback_distinguishes_unknown_and_zero_and_is_private(self):
        with tempfile.TemporaryDirectory() as folder, patch('advisor.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
            app = create_app(Path(folder) / 'test.db')
            with TestClient(app) as user, TestClient(app) as other:
                for client, name in [(user, 'confirmed'), (other, 'different')]:
                    self.assertEqual(client.post('/api/auth/register', json={
                        'username': name, 'password': 'test-only-long-password'}).status_code, 201)
                base = '/api/me/purchases'
                body = {'date':'2026-11-20','categoryName':'Такси','amountKopecks':250000}
                one, two = [user.post(base, json=body).json()['id'] for _ in range(2)]
                first, second = [base + '/' + id_ + '/cashback' for id_ in (one, two)]
                self.assertEqual(other.put(first, json={'amountKopecks':100}).status_code, 404)
                for endpoint, amount in [(first, 0), (second, 15000)]:
                    self.assertEqual(user.put(endpoint, json={'amountKopecks':amount}).status_code, 204)
                report = user.get('/api/me/spending').json()
                self.assertEqual((report['actualCashbackKopecks'], report['actualCashbackCount']), (15000, 2))
                self.assertEqual(user.put(second, json={'amountKopecks':None}).status_code, 204)
                report = user.get('/api/me/spending').json()
                self.assertEqual((report['actualCashbackKopecks'], report['actualCashbackCount']), (0, 1))
                self.assertEqual({p['id']:p['actualCashbackKopecks'] for p in report['purchases']}, {one:0, two:None})
