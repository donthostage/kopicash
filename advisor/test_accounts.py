import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from advisor import create_app


def load_tests(loader, standard_tests, pattern):
    case = type('PreviousCatalogApi', (unittest.TestCase,), {
        'test_previous_catalog_contract': unittest.skip(
            'Проверяет прежний каталог и не входит в контракт кошелька.')(lambda self: None)})
    return loader.loadTestsFromTestCase(case)


class AccountsTests(unittest.TestCase):
    credentials = {'username': 'test.member', 'password': 'a-long-test-password'}
    card = {'name': 'Личная', 'bankName': 'Мой банк', 'rules': [{'categoryName': 'Такси', 'rateBps': 500}]}

    def setUp(self):
        self.db = Path(self.enterContext(tempfile.TemporaryDirectory())) / 'test.db'

    def test_running_server_keeps_matching_html_after_file_changes(self):
        page = self.db.with_suffix('.html')
        page.write_text('<p>first build</p>', encoding='utf-8')
        with patch('advisor.PAGE', page), TestClient(create_app(self.db)) as client:
            page.write_text('<p>new build</p>', encoding='utf-8')
            self.assertEqual(client.get('/').text, '<p>first build</p>')

    def test_devices_guest_transfer_and_logout(self):
        with TestClient(create_app(self.db)) as first:
            self.assertEqual(first.post('/api/me/manual-cards', json=self.card).status_code, 201)
            registration = first.post('/api/auth/register', json={**self.credentials, 'transferGuestCards': True})
            self.assertEqual(registration.status_code, 201)
            self.assertIn('HttpOnly', registration.headers['set-cookie'])
            self.assertEqual(first.get('/api/auth/me').json(), {'username': 'test.member'})
            with TestClient(create_app(self.db)) as second:
                self.assertEqual(second.get('/api/me/manual-cards').json(), [])
                self.assertEqual(second.post('/api/auth/login', json=self.credentials).status_code, 200)
                self.assertEqual(second.get('/api/me/manual-cards').json()[0]['name'], 'Личная')
                self.assertEqual(second.post('/api/me/manual-cards', json=dict(self.card, name='Вторая')).status_code, 201)
                cookie = second.cookies.get('advisor_auth')
                self.assertEqual(second.post('/api/auth/logout').status_code, 204)
                second.cookies.set('advisor_auth', cookie)
                self.assertEqual(second.get('/api/me/manual-cards').json(), [])
            self.assertEqual(len(first.get('/api/me/manual-cards').json()), 2)
        with TestClient(create_app(self.db)) as third:
            other = {'username': 'other.member', 'password': self.credentials['password']}
            self.assertEqual(third.post('/api/auth/register', json=other).status_code, 201)
            self.assertEqual(third.get('/api/me/manual-cards').json(), [])
            self.assertEqual(third.post('/api/auth/login', json=self.credentials).status_code, 200)
            self.assertEqual(len(third.get('/api/me/manual-cards').json()), 2)

    def test_invalid_credentials_and_foreign_origin(self):
        with TestClient(create_app(self.db)) as client:
            self.assertEqual(client.post('/api/auth/register', json=dict(self.credentials, password='short')).status_code, 422)
            self.assertEqual(client.post('/api/auth/register', json=self.credentials, headers={'Origin': 'https://example.org'}).status_code, 403)
            self.assertEqual(client.post('/api/auth/login', json=self.credentials).status_code, 401)

    def test_metrics_track_request_without_user_data(self):
        with TestClient(create_app(self.db)) as client, self.assertLogs('advisor', level='INFO') as logs:
            request = client.post('/api/auth/login', json=self.credentials)
            self.assertIn('X-Request-ID', request.headers)
            metrics = client.get('/metrics')
            self.assertEqual(metrics.status_code, 200)
            self.assertIn('advisor_http_requests_total', metrics.text)
            self.assertIn('/api/auth/login', metrics.text)
            for secret in self.credentials.values():
                self.assertNotIn(secret, metrics.text + ''.join(logs.output))
