"""Боевой прогон: регистрация, карта через шторку, скрин из галереи в живой сервис.

Запуск против уже поднятого стенда:
    python tests/browser_live.py http://127.0.0.1:18745
"""
import argparse
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOT = ROOT / 'tests' / 'fixtures' / 'cashback-gallery.png'


def button(root, name):
    return root.get_by_role('button', name=name, exact=isinstance(name, str))


def run(base, chromium=None):
    if not SHOT.is_file():
        raise SystemExit(f'Нет снимка галереи: {SHOT}')
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=chromium)
        try:
            page = browser.new_page(viewport={'width': 390, 'height': 844}, locale='ru-RU')
            page.set_default_timeout(15000)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base)
            page.frame_locator('#welcomeScreen').locator('#start').click()
            auth = page.locator('#authForm')
            login, password = 'live_' + uuid4().hex[:10], uuid4().hex
            auth.get_by_label('Логин').fill(login)
            auth.get_by_label('Пароль', exact=True).fill(password)
            button(auth, 'Создать кошелёк').click()
            expect(page.locator('#openBuy')).to_be_visible()
            expect(page.locator('#openBuy')).to_have_accessible_name('Сравнить карты')

            page.locator('#openCards').click()
            cards = page.locator('#cardsPanel')
            add = page.locator('#addDialog')
            button(cards, 'Добавить карту').click()
            button(add, 'Выбрать банк').click()
            add.locator('#bankSearch').fill('ВТБ')
            add.locator('#bankSuggestions').get_by_role('option', name='ВТБ', exact=True).click()
            button(add, 'Добавить карту').click()
            expect(add).to_be_hidden()
            expect(page.locator('#carouselDetails')).to_contain_text('ВТБ')
            cards.locator('#addCashbackBtn').click()
            review = page.locator('#catalogDialog')
            expect(review.locator('#cashbackShot')).to_be_visible()
            with page.expect_response(lambda response: response.url.endswith('/api/me/cashback-screenshot'),
                                      timeout=55_000) as recognition:
                review.locator('#cashbackShot').set_input_files(SHOT)
                review.locator('#confirmCard').click()
            assert recognition.value.status == 201, recognition.value.text()
            expect(review.locator('#reviewForm')).to_be_visible()
            rows = page.locator('#reviewRows .review-row')
            expect(rows).to_have_count(3)
            labels = rows.locator('[data-key=label]').evaluate_all('(els) => els.map(el => el.value)')
            rates = rows.locator('[data-key=rateBps]').evaluate_all('(els) => els.map(el => Number(el.value))')
            assert dict(zip(labels, rates, strict=True)) == {'Кафе': 5, 'Супермаркеты': 7, 'АЗС': 3}
            print('Черновик:', labels)
            month = page.locator('#reviewMonth')
            if not month.input_value():
                month.fill(page.evaluate("""() => new Date().toISOString().slice(0, 7)"""))
            for box in rows.locator('[data-key=include]').all():
                if not box.is_checked():
                    box.check()
            review.locator('#saveReview').click()
            expect(review).to_be_hidden(timeout=20000)
            page.reload()
            expect(cards).to_be_visible()
            expect(page.locator('#carouselDetails')).to_contain_text('ВТБ')
            for label in labels:
                expect(page.locator('#carouselCategories')).to_contain_text(label)
            assert not errors, errors
            print(f'Боевой прогон пройден: {login}, карта ВТБ, снимок из галереи сохранён.')
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url', nargs='?', default='http://127.0.0.1:18745')
    parser.add_argument('--chromium-executable')
    args = parser.parse_args()
    run(args.base_url.rstrip('/'), args.chromium_executable)
