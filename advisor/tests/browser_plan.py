"""Exercise the wallet UI with a new account on a disposable local instance. No AI calls."""
import argparse
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def check(base, chromium=None):
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=chromium)
        try:
            page = browser.new_page(viewport={'width': 390, 'height': 720}, is_mobile=True,
                                    has_touch=True, service_workers='block')
            page.set_default_timeout(5000)
            errors, blocked = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            def block_ai(route):
                blocked.append(route.request.url)
                route.abort()
            page.route('**/api/me/cashback-screenshot', block_ai)
            page.route('**/api/me/stats/comment', block_ai)
            response = page.request.post(base + '/api/auth/register', data={'login':'plan_' + uuid4().hex[:12], 'password':uuid4().hex})
            assert response.status in (200, 201), response.text()
            page.goto(base)
            loc = lambda ident: page.locator('#' + ident)
            loc('openCards').click()
            # Simulate only the OCR response; never send an image to the service.
            loc('openCatalog').click()
            loc('addRouteShot').click()
            loc('chooseActive').click()
            page.route('**/api/me/cashback-screenshot', lambda r: r.fulfill(json={'rules':[{'label':'Кафе','selected':None,'uncertain':True}]}))
            loc('cashbackShot').set_input_files({
                'name': 'synthetic.png', 'mimeType': 'image/png',
                'buffer': bytes.fromhex('89504e470d0a1a0a') + b'synthetic',
            })
            loc('confirmCard').click()
            expect(loc('reviewForm')).to_be_visible()
            current_month = page.evaluate('() => new Date().toISOString().slice(0, 7)')
            expect(loc('reviewMonth')).to_have_value(current_month)
            expect(loc('reviewMonthText')).not_to_be_empty()
            review_row = loc('reviewRows').locator('.review-row')
            expect(review_row).to_have_count(1)
            checkbox = review_row.get_by_role('checkbox', name='Подключена')
            expect(checkbox).to_be_visible()
            expect(checkbox).not_to_be_checked()
            review_row.locator('summary').click()
            expect(review_row.get_by_label('Ставка, %')).to_be_visible()
            expect(loc('saveReview')).to_be_disabled()
            loc('closeCatalog').click()
            expect(loc('discardDialog')).to_be_visible()
            loc('discardLeave').click()
            expect(loc('openCatalog')).to_be_focused()
            loc('openCashback').click()
            loc('openPlan').click()
            month = page.evaluate("""() => {const d = new Date();return new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,1)).toISOString().slice(0,7)}""")
            expect(loc('planMonth')).to_have_value(month)
            loc('calculatePlan').click()
            expect(loc('planResult')).to_contain_text('Нет расходов')
            loc('planResult').get_by_role('button', name='Ввести расходы').click()
            def spend(index, category, amount):
                row = loc('spendRows').locator(':scope > div').nth(index)
                row.locator('[data-key=categoryId]').select_option(category)
                row.locator('[data-key=amount]').fill(amount)
            spend(0, 'cafe', '1000')
            loc('spendingInputs').get_by_role('button', name='Добавить покупку').click()
            spend(1, 'supermarkets', '2000')
            loc('calculatePlan').click()
            expect(loc('planResult')).to_contain_text('Нет подтверждённых условий')
            banks = loc('bankId').locator('option').evaluate_all('(options) => options.slice(0,2).map(o=>[o.value,o.text])')
            assert len(banks) == 2
            labels = ['Кафе', 'Супермаркеты']
            for (bank, _), label, category, rate in zip(banks, labels, ('cafe', 'supermarkets'), (500, 1000)):
                response = page.request.post(base+'/api/me/cashback-confirm', data={
                    'bankId':bank, 'month':month, 'mode':'offer', 'slots':1, 'requestId':uuid4().hex,
                    'rules':[{'label':label,'categoryId':category,'rateBps':rate,'limitKopecks':None,'minAmountKopecks':1,'selected':True,'uncertain':False}],
                })
                assert response.ok, response.text()
            loc('calculatePlan').click()
            expect(loc('planResult')).to_contain_text('250')
            metrics = loc('planResult').locator('[data-kopecks]').evaluate_all('(els)=>els.map(e=>Number(e.dataset.kopecks))')
            assert metrics == [0, 25000, 25000], metrics
            def count_plan(route):
                plan_requests.append(route.request.url)
                route.continue_()
            plan_requests = []
            page.route('**/api/me/cashback-plan', count_plan)
            loc('calculatePlan').click()
            expect(loc('planResult')).to_contain_text('250')
            assert not plan_requests
            spend(1, 'supermarkets', '3000')
            loc('calculatePlan').click()
            expect(loc('planResult')).to_contain_text('350')
            assert len(plan_requests) == 1
            expect(loc('planResult').get_by_role('button', name='Добавить предложения банка')).to_have_count(0)
            expect(loc('planResult').get_by_role('button', name='Я выбрал это в банке')).to_have_count(0)
            loc('planCurrent').click()
            expect(loc('planMonth')).to_have_value(current_month)
            loc('planNext').click()
            expect(loc('planMonth')).to_have_value(month)
            expect(loc('spendingMonth')).to_have_value(current_month)
            page.on('dialog', lambda d: d.accept())
            loc('closePlan').click()
            expect(loc('openPlan')).to_be_focused()
            assert not errors and not blocked, (errors, blocked)
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('base')
    parser.add_argument('--chromium-executable')
    args = parser.parse_args()
    check(args.base, args.chromium_executable)
    print('Advisor monthly plan acceptance passed.')
