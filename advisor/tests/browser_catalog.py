"""Fast, independent browser check of the mandatory catalog flow."""
from playwright.sync_api import expect, sync_playwright

from browser_mvp import category, isolated_server, rank


def check(chromium=None):
    with isolated_server() as base, sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=chromium)
        try:
            page = browser.new_page(base_url=base, viewport={'width': 390, 'height': 844},
                                    service_workers='block', reduced_motion='reduce')
            page.set_default_timeout(6500)
            page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base + '/')
                       else route.abort())
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            guest = page.request.post('/api/auth/guest', data={})
            assert guest.ok, guest.text()
            page.goto('/#buy')
            buy = page.locator('#buyPanel')
            expect(buy).to_be_visible()
            category(page, 'Супермаркеты')
            page.locator('#buyAmount').fill('2 500')
            rank(page, [('Карта B', '150'), ('Карта A', '100'), ('Карта C', '100')])
            card = buy.get_by_role('article').nth(1)
            card.get_by_text('Условия', exact=True).click()
            expect(card.locator('details[open]')).to_contain_text('Актуальность')
            expect(card.locator('details[open]')).to_contain_text('применён')
            category(page, 'Кафе')
            rank(page, [('Карта D', '200')])
            assert not errors, errors
        finally:
            browser.close()
