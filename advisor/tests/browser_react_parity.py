"""Chromium acceptance against a local React origin backed by a disposable database."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
from urllib.parse import urlparse
from uuid import uuid4
from playwright.sync_api import expect, sync_playwright


def run(base, widths, built=False):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for width in widths:
            context = browser.new_context(base_url=base, viewport={'width': width, 'height': 850}, service_workers='block', reduced_motion='reduce')
            page = context.new_page()
            page.set_default_timeout(5000)
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base + '/') else route.abort())
            response = page.goto('/')
            assert response and response.ok
            if built:
                served = response.text()
                dist = Path(__file__).resolve().parents[1] / 'frontend/dist'
                assert response.body() == (dist / 'index.html').read_bytes()
                assets = re.findall(r'"(/assets/[^\"]+\.(?:js|css))"', served)
                assert len(assets) == 2 and '/src/main.tsx' not in served
                for asset in assets:
                    result = page.request.get(asset, headers={'Cache-Control': 'no-cache'})
                    assert result.ok and result.body() == (dist / asset.lstrip('/')).read_bytes()
            assert page.request.get('/static/wallet-shell.css').ok
            page.get_by_role('button', name='Начать', exact=True).click()
            page.get_by_role('button', name='Войти как гость').click()
            expect(page.locator('.topbar')).to_be_visible()
            assert context.cookies(base) and page.request.get('/api/auth/me').json()['authenticated']
            page.reload()
            expect(page.locator('.topbar')).to_be_visible()
            page.locator('nav').get_by_role('button', name='Кэшбэк').click()
            summary = page.locator('#homeMonthCashback')
            expect(summary.get_by_role('button', name='Рассчитать покупку')).to_be_visible()
            expect(summary.get_by_text('Покупки за месяц')).to_have_count(0)
            summary.get_by_role('button', name='Рассчитать покупку').click()
            expect(page).to_have_url(re.compile('#buy$'))
            page.locator('nav').get_by_role('button', name='Мои карты').click()
            for bank in ('Сбер', 'Альфа'):
                page.get_by_role('button', name=re.compile('Добавить карту')).click()
                dialog = page.get_by_role('dialog')
                dialog.get_by_role('combobox').fill(bank)
                dialog.get_by_role('option', name=re.compile(bank)).first.click()
                dialog.get_by_role('button', name='Добавить карту', exact=True).click()
                toast = page.get_by_role('status').filter(has_text='Карта добавлена')
                expect(toast).to_be_visible()
                box, nav = toast.bounding_box(), page.locator('nav').bounding_box()
                assert box and nav and box['width'] < width * .85 and box['y'] + box['height'] <= nav['y'], (box, nav)
            expect(toast).to_be_hidden()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.evaluate('window.parityMarker = true')
            action = page.get_by_role('button', name='Добавить категории', exact=True)
            expect(action.locator('svg')).to_have_count(0)
            action.click()
            page.get_by_role('button', name='Ввести вручную').click()
            page.locator('[data-key=label]').fill('Кафе')
            page.locator('[data-key=categoryId]').fill('cafe')
            page.locator('[data-key=rateBps]').fill('5')
            page.locator('#saveReview').click()
            details = page.locator('.kw-details')
            expect(details.get_by_role('button', name='Настройки карты')).to_be_visible()
            expect(details.get_by_text('Кафе')).to_be_visible()

            page.locator('#brandHome').click()
            page.locator('#openBuy').click()
            page.locator('#scopeMine').click()
            page.locator('#categoryGrid [data-id=cafe]').click()
            page.locator('#buyAmount').fill('1000')
            expect(page.locator('#buyResults')).to_contain_text(re.compile(r'50\s*₽'))
            page.locator('#paidWith').select_option(index=1)
            page.get_by_role('button', name='Записать покупку').click()
            expect(page.get_by_text(re.compile('Покупка записана'))).to_be_visible()
            page.locator('#openCashback').click()
            summary.get_by_role('button', name='Покупки за месяц').click()
            month = datetime.now(timezone.utc).strftime('%Y-%m')
            expect(page.locator('#historyMonth')).to_have_value(month)
            expect(page.locator('#historyMonth')).to_be_visible()
            page.locator('#openCashback').click()
            page.locator('#openPlan').click()
            expect(page.locator('#spendingSource')).to_have_value('history')
            page.locator('#spendingMonth').fill(month)
            with page.expect_response(lambda res: res.url.endswith('/api/me/cashback-plan')) as forecast:
                page.locator('#calculatePlan').click()
            payload = forecast.value.request.post_data_json
            assert forecast.value.ok and payload and payload['spendingMonth'] == month
            expect(page.locator('#planResult')).to_contain_text('История покупок')
            page.locator('#closePlan').click()
            page.locator('#openCards').click()
            page.get_by_role('button', name='Следующая карта').click()
            expect(details.get_by_role('heading')).to_have_text('Альфа-Банк')
            details.get_by_role('button', name='Настройки карты').click()
            dialog = page.get_by_role('dialog')
            dialog.get_by_text('Лимиты кэшбэка на месяц', exact=True).click()
            card = dialog.get_by_role('group', name='Вся карта')
            card.get_by_label('Лимит, ₽', exact=True).fill('100')
            card.get_by_label('Уже получено, ₽').fill('101')
            dialog.get_by_role('button', name='Сохранить лимиты').click()
            expect(dialog.get_by_text('Уже получено не может быть больше лимита')).to_be_visible()
            expect(card.get_by_label('Уже получено, ₽')).to_have_attribute('aria-invalid', 'true')
            dialog.get_by_role('button', name='Удалить карту').click()
            dialog = page.get_by_role('dialog', name='Удалить карту?')
            dialog.get_by_role('button', name='Отмена').click()
            expect(page.get_by_role('dialog', name='Настройки карты')).to_be_visible()
            page.keyboard.press('Escape')
            delete = details.get_by_role('button', name='Удалить карту')
            delete_box, category_box = delete.bounding_box(), details.get_by_text('Кафе').bounding_box()
            assert delete_box and category_box and delete_box['y'] > category_box['y']
            delete.click()
            dialog = page.get_by_role('dialog', name='Удалить карту?')
            confirm = dialog.get_by_role('button', name='Удалить карту')
            page.route('**/api/me/manual-cards/*', lambda route: route.fulfill(status=503, json={'message': 'Тестовая ошибка удаления'}) if route.request.method == 'DELETE' else route.fallback(), times=1)
            confirm.click()
            expect(dialog.get_by_role('alert')).to_be_visible()
            expect(details.get_by_text('Кафе')).to_be_visible()
            confirm.click()
            expect(dialog).to_have_count(0)
            expect(details.get_by_role('heading')).to_contain_text('Сбер')
            details.get_by_role('button', name='Удалить карту').click()
            page.get_by_role('dialog').get_by_role('button', name='Удалить карту').click()
            expect(page.get_by_role('heading', name='Кошелёк пуст')).to_be_visible()
            assert page.evaluate('window.parityMarker') is True
            assert page.request.get('/api/me/manual-cards').json() == []
            page.get_by_role('button', name=re.compile('Добавить карту')).click()
            page.get_by_role('button', name='Импортировать со скриншота').click()
            page.locator('#bankId').select_option('vtb')
            page.locator('#chooseActive').click()
            uploads = []

            def mock_ocr(route):
                uploads.append(route.request.post_data_json)
                route.fulfill(status=201, json={'rules': [dict(label='Транспорт', categoryId='transport', rateBps=1500, selected=True)]})

            page.route('**/api/me/cashback-screenshot', mock_ocr)
            page.locator('#cashbackShot').set_input_files(Path(__file__).parent / 'fixtures/cashback-gallery.png')
            expect(page.locator('#confirmCard')).to_be_visible()
            assert not uploads
            page.locator('#confirmCard').click()
            expect(page.locator('[data-key=label]')).to_have_value('Транспорт')
            assert len(uploads) == 1 and page.request.get('/api/me/manual-cards').json() == []
            page.locator('#saveReview').click()
            expect(details.get_by_text('Транспорт')).to_be_visible()
            assert page.request.get('/api/me/manual-cards').json()[0]['rules']
            page.get_by_role('button', name='Профиль').click()
            expect(page.get_by_role('button', name='Выйти', exact=True)).to_be_visible()
            page.get_by_role('button', name='Выйти', exact=True).click()
            page.get_by_role('button', name='Начать', exact=True).click()
            username, password = 'parity_' + uuid4().hex[:12], uuid4().hex
            page.get_by_label('Логин').fill(username)
            page.get_by_label('Пароль', exact=True).fill(password)
            page.locator('#authSubmit').click()
            page.get_by_role('button', name='Профиль').click()
            page.get_by_role('button', name='Выйти', exact=True).click()
            page.get_by_role('button', name='Войти', exact=True).click()
            page.get_by_label('Логин').fill(username)
            page.get_by_label('Пароль', exact=True).fill(password)
            page.locator('#authSubmit').click()
            expect(page.locator('.topbar')).to_be_visible()
            assert page.request.get('/api/auth/me').json()['login'] == username
            assert not errors, errors
            print(f'Chromium {width}px: wallet, monthly empty state, guest cookie and writes passed', flush=True)
            context.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url')
    parser.add_argument('--widths', type=int, nargs='+', default=[320, 390, 1280])
    parser.add_argument('--built', action='store_true', help='Verify served files against local Vite dist')
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    if urlparse(base).hostname not in {'127.0.0.1', 'localhost'}:
        parser.error('Use a local disposable server')
    run(base, args.widths, args.built)
