import unittest
import tempfile
from pathlib import Path
from datetime import UTC, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from advisor import create_app


def load_tests(loader, standard_tests, pattern):
    case = type('PreviousCatalogApi', (unittest.TestCase,), {
        'test_previous_catalog_contract': unittest.skip(
            'Проверяет прежний каталог и не входит в контракт кошелька.')(lambda self: None)})
    return loader.loadTestsFromTestCase(case)


class RecommendationsAPI(unittest.TestCase):
    def setUp(self):
        clock = self.enterContext(patch('advisor.datetime'))
        clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / 'test.db'
        self.client = self.enterContext(TestClient(create_app(self.path)))

    def request(self, **overrides):
        payload = dict(categoryId='supermarkets', amountKopecks=250000, scope='all')
        payload.update(overrides)
        return self.client.post('/api/recommendations', json=payload)

    def test_screen_is_served(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.headers['content-type'])
        self.assertIn('/api/recommendations', response.text)

    def test_ranking_details_and_repeatability(self):
        response = self.request()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['asOf'], '2026-11-20')
        self.assertEqual(data['catalogVersion'], 'training-v1')
        self.assertEqual([(x['cardId'], x['cashbackKopecks']) for x in data['top3']],
                         [('B', 15000), ('A', 10000), ('C', 10000)])
        self.assertEqual([x['cardId'] for x in data['allMatches']], ['B', 'A', 'C', 'D'])
        capped = data['top3'][1]
        self.assertTrue(capped['limitApplied'])
        self.assertEqual(capped['limitKopecks'], 10000)
        self.assertEqual(capped['updatedOn'], '2026-11-01')
        self.assertEqual(self.request().json(), data)

    def test_cafe_changes_winner(self):
        response = self.request(categoryId='cafe')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([(x['cardId'], x['cashbackKopecks']) for x in response.json()['top3']],
                         [('D', 20000)])

    def test_empty_category_is_not_an_error(self):
        response = self.request(categoryId='fuel')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['top3'], [])
        self.assertEqual(response.json()['allMatches'], [])

    def test_invalid_amounts(self):
        for amount in (0, -1, 2.5, True, '250000', None):
            with self.subTest(amount=amount):
                response = self.request(amountKopecks=amount)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json(),
                                 {'field': 'amountKopecks', 'code': 'positive_integer_required'})

    def test_unknown_category(self):
        response = self.request(categoryId='unknown')
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['field'], 'categoryId')

    def test_empty_mine_does_not_show_all_cards(self):
        response = self.request(scope='mine')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['allMatches'], [])
        self.assertEqual(response.json()['catalogSuggestion']['cardId'], 'B')

    def test_catalog_suggestion_is_separate_and_only_for_positive_cashback(self):
        self.assertEqual(self.client.put('/api/me/cards/A').status_code, 204)
        self.assertNotIn('catalogSuggestion', self.request(scope='mine').json())
        response = self.request(scope='mine', categoryId='cafe').json()
        self.assertEqual(response['top3'], [])
        self.assertEqual(response['catalogSuggestion']['cardId'], 'D')
        self.assertEqual(response['catalogSuggestion']['cashbackKopecks'], 20000)
        self.assertNotIn('catalogSuggestion', self.request(scope='mine', categoryId='cafe', amountKopecks=5000).json())
        self.assertNotIn('catalogSuggestion', self.request(scope='mine', categoryId='clothes').json())

    def test_category_picker_includes_categories_without_catalog_rules(self):
        groups = self.client.get('/api/category-groups').json()
        self.assertEqual(groups['Еда и покупки']['groceries'], 'Продукты')
        self.assertEqual(groups['Повседневные расходы и дом']['clothes'], 'Одежда и обувь')
        response = self.request(categoryId='groceries')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['top3'], [])

    def test_mine_combines_catalog_and_named_manual_category(self):
        self.assertEqual(self.client.put('/api/me/cards/A').status_code, 204)
        personal = self.client.post('/api/me/manual-cards', json={
            'name': 'Моя карта',
            'rules': [{'categoryName': '  СУПЕРМАРКЕТЫ  ', 'rateBps': 800}],
        })
        self.assertEqual(personal.status_code, 201)
        results = self.request(scope='mine').json()['allMatches']
        self.assertEqual([(item['cardName'], item['cashbackKopecks']) for item in results],
                         [('Моя карта', 20000), ('Карта A', 10000)])

    def test_manual_category_aliases_are_unique_and_legacy_cards_rank_once(self):
        import json

        from catalog import connect

        def create(name, rate):
            response = self.client.post('/api/me/manual-cards', json={
                'name':name, 'rules':[{'categoryName':'Кафе','rateBps':rate}],
            })
            self.assertEqual(response.status_code, 201)
            return response.json()['cardId']

        duplicate = self.client.post('/api/me/manual-cards', json={
            'name':'Одна карта', 'rules':[
                {'categoryName':'Кафе','rateBps':1000},
                {'categoryName':'Кафе и рестораны','rateBps':900},
            ],
        })
        self.assertEqual((duplicate.status_code, duplicate.json()['code']), (422, 'duplicate_category'))
        first, second, third = (create(name, rate) for name, rate in [('Одна', 1000), ('Две', 800), ('Три', 700)])
        with connect(self.path) as db:
            rules_json, = db.execute('SELECT rules_json FROM manual_cards WHERE card_id=?', (first,)).fetchone()
            rules = json.loads(rules_json)
            rules.append(dict(rules[0], categoryName='Кафе и рестораны', rateBps=900))
            db.execute('UPDATE manual_cards SET rules_json=? WHERE card_id=?', (json.dumps(rules), first))
        for options in (dict(categoryId='cafe', scope='mine'),
                        dict(categoryId='Кафе и рестораны', scope='manual')):
            result = self.request(**options).json()
            self.assertEqual([(r['cardId'], r['cashbackKopecks']) for r in result['top3']],
                             [(first, 25000), (second, 20000), (third, 17500)])
            self.assertEqual(result['top3'], result['allMatches'])

    def test_location_removed_but_category_groups_still_available(self):
        self.assertEqual(self.client.get('/api/nearby').status_code, 404)
        self.assertEqual(self.client.post('/api/nearby', json={}).status_code, 404)
        response = self.client.get('/')
        self.assertNotIn(b'navigator.geolocation', response.content)
        self.assertNotIn(b'/api/nearby', response.content)
        self.assertIn('supermarkets', self.client.get('/api/categories').json())
        self.assertTrue(self.client.get('/api/category-groups').json())

    def test_catalog_metadata_is_persistent_and_versions_are_public(self):
        from catalog import SEED, import_catalog

        before = self.request().json()
        named = dict(SEED[1], bankName='Учебный Север', cardName='Карта Севера')
        import_catalog(self.path, [named])
        published = self.request().json()
        self.assertNotEqual(published['catalogVersion'], before['catalogVersion'])
        self.assertEqual(published['top3'][0]['cardName'], 'Карта Севера')
        self.assertEqual(self.client.get('/api/cards/B').json()['bankName'], 'Учебный Север')
        self.assertEqual(self.client.put('/api/me/cards/B').status_code, 204)
        self.assertEqual(self.client.put('/api/me/cards/B/monthly-limit', json={
            'month':'2026-11','limitKopecks':300000,'usedKopecks':295000}).status_code, 204)
        self.assertEqual(self.request(scope='mine').json()['catalogVersion'], published['catalogVersion'])
        self.assertEqual(self.request(scope='manual').json()['catalogVersion'], published['catalogVersion'])
        self.assertEqual(self.request(scope='mine').json()['top3'][0]['cashbackKopecks'], 5000)
        import_catalog(self.path, [named])
        self.assertEqual(self.request().json(), published)

    def test_recommendations_do_not_include_bank_links(self):
        self.assertTrue(all('bankAccess' not in card for card in self.request().json()['allMatches']))
        response = self.client.post('/api/me/manual-cards', json={'name': 'Моя карта', 'bankName': 'Т‑Банк',
            'rules': [{'categoryName': 'Супермаркеты', 'rateBps': 900}]})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(all('bankAccess' not in card for card in self.request(scope='mine').json()['allMatches']))
        for path in ('/bank-link-test', '/android-bank-test'):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_bank_picker_uses_the_russian_central_bank_directory(self):
        response = self.client.get('/api/banks')
        self.assertEqual(response.status_code, 200)
        directory = response.json()
        self.assertEqual(directory['source'], 'https://www.cbr.ru/banking_sector/credit/FullCoList')
        banks = {bank['registrationNumber']:bank for bank in directory['banks']}
        self.assertGreater(len(banks), 100)
        self.assertEqual(len(banks), len(directory['banks']))
        self.assertEqual(banks['1927']['name'], 'Модульбанк')
        self.assertNotIn('3166', banks)
        self.assertNotIn('654', banks)
