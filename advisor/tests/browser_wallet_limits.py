"""Run with: python tests/browser_wallet_limits.py (requires Playwright Chromium)."""
import os
import unittest

from playwright.sync_api import expect, sync_playwright

from browser_mvp import isolated_server


class WalletLimitsBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = cls.enterClassContext(isolated_server())
        runtime = cls.enterClassContext(sync_playwright())
        cls.browser = runtime.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH'))
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        context = self.browser.new_context(base_url=self.base, viewport={'width': 390, 'height': 844},
                                           reduced_motion='reduce', service_workers='block')
        self.addCleanup(context.close)
        self.page = context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        response = self.page.request.post('/api/auth/guest', data={})
        self.assertTrue(response.ok, response.text())
        self.paths = []
        for name in ('Карта А', 'Карта Б'):
            response = self.page.request.post('/api/me/manual-cards', data={
                'name': name, 'rules': [{'categoryId': 'cafe', 'rateBps': 500}],
            })
            self.assertTrue(response.ok, response.text())
            self.paths.append(f"/api/me/cards/{response.json()['cardId']}/cashback-limits")
        self.page.goto('/#cards')
        expect(self.page.locator('#cardsPanel')).to_be_visible()
        self.limits = self.page.locator('#cardLimits')

    def open_limits(self):
        self.page.get_by_role('button', name='Настройки карты', exact=True).click()
        expect(self.page.get_by_role('dialog', name='Настройки карты')).to_be_visible()
        expect(self.page.locator('#deleteActiveBtn')).to_be_visible()
        form = self.limits.locator('form')
        expect(form).to_be_visible()
        return form.get_by_role('group', name='Вся карта')

    def test_adding_the_same_demo_card_creates_a_separate_copy(self):
        add = self.page.locator('#addDialog')
        for count in (3, 4):
            self.page.locator('#openCatalog').click()
            expect(add.locator('#bankSearch')).to_have_value('')
            expect(add.locator('#saveNewCard')).to_be_disabled()
            add.locator('#openCatalogSource').click()
            add.locator('#newBank').select_option('A')
            add.locator('#saveNewCard').click()
            expect(add).to_be_hidden()
            expect(self.page.locator('#carouselPosition')).to_contain_text(f'из {count}')
        owned = self.page.request.get('/api/me/manual-cards').json()
        generated = [card for card in owned if 'учебная' in card['name']]
        self.assertEqual(len(generated), 1)
        self.assertTrue(generated[0]['rules'])
        self.assertEqual(self.errors, [])

    def test_save_limits_and_reopen_after_reload(self):
        card = self.open_limits()
        card.get_by_label('Лимит, ₽', exact=True).fill('3000')
        card.get_by_label('Уже получено, ₽').fill('0')
        with self.page.expect_response(lambda r: r.url.endswith('/cashback-limits') and r.request.method == 'PUT') as saved:
            self.limits.get_by_role('button', name='Сохранить лимиты').click()
        self.assertTrue(saved.value.ok, saved.value.text())
        self.assertEqual(saved.value.json()['card']['limitKopecks'], 300_000)
        self.page.reload()
        card = self.open_limits()
        expect(card.get_by_label('Лимит, ₽', exact=True)).to_have_value('3000')
        expect(card.get_by_label('Уже получено, ₽')).to_have_value('0')
        self.assertEqual(self.errors, [])

    def test_invalid_limit_and_delete_without_reloading_wallet(self):
        card = self.open_limits()
        card.get_by_label('Лимит, ₽', exact=True).fill('100,50')
        received = card.get_by_label('Уже получено, ₽')
        received.fill('101')
        self.limits.get_by_role('button', name='Сохранить лимиты').click()
        expect(self.limits.locator('form [role=status]')).to_contain_text('не может быть больше лимита')
        expect(received).to_have_value('101')
        self.page.route('**/api/me/manual-cards', lambda route: route.abort())
        self.page.locator('#deleteActiveBtn').click()
        self.page.locator('#cancelDelete').click()
        expect(self.page.locator('#carouselPosition')).to_contain_text('из 2')
        self.page.get_by_role('button', name='Настройки карты', exact=True).click()
        self.page.locator('#deleteActiveBtn').click()
        self.page.locator('#confirmDelete').click()
        expect(self.page.locator('#deleteDialog')).to_be_hidden()
        expect(self.page.locator('#carouselTrack .carousel-card')).to_have_count(1)
        self.assertEqual(self.errors, [])

    def test_switching_cards_shows_each_cards_own_limit(self):
        for path, rubles in zip(self.paths, (1000, 2000), strict=True):
            current = self.page.request.get(path)
            self.assertTrue(current.ok, current.text())
            response = self.page.request.put(path, data={
                'month': current.json()['month'], 'categories': [],
                'card': {'limitKopecks': rubles * 100, 'usedKopecks': 0},
            })
            self.assertTrue(response.ok, response.text())
        self.page.reload()
        expect(self.page.locator('#cardsPanel')).to_be_visible()
        seen = set()
        for index in range(2):
            if index:
                self.page.keyboard.press('Escape')
                self.page.locator('#cardCarousel').press('ArrowRight')
                expect(self.limits.locator('form')).to_be_hidden()
            card = self.open_limits()
            name = self.page.locator('#cardSettingsBank').text_content()
            expected = {'Карта А': '1000', 'Карта Б': '2000'}[name]
            expect(card.get_by_label('Лимит, ₽', exact=True)).to_have_value(expected)
            seen.add(name)
        self.assertEqual(seen, {'Карта А', 'Карта Б'})
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
