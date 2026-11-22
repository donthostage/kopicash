"""Integration tests for the current public recommendation contract."""
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from advisor import create_app


class RecommendationsContract(unittest.TestCase):
    def setUp(self):
        path = Path(self.enterContext(tempfile.TemporaryDirectory())) / 'catalog.sqlite3'
        self.clock = self.enterContext(patch('advisor.datetime'))
        self.clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
        self.client = self.enterContext(TestClient(create_app(path)))

    def query(self, category='supermarkets', amount: object = 250_000):
        return self.client.post('/api/recommendations', json={
            'scope': 'all', 'categoryId': category, 'amountKopecks': amount,
        })

    def test_required_purchase_is_repeatable_and_explains_cap(self):
        response = self.query()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual([(row['cardId'], row['cashbackKopecks']) for row in result['allMatches']],
                         [('B', 15_000), ('A', 10_000), ('C', 10_000), ('D', 5_000)])
        self.assertEqual(result['top3'], result['allMatches'][:3])
        capped = result['top3'][1]
        self.assertEqual(capped['calculation']['beforeLimitsKopecks'], 25_000)
        self.assertEqual(capped['calculation']['afterCategoryLimitKopecks'], 10_000)
        self.assertEqual(capped['updatedOn'], '2026-11-01')
        self.assertEqual(self.query().json(), result)

    def test_switching_category_changes_winner(self):
        response = self.query('cafe')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([(row['cardId'], row['cashbackKopecks']) for row in response.json()['top3']],
                         [('D', 20_000)])

    def test_expired_offers_are_not_returned(self):
        self.clock.now.return_value = datetime(2027, 11, 1, tzinfo=UTC)
        response = self.query()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['allMatches'], [])

    def test_rejects_invalid_amounts(self):
        for amount in (0, -1, True, 2.5, '250000', None):
            with self.subTest(amount=amount):
                response = self.query(amount=amount)
                self.assertEqual(response.status_code, 422, response.text)
