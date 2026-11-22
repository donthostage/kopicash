"""Regression coverage for the current card/category limits API."""
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from advisor import create_app


class CashbackLimitsAPI(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.app = create_app(Path(directory) / 'limits.sqlite3')
        clock = self.enterContext(patch('advisor.datetime'))
        clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
        self.client = self.enterContext(TestClient(self.app))
        self.register(self.client, 'limit_owner')
        response = self.client.post('/api/me/manual-cards', json={
            'name': 'Личная карта', 'rules': [{'categoryId': 'cafe', 'rateBps': 500}],
        })
        self.assertEqual(response.status_code, 201, response.text)
        self.endpoint = f"/api/me/cards/{response.json()['cardId']}/cashback-limits"
        self.body = {
            'month': '2026-11', 'card': {'limitKopecks': 30_000, 'usedKopecks': 0},
            'categories': [{'categoryId': 'cafe', 'limitKopecks': 10_000, 'usedKopecks': 3_000}],
        }

    def register(self, client, login):
        response = client.post('/api/auth/register', json={'login': login, 'password': 'test-only-password'})
        self.assertEqual(response.status_code, 201, response.text)

    def read(self):
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def save(self):
        response = self.client.put(self.endpoint, json=self.body)
        self.assertEqual(response.status_code, 200, response.text)

    def test_explicit_zero_survives_readback(self):
        self.assertIsNone(self.read()['card']['usedKopecks'])
        self.save()
        saved = self.read()
        self.assertEqual(saved['card']['usedKopecks'], 0)
        self.assertEqual(saved['card']['remainingKopecks'], 30_000)
        self.assertEqual(saved['categories'][0]['remainingKopecks'], 7_000)

    def test_invalid_category_does_not_partially_replace_card_limit(self):
        self.save()
        before = self.read()
        invalid = dict(self.body, card={'limitKopecks': 1, 'usedKopecks': 0},
                       categories=[*self.body['categories'], {'categoryId': 'missing',
                                   'limitKopecks': 100, 'usedKopecks': 0}])
        response = self.client.put(self.endpoint, json=invalid)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.read(), before)

    def test_received_cannot_exceed_card_or_category_limit(self):
        self.save()
        before = self.read()
        excessive = {'limitKopecks': 10_050, 'usedKopecks': 10_100}
        for body in (dict(self.body, card=excessive),
                     dict(self.body, categories=[dict(excessive, categoryId='cafe')])):
            response = self.client.put(self.endpoint, json=body)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(self.read(), before)

    def test_other_account_cannot_overwrite_saved_limits(self):
        self.save()
        before = self.read()
        with TestClient(self.app) as other:
            self.register(other, 'different_owner')
            response = other.put(self.endpoint, json=dict(self.body, categories=[]))
            self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(self.read(), before)
