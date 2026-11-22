from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from advisor import create_app


class CashbackBalanceTests(TestCase):
    def test_reconciliation_drives_single_purchase_and_plan_across_restarts(self):
        directory = self.enterContext(TemporaryDirectory())
        db = Path(directory) / 'wallet.sqlite3'
        clock = self.enterContext(patch('advisor.datetime'))
        clock.now.return_value = datetime(2026, 11, 21, 12, tzinfo=UTC)
        app = create_app(db)
        client = self.enterContext(TestClient(app))
        credentials = {'login': 'balance_user', 'password': 'test-password'}
        self.assertEqual(client.post('/api/auth/register', json=credentials).status_code, 201)

        def card(name):
            response = client.post('/api/me/manual-cards', json={'name': name, 'rules': [
                {'categoryId': 'supermarkets', 'rateBps': 1000},
            ]})
            self.assertEqual(response.status_code, 201, response.text)
            return response.json()['cardId']

        first, other = card('Первая карта'), card('Другая карта')
        endpoint = f'/api/me/cards/{first}/cashback-reconciliation'
        self.assertIsNone(client.get(endpoint).json()['remainingKopecks'])
        purchase = {'categoryId': 'supermarkets', 'amountKopecks': 500_000}

        def record(card_id, actual=None):
            response = client.post('/api/me/purchases', json={**purchase, 'chosenCardId': card_id})
            self.assertEqual(response.status_code, 201, response.text)
            id_ = response.json()['id']
            if actual is not None:
                self.assertEqual(set_actual(id_, actual).status_code, 204)
            return id_

        def set_actual(id_, amount):
            return client.put(f'/api/me/purchases/{id_}/cashback', json={'amountKopecks': amount})

        included, new = record(first, 5_000), record(first, 8_000)
        estimate_only, other_purchase = record(first), record(other, 9_000)
        draft = dict(month='2026-11', bankRemainingKopecks=30_000, includedPurchaseIds=[included])
        rows = client.get(endpoint).json()['accruals']
        self.assertEqual([row['purchaseId'] for row in rows], [new, included])
        report = {row['id']: row['actualCashbackKopecks'] for row in client.get('/api/me/stats').json()['purchases']}
        self.assertIsNone(report[estimate_only])
        self.assertEqual(report[new], 8_000)
        self.assertEqual(client.put(endpoint, json={**draft, 'includedPurchaseIds': [other_purchase]}).status_code, 409)
        with TestClient(app) as stranger:
            self.assertEqual(stranger.post('/api/auth/register', json={**credentials, 'login': 'stranger'}).status_code, 201)
            self.assertEqual(stranger.get(endpoint).status_code, 404)
            self.assertEqual(stranger.put(f'/api/me/purchases/{new}/cashback', json={'amountKopecks': 1}).status_code, 404)

        saved = client.put(endpoint, json=draft).json()
        self.assertEqual((saved['deductedKopecks'], saved['remainingKopecks']), (8_000, 22_000))
        self.assertEqual(client.put(endpoint, json=draft).json(), saved)
        matches = client.post('/api/recommendations', json={**purchase, 'scope': 'mine'}).json()['allMatches']
        self.assertEqual(next(row['cashbackKopecks'] for row in matches if row['cardId'] == first), 22_000)
        self.assertEqual(client.put(f'/api/me/cards/{other}/monthly', json={
            'limitKopecks': 50_000, 'usedKopecks': 0}).status_code, 200)
        plan = client.post('/api/me/purchase-plan', json={'purchases': [purchase] * 2}).json()
        self.assertEqual(plan['optimized']['totalKopecks'], 72_000)
        self.assertEqual(client.get(f'/api/me/cards/{first}/monthly').json()['remainingKopecks'], 22_000)

        with TestClient(create_app(db)) as reopened:
            self.assertEqual(reopened.post('/api/auth/login', json=credentials).status_code, 200)
            self.assertEqual(reopened.get(endpoint).json(), saved)
        clock.now.return_value = datetime(2026, 11, 22, 12, tzinfo=UTC)
        next_draft = {**draft, 'bankRemainingKopecks': 22_000, 'includedPurchaseIds': [included, new]}
        again = client.put(endpoint, json=next_draft).json()
        self.assertEqual((again['deductedKopecks'], again['remainingKopecks']), (0, 22_000))
        self.assertNotEqual(again['reconciledAt'], saved['reconciledAt'])
        self.assertEqual(set_actual(estimate_only, 25_000).status_code, 204)
        self.assertEqual(client.get(endpoint).json()['remainingKopecks'], 0)
        self.assertEqual(set_actual(estimate_only, None).status_code, 204)
        self.assertEqual(client.get(endpoint).json()['remainingKopecks'], 22_000)
        self.assertEqual(client.put(endpoint, json={**next_draft, 'bankRemainingKopecks': 0}).json()['remainingKopecks'], 0)

        clock.now.return_value = datetime(2026, 12, 1, 0, tzinfo=UTC)
        balance = client.get(endpoint).json()
        self.assertEqual(balance['accruals'], [])
        self.assertIsNone(balance['remainingKopecks'])
        self.assertEqual(client.put(endpoint, json=next_draft).status_code, 409)

    def test_reconciliation_distinguishes_foreign_purchase_from_unavailable_owned_mark(self):
        directory = self.enterContext(TemporaryDirectory())
        app = create_app(Path(directory) / 'wallet.sqlite3')
        owner = self.enterContext(TestClient(app))
        other = self.enterContext(TestClient(app))

        def setup(client, login):
            self.assertEqual(client.post('/api/auth/register', json={
                'login': login, 'password': 'test-only-password',
            }).status_code, 201)
            card = client.post('/api/me/manual-cards', json={'name': login, 'rules': [
                {'categoryId': 'supermarkets', 'rateBps': 1000},
            ]})
            self.assertEqual(card.status_code, 201, card.text)
            card_id = card.json()['cardId']
            purchase = client.post('/api/me/purchases', json={
                'categoryId': 'supermarkets', 'amountKopecks': 250_000, 'chosenCardId': card_id,
            })
            self.assertEqual(purchase.status_code, 201, purchase.text)
            return card_id, purchase.json()['id']

        card, estimate = setup(owner, 'balance_owner')
        _, foreign = setup(other, 'balance_other')
        self.assertEqual(other.put(f'/api/me/purchases/{foreign}/cashback', json={
            'amountKopecks': 8_000,
        }).status_code, 204)
        endpoint = f'/api/me/cards/{card}/cashback-reconciliation'
        before = owner.get(endpoint)
        self.assertEqual(before.status_code, 200, before.text)
        draft = dict(month=before.json()['month'], bankRemainingKopecks=30_000)
        for id_, expected in ((estimate, 409), (foreign, 404), (2**63 - 1, 404)):
            with self.subTest(purchase=id_):
                response = owner.put(endpoint, json={**draft, 'includedPurchaseIds': [id_]})
                self.assertEqual(response.status_code, expected, response.text)
                self.assertEqual(owner.get(endpoint).json(), before.json())

    def test_replacing_marks_does_not_keep_a_hidden_old_inclusion(self):
        directory = self.enterContext(TemporaryDirectory())
        clock = self.enterContext(patch('advisor.datetime'))
        clock.now.return_value = datetime(2026, 11, 21, 12, tzinfo=UTC)
        client = self.enterContext(TestClient(create_app(Path(directory) / 'wallet.sqlite3')))
        self.assertEqual(client.post('/api/auth/register', json={
            'login': 'balance_marks', 'password': 'test-only-password',
        }).status_code, 201)
        card = client.post('/api/me/manual-cards', json={'name': 'Карта', 'rules': [
            {'categoryId': 'supermarkets', 'rateBps': 1000},
        ]})
        self.assertEqual(card.status_code, 201, card.text)
        card_id = card.json()['cardId']
        purchase = client.post('/api/me/purchases', json={
            'categoryId': 'supermarkets', 'amountKopecks': 250_000, 'chosenCardId': card_id,
        })
        self.assertEqual(purchase.status_code, 201, purchase.text)
        id_ = purchase.json()['id']
        actual = f'/api/me/purchases/{id_}/cashback'
        endpoint = f'/api/me/cards/{card_id}/cashback-reconciliation'
        draft = dict(month='2026-11', bankRemainingKopecks=30_000)
        self.assertEqual(client.put(actual, json={'amountKopecks': 5_000}).status_code, 204)
        saved = client.put(endpoint, json={**draft, 'includedPurchaseIds': [id_]})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(client.put(actual, json={'amountKopecks': None}).status_code, 204)
        clock.now.return_value = datetime(2026, 11, 22, 12, tzinfo=UTC)
        stale = client.put(endpoint, json={**draft, 'includedPurchaseIds': [id_]})
        self.assertEqual(stale.status_code, 409, stale.text)
        refreshed = client.put(endpoint, json={**draft, 'includedPurchaseIds': []})
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertEqual(client.put(actual, json={'amountKopecks': 5_000}).status_code, 204)
        current = client.get(endpoint).json()
        self.assertEqual(current['remainingKopecks'], 25_000)
        self.assertFalse(current['accruals'][0]['includedInBankBalance'])
        self.assertNotEqual(refreshed.json()['reconciledAt'], saved.json()['reconciledAt'])
        clock.now.return_value = datetime(2026, 11, 23, 12, tzinfo=UTC)
        self.assertEqual(client.put(endpoint, json={**draft, 'includedPurchaseIds': []}).json(), current)
