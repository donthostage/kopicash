"""Exercise the visible wallet in Chromium; always start a private loopback server and DB."""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = (320, 360, 390, 430, 1280)
REC = '**/api/recommendations'


@contextmanager
def isolated_server():
    import uvicorn
    sys.path.insert(0, str(ROOT))
    from catalog import SEED, import_catalog
    with tempfile.TemporaryDirectory(prefix='advisor-smoke-') as tmp, socket.socket() as sock:
        db = str(Path(tmp) / 'wallet.sqlite3')
        # Keep the real seed rates, caps, thresholds and ordering valid on future CI dates.
        import_catalog(db, [dict(row, validFrom='2000-01-01', validUntilExclusive='2100-01-01',
                                 updatedOn='2000-01-01') for row in SEED])
        os.environ['ADVISOR_DB'] = db  # advisor constructs its default app at import.
        from advisor import create_app
        sock.bind(('127.0.0.1', 0))
        base = f'http://127.0.0.1:{sock.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(create_app(db), log_level='warning'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                if not thread.is_alive() or time.monotonic() > deadline:
                    raise RuntimeError('Disposable server did not start')
                time.sleep(.025)
            yield base
        finally:
            server.should_exit = True
            thread.join(10)


def button(root, name):
    return root.get_by_role('button', name=name, exact=isinstance(name, str))


def screenshots(page, directory, stage):
    for width in WIDTHS:
        page.set_viewport_size({'width': width, 'height': 844})
        page.evaluate('window.scrollTo(0, 0)')
        page.screenshot(path=directory / f'{stage}-{width}.png', animations='disabled', full_page=True)
        for frame in page.frames:
            if frame != page.main_frame and not frame.frame_element().is_visible():
                continue
            viewport, content = frame.evaluate('''() => [document.documentElement.clientWidth,
                Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)]''')
            assert viewport == width and content <= width, (stage, frame.url, width, viewport, content)
    page.set_viewport_size({'width': 390, 'height': 844})


def rank(page, rows):
    articles = page.locator('#buyResults').get_by_role('article')  # excludes collapsed rows
    expect(articles).to_have_count(len(rows))
    for i, (name, rubles) in enumerate(rows):
        expect(articles.nth(i).get_by_role('heading').first).to_contain_text(name)
        expect(articles.nth(i)).to_contain_text(re.compile(r'(?<![\d,])' + rubles + r'(?:,00)?\s*₽'))


def category(page, name):
    grid = page.locator('#categoryGrid')
    if not grid.is_visible():
        button(page, re.compile('Изменить')).click()
    tile = button(grid, name)
    if not tile.is_visible():
        button(page, 'Все категории').click()
    tile.click()
    expect(grid).to_be_hidden()
    expect(button(page, re.compile('Изменить'))).to_contain_text(name)


def purchase_plan_scenario(page):
    ids = []
    for name, supermarket, transport in [('Карта плана А', 1000, 1000), ('Карта плана Б', 800, 100)]:
        response = page.request.post('/api/me/manual-cards', data={'name': name, 'rules': [
            {'categoryId': 'supermarkets', 'rateBps': supermarket},
            {'categoryId': 'transport', 'rateBps': transport},
        ]})
        assert response.ok, response.text()
        ids.append(response.json()['cardId'])
    response = page.request.put(f'/api/me/cards/{ids[0]}/monthly',
                                data={'limitKopecks': 30_000, 'usedKopecks': 20_000})
    assert response.ok, response.text()

    page.evaluate('() => load()')
    page.locator('#openCashback').click()
    page.get_by_text('Спланировать несколько покупок', exact=True).click()
    rows = page.locator('#purchasePlanRows').get_by_role('group')
    expect(rows).to_have_count(2)
    for row, category_id in zip(rows.all(), ['supermarkets', 'transport'], strict=True):
        row.get_by_label('Категория').select_option(category_id)
        row.get_by_label('Сумма, ₽').fill('1 000')
    button(page, 'Рассчитать план').click()
    result = page.locator('#purchasePlanResult')
    for value in ('180', '110', '70'):
        expect(result).to_contain_text(re.compile(value + r'\s*₽'))
    for row, name in zip(result.get_by_role('listitem').all(), ('Карта плана Б', 'Карта плана А'), strict=True):
        expect(row).to_contain_text(name)

    button(page, 'Добавить покупку').click()
    expect(rows).to_have_count(3)
    expect(result).to_be_hidden()
    button(page, 'Удалить покупку 3').click()
    expect(rows).to_have_count(2)
    page.locator('#purchasePlan summary').click()
    page.locator('#brandHome').click()
    for card in ids:
        assert page.request.delete(f'/api/me/manual-cards/{card}').ok
    page.evaluate('() => load()')


def catalog_scenario(page, directory):
    buy = page.locator('#buyPanel')
    amount, status = page.locator('#buyAmount'), page.locator('#buyStatus')
    page.goto('/#buy')
    expect(amount).to_be_visible()
    expect(amount).not_to_be_focused()
    expect(button(buy, 'Все карты')).to_have_attribute('aria-pressed', 'true')
    screenshots(page, directory, 'categories')
    category(page, 'Супермаркеты')
    amount.fill('2 500')
    rank(page, [('Карта B', '150'), ('Карта A', '100'), ('Карта C', '100')])
    button(buy, 'Мои карты').click()
    expect(status).to_contain_text('Кошелёк пуст')
    expect(buy.get_by_role('article')).to_have_count(0)
    button(buy, 'Добавить карту').click()
    expect(page.locator('#addDialog')).to_be_visible()
    page.locator('#closeAdd').click()
    page.locator('#brandHome').click()
    expect(page.locator('#openBuy')).to_be_visible()
    page.locator('#openBuy').click()
    expect(amount).to_be_visible()
    button(buy, 'Мои карты').click()
    for card in 'ABCD':
        assert page.request.put(f'/api/me/cards/{card}').ok
    page.evaluate('() => load()')
    amount.fill('2 500')
    top = [('Карта B', '150'), ('Карта A', '100'), ('Карта C', '100')]
    rank(page, top)
    screenshots(page, directory, 'top3')
    card_a = buy.get_by_role('article').nth(1)
    card_a.get_by_text('Условия', exact=True).click()
    for evidence in ['10%', 'применён', 'Актуальность', '01.01.2000']:
        expect(card_a.locator('details[open]')).to_contain_text(evidence)
    buy.get_by_text(re.compile('^Все подходящие карты')).click()
    rank(page, top + [('Карта D', '50')])
    category(page, 'Кафе')
    expect(amount).to_have_value('2 500')
    rank(page, [('Карта D', '200')])
    amount.fill('99,99')
    expect(status).to_contain_text('подходящих условий нет')
    rank(page, [])
    amount.fill('100')
    rank(page, [('Карта D', '8')])
    category(page, 'Супермаркеты')
    amount.fill('2500')
    rank(page, top)

    sent = []
    page.on('request', lambda req: sent.append(req.post_data_json) if req.url.endswith('/api/recommendations') else None)
    for raw, hint in [('', 'Введите'), ('0', 'нуля'), ('-1', 'отрицатель'), ('1.234', 'двух'),
                      ('10000000001', 'Максимальная'), ('2,', 'целиком')]:
        amount.fill(raw)
        expect(status).to_contain_text(hint)
        rank(page, [])
    # Cross the debounce interval once, then use a valid calculation as a synchronization point.
    for raw in ('2500,50', '2500.50'):
        with page.expect_response(lambda r: r.url.endswith('/api/recommendations')) as response:
            amount.fill(raw)
        assert response.value.request.post_data_json['amountKopecks'] == 250050
        rank(page, [('Карта B', '150,03'), ('Карта C', '100,02'), ('Карта A', '100')])
    assert [body['amountKopecks'] for body in sent] == [250050, 250050], sent
    page.route(REC, lambda route: route.fulfill(status=503, body='{}'), times=1)
    amount.fill('2500')
    retry = button(buy, re.compile('Повторить'))
    expect(retry).to_be_visible()
    rank(page, [])
    retry.click()
    rank(page, top)


def record_once(page, base, card_name):
    paid = page.get_by_label('Какой картой вы оплатили?')
    expect(paid).to_have_value('')
    paid.select_option(label=card_name)
    submit = button(page, 'Записать покупку')
    bodies = []

    def lose_first_response(route):
        bodies.append(route.request.post_data_json)
        if len(bodies) == 1:
            # Commit to the real DB first; drop only the response on the way to the UI.
            upstream = route.fetch(max_retries=0)
            assert upstream.status == 201, upstream.text()
            route.abort()
        else:
            route.continue_()

    stats = base + '/api/me/stats'
    assert page.request.get(stats).json()['count'] == 0
    page.route('**/api/me/purchases', lose_first_response)
    submit.click()
    expect(page.get_by_text(re.compile('Нет соединения с сервером|Не удалось подтвердить запись'))).to_be_visible()
    submit.click()
    expect(page.locator('#buyStatus')).to_contain_text('Покупка записана')
    assert len(bodies) == 2 and bodies[0] == bodies[1] and bodies[0]['requestId'], bodies
    report = page.request.get(stats).json()
    assert report['count'] == 1 and report['purchases'][0]['amountKopecks'] == bodies[0]['amountKopecks'], report
    button(page, 'Открыть историю').click()
    history = page.locator('#historyPanel')
    expect(history.get_by_role('heading', name='История покупок')).to_be_visible()
    expect(history).to_contain_text(card_name)


def personal_scenario(page, base, directory):
    page.locator('#brandHome').click()
    expect(page.locator('#hero')).to_be_visible()
    page.locator('#openCards').click()
    cards = page.locator('#cardsPanel')
    expect(cards).to_be_visible()
    add = page.locator('#addDialog')
    cards.locator('#openCatalog').click()
    button(add, 'Учебный каталог').click()
    add.locator('#newBank').select_option('A')
    button(add, 'Добавить карту').click()
    expect(add).to_be_hidden()
    expect(page.locator('#carouselDetails')).to_contain_text('Карта A')
    expect(page.locator('#carouselControls')).to_be_hidden()
    expect(cards.locator('#addCashbackBtn')).to_have_text('Настройки карты')
    cards.locator('#addCashbackBtn').click()
    expect(page.locator('#cardSettingsDialog')).to_be_visible()
    page.locator('#closeCardSettings').click()
    cards.locator('#openCatalog').click()
    search = add.get_by_role('combobox', name='Найти банк')
    search.fill('несуществующийбанк')
    expect(button(add, 'Добавить карту')).to_be_disabled()
    search.fill('ВТБ')
    add.locator('#bankSuggestions').get_by_role('option', name='ВТБ', exact=True).click()
    button(add, 'Добавить карту').click()
    expect(add).to_be_hidden()
    details = page.locator('#carouselDetails')
    expect(details).to_contain_text('ВТБ')
    expect(page.locator('#carouselPosition')).to_contain_text('из 2')
    expect(page.locator('#previousCard')).to_be_hidden()
    expect(page.locator('#nextCard')).to_be_hidden()
    expect(page.get_by_text('На главную', exact=True)).to_have_count(0)
    toast = page.locator('#toast')
    expect(toast).to_have_text('Карта добавлена')
    assert toast.bounding_box()['height'] < 100
    expect(cards.get_by_role('button', name='Сравнивать с этой картой', exact=True)).to_have_count(0)
    cards.locator('#deleteEmptyCard').click()
    expect(page.locator('#deleteDialog')).to_be_visible()
    expect(page.locator('#cancelDelete')).to_be_focused()
    page.locator('#cancelDelete').click()
    expect(cards.locator('#deleteEmptyCard')).to_be_focused()
    cards.locator('#addCashbackBtn').click()
    expect(page.locator('#catalogDialog')).to_be_visible()
    page.locator('#closeCatalog').click()
    carousel = page.locator('#cardCarousel')
    carousel.focus()
    carousel.press('ArrowLeft')
    expect(details).to_contain_text('Карта A')
    carousel.press('ArrowRight')
    expect(details).to_contain_text('ВТБ')
    cards.locator('#addCashbackBtn').click()
    review = page.locator('#catalogDialog')
    expect(review.locator('#cashbackShot')).to_be_visible()
    rules = [
        dict(label='Транспорт', categoryId='transport', rateBps=1500, selected=True),
        dict(label='На все покупки', categoryId='all', rateBps=100, selected=True),
    ]
    uploads = []

    def recognize(route):
        uploads.append(route.request.post_data_json)
        route.fulfill(status=201, json={'rules': rules})

    page.route('**/api/me/cashback-screenshot', recognize, times=1)
    review.locator('#cashbackShot').set_input_files(ROOT / 'tests/fixtures/cashback-gallery.png')
    expect(review.locator('#confirmCard')).to_be_visible()
    assert not uploads
    review.locator('#confirmCard').click()
    expect(review.locator('#reviewRows .review-row')).to_have_count(2)
    assert len(uploads) == 1
    screenshots(page, directory, 'manual-conditions')
    button(review, re.compile('Сохранить')).click()
    expect(review).to_be_hidden()
    expect(cards.locator('#addCashbackBtn')).to_have_text('Настройки карты')
    cards.locator('#addCashbackBtn').click()
    expect(page.locator('#cardSettingsDialog')).to_be_visible()
    editor = page.locator('#carouselCategories details', has_text='Изменить Транспорт')
    editor.locator('summary').click()
    editor.get_by_label('Название категории').fill('Поездки')
    editor.get_by_role('button', name='Сохранить').click()
    expect(page.locator('#carouselCategories')).to_contain_text('Поездки')
    expect(page.locator('#carouselCategories')).not_to_contain_text('Изменить Транспорт')
    page.locator('#closeCardSettings').click()
    carousel.press('ArrowLeft')
    expect(details).to_contain_text('Карта A')
    # Existing accounts may have a comparison card set through the legacy API.
    assert page.request.put('/api/me/usual-card', data={'cardId': 'A'}).ok
    page.reload()
    expect(cards).to_be_visible()
    expect(page.locator('#carouselDetails')).to_contain_text(re.compile('Карта A|ВТБ'))
    page.locator('#brandHome').click()
    page.locator('#openBuy').click()
    category(page, 'Транспорт')
    amount = page.locator('#buyAmount')
    amount.fill('1000')
    rank(page, [('ВТБ', '150')])  # Exact rule, not 15% + 1%.
    category(page, 'АЗС')
    rank(page, [('ВТБ', '10')])  # Only this card has a fallback rule.
    amount.fill('0,01')
    rank(page, [('ВТБ', '0')])
    expect(page.locator('#buyStatus')).to_contain_text('0 ₽')
    category(page, 'Супермаркеты')
    amount.fill('2500')
    rank(page, [('Карта A', '100'), ('ВТБ', '25')])
    record_once(page, base, 'ВТБ')
    history = page.locator('#historyPanel')
    expect(history.locator('.journal-summary')).to_contain_text(re.compile(r'100(?:,00)?\s*₽'))
    history.locator('.journal-row').first.click()
    expect(history.locator('.journal-detail').first).to_contain_text(re.compile(r'Карта для сравнения: 100(?:,00)?\s*₽'))
    expect(history.locator('.journal-detail').first).to_contain_text(re.compile(r'Выбранная карта: ВТБ, 25(?:,00)?\s*₽'))
    screenshots(page, directory, 'history')


def cashback_summary_scenario(page):
    page.set_viewport_size({'width': 390, 'height': 844})
    history = page.locator('#historyPanel')
    history.locator('.journal-confirm').first.click()
    form = history.locator('.journal-actual').first
    amount = form.get_by_label('Сколько начислил банк, ₽')
    expect(form).to_contain_text('Начисление ещё не подтверждено')
    amount.fill('48')
    page.route('**/api/me/purchases/*/cashback', lambda route: route.fulfill(
        status=503, json={'message': 'Временно недоступно'}), times=1)
    button(form, 'Сохранить').click()
    expect(form.locator('.journal-actual-error')).to_have_text('Временно недоступно')
    expect(amount).to_have_value('48')
    button(form, 'Сохранить').click()
    expect(form.locator('.journal-actual-note')).to_contain_text('Сохранено:')

    page.locator('#openProfile').click()
    profile = page.locator('#accountPanel')
    expect(profile).to_contain_text('Кэшбэк получен')
    expect(profile).to_contain_text(re.compile(r'48(?:,00)?\s*₽'))
    expect(profile).to_contain_text(re.compile(r'2\s*500(?:,00)?\s*₽'))
    expect(profile.locator('.profile-chart')).to_contain_text('Супермаркеты')
    theme = page.locator('#themeToggle')
    theme.click()
    expect(theme).to_have_attribute('aria-pressed', 'true')
    page.reload()
    expect(theme).to_have_attribute('aria-pressed', 'true')
    theme.click()
    page.locator('#openCashback').click()
    summary = page.locator('#homeMonthCashbackBody')
    expect(summary.locator('.month-cashback-actual .money')).to_have_text(re.compile(r'^48(?:,00)?\s*₽$'))
    expect(summary).to_contain_text('Подтверждённые начисления: 1 из 1')
    expect(summary).to_contain_text('По расчёту')
    expect(summary).to_contain_text('Можно было ещё')
    summary.get_by_text('По картам', exact=True).click()
    expect(summary.locator('li').first).to_contain_text(re.compile(r'48(?:,00)?\s*₽'))
    assert page.evaluate('document.documentElement.scrollWidth === innerWidth')

    button(summary, 'Покупки за месяц').click()
    history.locator('.journal-confirm').first.click()
    expect(amount).to_have_value('48')
    amount.fill('0')
    button(form, 'Сохранить').click()
    expect(form.locator('.journal-actual-note')).to_contain_text('Подтверждённый ноль')
    page.locator('#cashbackPanel').get_by_role('button', name='Сводка и план').click()
    expect(summary.locator('.month-cashback-actual .money')).to_have_text(re.compile(r'^0(?:,00)?\s*₽$'))
    button(summary, 'Покупки за месяц').click()
    history.locator('.journal-confirm').first.click()
    button(form, 'Удалить отметку').click()
    expect(form.locator('.journal-actual-note')).to_have_text('Начисление ещё не подтверждено')
    page.locator('#cashbackPanel').get_by_role('button', name='Сводка и план').click()
    expect(summary).to_contain_text('Нет подтверждённых начислений')


def run_cashback_summary(chromium):
    with isolated_server() as base, sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=chromium)
        try:
            page = browser.new_page(base_url=base, viewport={'width': 390, 'height': 844}, locale='ru-RU')
            response = page.request.post('/api/auth/register', data={
                'login': 'cashback_summary', 'password': uuid4().hex,
            })
            assert response.ok, response.text()
            assert page.request.put('/api/me/cards/B').ok
            page.goto('/#cashback')
            expect(page.locator('#homeMonthCashbackBody')).to_contain_text('в этом месяце пока нет')
            response = page.request.post('/api/me/purchases', data={
                'chosenCardId': 'B', 'categoryId': 'supermarkets', 'amountKopecks': 250_000,
            })
            assert response.ok, response.text()
            page.goto('/#history')
            expect(page.locator('.journal-row').first).to_be_visible()
            cashback_summary_scenario(page)
        finally:
            browser.close()


def run(chromium, directory, revision):
    directory.mkdir(parents=True, exist_ok=True)
    with isolated_server() as base, sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=chromium)
        try:
            context = browser.new_context(base_url=base, viewport={'width':390, 'height':844}, locale='ru-RU',
                                          reduced_motion='reduce', service_workers='block')
            denied, errors = [], []

            def local_only(route):
                url = route.request.url
                if not url.startswith(base + '/') or url.endswith(('/cashback-screenshot', '/stats/comment')):
                    denied.append(url)
                    route.abort()
                else:
                    route.continue_()
            context.route('**/*', local_only)
            page = context.new_page()
            page.set_default_timeout(6500)
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(base)
                start = page.frame_locator('#welcomeScreen').locator('#start')
                expect(start).to_be_visible()
                screenshots(page, directory, 'welcome')
                start.click()
                auth = page.locator('#authForm')
                login, password = 'qa_' + uuid4().hex[:10], uuid4().hex
                auth.get_by_label('Логин').fill(login)
                auth.get_by_label('Пароль', exact=True).fill(password)
                button(auth, re.compile('Создать|Зарегистр')).click()
                expect(page.locator('#openBuy')).to_be_visible()
                screenshots(page, directory, 'home-empty')
                expect(page.locator('#openBuy')).to_have_accessible_name('Сравнить карты')
                purchase_plan_scenario(page)
                catalog_scenario(page, directory)
                for card in 'ABCD':
                    assert page.request.delete(f'/api/me/cards/{card}').ok
                page.evaluate('() => load()')
                personal_scenario(page, base, directory)
                cashback_summary_scenario(page)
                assert not denied and not errors, (denied, errors)
            except Exception:
                page.screenshot(path=directory/'failure.png', animations='disabled', full_page=True)
                raise
        finally:
            browser.close()
        if revision:
            subprocess.run([sys.executable, str(ROOT/'deploy'/'smoke.py'), base, '--revision', revision], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium-executable', help='Optional installed Chrome/Edge executable')
    parser.add_argument('--artifacts', type=Path, default=None)
    parser.add_argument('--cashback-summary-only', action='store_true')
    parser.add_argument('--revision', help='Verify the revision when running a release archive')
    args = parser.parse_args()
    if args.cashback_summary_only:
        run_cashback_summary(args.chromium_executable)
        print('Cashback summary and journal acceptance passed at 390 px.')
    else:
        artifacts = args.artifacts or Path(tempfile.mkdtemp(prefix='advisor-screens-'))
        print(f'Browser screenshots: {artifacts.resolve()}', flush=True)
        run(args.chromium_executable, artifacts, args.revision)
        print('Advisor visible wallet acceptance passed.')
