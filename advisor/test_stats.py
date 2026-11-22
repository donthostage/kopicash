import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from advisor import month_totals
from catalog import connect, initialize
from test_cashback import API


class MonthTotals(unittest.TestCase):
    def test_recorded_choices_against_best_and_usual(self):
        totals = month_totals([
            dict(chosenKopecks=10000, recommendedKopecks=15000, usualKopecks=8000),
            dict(chosenKopecks=5000, recommendedKopecks=5000, usualKopecks=2000),
        ])
        self.assertEqual(totals['count'], 2)
        self.assertEqual(totals['calculatedKopecks'], 15000)
        self.assertEqual(totals['recommendedKopecks'], 20000)
        self.assertEqual(totals['missedKopecks'], 5000)
        self.assertEqual(totals['versusUsualKopecks'], 5000)

    def test_without_usual_card_the_gap_stays_empty(self):
        totals = month_totals([
            dict(chosenKopecks=10000, recommendedKopecks=10000, usualKopecks=None),
        ])
        self.assertIsNone(totals['usualKopecks'])
        self.assertIsNone(totals['versusUsualKopecks'])


class StatsMonthQuery(unittest.TestCase):
    def test_month_comment_preserves_selected_period_without_model(self):
        from advisor import create_app

        with tempfile.TemporaryDirectory() as directory, patch('advisor.vision_key', return_value=None):
            path = Path(directory) / 'report.sqlite3'
            initialize(path)
            with API(create_app(path)) as client:
                self.assertEqual(client.post('/api/auth/register', json={
                    'login': 'month_report', 'password': 'test-only-long-password'
                }).status_code, 201)
                report = client.post('/api/me/stats/comment?month=2026-10', json={})
                self.assertEqual(report.status_code, 200, report.text)
                self.assertIn('Начисления ещё не указаны', report.json()['comment'])
                self.assertEqual(client.post('/api/me/stats/comment?month=bad', json={}).status_code, 422)

    def test_month_defaults_to_current_utc_and_filters_by_query(self):
        with tempfile.TemporaryDirectory() as folder, patch('advisor.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
            path = Path(folder) / 'advisor.sqlite3'
            initialize(path)
            from advisor import create_app
            app = create_app(path)
            with API(app) as client, API(app) as stranger:
                self.assertEqual(stranger.get('/api/me/stats').status_code, 401)
                self.assertEqual(client.post('/api/auth/register', json={
                    'login': 'stats_month', 'password': 'test-only-long-password',
                }).status_code, 201)
                card = client.post('/api/me/manual-cards', json={
                    'name': 'Карта',
                    'rules': [{'categoryId': 'cafe', 'rateBps': 500, 'validFrom': '2026-01-01'}],
                }).json()['cardId']
                purchase = {'chosenCardId': card, 'categoryId': 'cafe', 'amountKopecks': 10000}
                self.assertEqual(client.post('/api/me/purchases', json={
                    **purchase, 'requestId': 'stats-month-nov-0001',
                }).status_code, 201)
                current = client.get('/api/me/stats').json()
                self.assertEqual(current['month'], '2026-11')
                self.assertEqual(current['count'], 1)
                november = client.get('/api/me/stats?month=2026-11').json()
                self.assertEqual(november['month'], '2026-11')
                self.assertEqual(november['count'], 1)
                october = client.get('/api/me/stats?month=2026-10').json()
                self.assertEqual(october['month'], '2026-10')
                self.assertEqual(october['count'], 0)
                self.assertEqual(client.get('/api/me/stats?month=2026-13').status_code, 422)
                self.assertEqual(client.get('/api/me/stats?month=bad').status_code, 422)
                self.assertEqual(stranger.post('/api/auth/register', json={
                    'login': 'stats_other', 'password': 'test-only-long-password',
                }).status_code, 201)
                other = stranger.get('/api/me/stats?month=2026-11').json()
                self.assertEqual(other['count'], 0)

    def test_release_preserves_legacy_marks_and_does_not_restore_deleted_marks(self):
        from advisor import create_app

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'wallet.sqlite3'
            initialize(path)
            with API(create_app(path)) as client:
                self.assertEqual(client.post('/api/auth/register', json={
                    'login': 'legacy_actual', 'password': 'test-password',
                }).status_code, 201)
                card = client.post('/api/me/manual-cards', json={
                    'name': 'Карта', 'rules': [dict(categoryId='cafe', rateBps=500)],
                }).json()['cardId']
                purchase = client.post('/api/me/purchases', json={
                    'categoryId': 'cafe', 'chosenCardId': card, 'amountKopecks': 10000,
                }).json()['id']
                with connect(path) as db:
                    db.execute('INSERT INTO purchase_cashback VALUES (?, ?)', (purchase, 4800))
                initialize(path)
                self.assertEqual(client.get('/api/me/stats').json()['actualCashbackKopecks'], 4800)
                self.assertEqual(client.put(f'/api/me/purchases/{purchase}/cashback',
                                            json={'amountKopecks': None}).status_code, 204)
                initialize(path)
                self.assertIsNone(client.get('/api/me/stats').json()['actualCashbackKopecks'])


    def test_actual_cashback_on_stats_and_purchase_endpoint(self):
        with tempfile.TemporaryDirectory() as folder, patch('advisor.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
            path = Path(folder) / 'advisor.sqlite3'
            initialize(path)
            from advisor import create_app
            app = create_app(path)
            with API(app) as client, API(app) as other:
                self.assertEqual(client.post('/api/auth/register', json={
                    'login': 'cashback_ui', 'password': 'test-only-long-password',
                }).status_code, 201)
                self.assertEqual(other.post('/api/auth/register', json={
                    'login': 'cashback_other', 'password': 'test-only-long-password',
                }).status_code, 201)
                card = client.post('/api/me/manual-cards', json={
                    'name': 'Карта',
                    'rules': [{'categoryId': 'cafe', 'rateBps': 500}],
                }).json()['cardId']
                one = client.post('/api/me/purchases', json={
                    'chosenCardId': card, 'categoryId': 'cafe', 'amountKopecks': 10000,
                    'requestId': 'actual-cashback-one-01',
                }).json()['id']
                two = client.post('/api/me/purchases', json={
                    'chosenCardId': card, 'categoryId': 'cafe', 'amountKopecks': 20000,
                    'requestId': 'actual-cashback-two-02',
                }).json()['id']
                self.assertEqual(other.put(f'/api/me/purchases/{one}/cashback',
                                           json={'amountKopecks': 100}).status_code, 404)
                self.assertEqual(client.put(f'/api/me/purchases/{one}/cashback',
                                            json={'amountKopecks': 0}).status_code, 204)
                self.assertEqual(client.put(f'/api/me/purchases/{two}/cashback',
                                            json={'amountKopecks': 15000}).status_code, 204)
                report = client.get('/api/me/stats').json()
                self.assertEqual((report['actualCashbackKopecks'], report['actualCashbackCount']), (15000, 2))
                by_id = {row['id']: row['actualCashbackKopecks'] for row in report['purchases']}
                self.assertEqual(by_id, {one: 0, two: 15000})
                self.assertEqual(client.put(f'/api/me/purchases/{two}/cashback',
                                            json={'amountKopecks': None}).status_code, 204)
                report = client.get('/api/me/stats').json()
                self.assertEqual((report['actualCashbackKopecks'], report['actualCashbackCount']), (0, 1))
                by_id = {row['id']: row['actualCashbackKopecks'] for row in report['purchases']}
                self.assertEqual(by_id, {one: 0, two: None})

    def test_actual_summary_uses_only_confirmed_purchases_and_keeps_forecasts(self):
        from advisor import create_app

        with tempfile.TemporaryDirectory() as folder, patch('advisor.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 21, tzinfo=UTC)
            path = Path(folder) / 'wallet.sqlite3'
            initialize(path)
            app = create_app(path)
            with API(app) as client, API(app) as other:
                for login, actor in [('summary_owner', client), ('summary_other', other)]:
                    self.assertEqual(actor.post('/api/auth/register', json={
                        'login': login, 'password': 'test-password',
                    }).status_code, 201)

                def card(name, rate, actor=client):
                    response = actor.post('/api/me/manual-cards', json={
                        'name': name, 'rules': [dict(categoryId='cafe', rateBps=rate)],
                    })
                    self.assertEqual(response.status_code, 201, response.text)
                    return response.json()['cardId']

                def purchase(card_id, actor=client):
                    response = actor.post('/api/me/purchases', json={
                        'categoryId': 'cafe', 'amountKopecks': 100_000, 'chosenCardId': card_id,
                    })
                    self.assertEqual(response.status_code, 201, response.text)
                    return response.json()['id']

                def confirm(id_, amount, actor=client):
                    response = actor.put(f'/api/me/purchases/{id_}/cashback', json={'amountKopecks': amount})
                    self.assertEqual(response.status_code, 204, response.text)

                first, second = card('Карта А', 500), card('Карта Б', 1000)
                one, two, three = purchase(first), purchase(first), purchase(second)
                confirm(purchase(card('Другая карта', 1000, other), other), 999_999, other)
                clock.now.return_value = datetime(2026, 12, 1, tzinfo=UTC)
                report = lambda: client.get('/api/me/stats?month=2026-11').json()
                actual = lambda block: (block['actualCashbackKopecks'], block['actualCashbackCount'])

                self.assertEqual(actual(report()), (None, 0))
                confirm(one, 0)
                self.assertEqual(actual(report()), (0, 1))
                confirm(two, 4_800)
                result = report()
                self.assertEqual(actual(result), (4_800, 2))
                self.assertEqual((result['count'], result['calculatedKopecks'], result['missedKopecks']),
                                 (3, 20_000, 10_000))
                cards = {row['cardId']: row for row in result['cards']}
                self.assertEqual(actual(cards[first]), (4_800, 2))
                self.assertEqual(actual(cards[second]), (None, 0))
                self.assertEqual((cards[first]['cashbackKopecks'], cards[first]['missedKopecks']), (10_000, 10_000))
                self.assertIsNone(next(row for row in result['purchases'] if row['id'] == three)['actualCashbackKopecks'])
                self.assertEqual(actual(client.get('/api/me/stats').json()), (None, 0))

                confirm(two, 5_500)
                self.assertEqual(actual(report()), (5_500, 2))
                confirm(two, None)
                self.assertEqual(actual(report()), (0, 1))
                confirm(one, None)
                self.assertEqual(actual(report()), (None, 0))
                self.assertEqual(report()['missedKopecks'], 10_000)
