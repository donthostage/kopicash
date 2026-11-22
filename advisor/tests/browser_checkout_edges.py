"""Boundary cases in a real Chromium checkout. Only use a disposable local instance."""
import argparse
from datetime import datetime, UTC
from uuid import uuid4
from urllib.parse import urlparse
from playwright.sync_api import expect, sync_playwright


def check(base, executable=None):
    if urlparse(base).hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Укажите локальный тестовый стенд')
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        try:
            page = browser.new_page(viewport={'width':360,'height':780}, service_workers='block')
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            creds = {'login':'edge_'+uuid4().hex[:12], 'password':uuid4().hex}
            assert page.request.post(base+'/api/auth/register', data=creds).status == 201
            # Set up the private fixture using the same real confirmation API as the UI.
            def rule(label, cid, rate, minimum=1):
                return dict(label=label,categoryId=cid,rateBps=rate,limitKopecks=None,minAmountKopecks=minimum,selected=True,uncertain=False)
            body = dict(bankId='sber',month=datetime.now(UTC).strftime('%Y-%m'),mode='active',slots=3,requestId=uuid4().hex,
                        rules=[rule('Транспорт','transport',1500,10000),rule('На все покупки','all',100),rule('АЗС','fuel',0)])
            saved = page.request.post(base+'/api/me/cashback-confirm',data=body)
            assert saved.ok
            page.goto(base);page.locator('#openBuy').click()
            page.locator('#categoryGrid').get_by_role('button',name='Транспорт',exact=True).click()
            field=page.locator('#buyAmount'); val=page.locator('#buyResults .advice-value').first
            seen=[]
            page.on('request',lambda r: seen.append(r.post_data_json) if r.url.endswith('/api/recommendations') else None)
            for raw, text in [('1000','150'),('99,99','1'),('100','15'),('2 500','375'),('2500.50','375,08'),('2500,50','375,08')]:
                field.fill(raw);expect(val).to_have_text(text+' ₽');expect(field).to_be_focused()
            for raw in ('', '0', '-1', '1,', '1.123','10000000001','2 50'):
                count=len(seen);field.fill(raw);page.wait_for_timeout(230)
                assert len(seen)==count,(raw,seen[count:]);expect(val).to_have_count(0)
            field.fill('1000');expect(val).to_have_text('150 ₽')
            page.locator('#changeCategory').click();page.locator('#categoryGrid').get_by_role('button',name='АЗС',exact=True).click()
            expect(val).to_have_text('0 ₽');expect(page.locator('#buyStatus')).to_contain_text('0 ₽')
            page.route('**/api/recommendations',lambda route:route.abort());field.fill('1100');page.get_by_role('button',name='Повторить расчёт').wait_for()
            page.unroute('**/api/recommendations');page.get_by_role('button',name='Повторить расчёт').click();expect(val).to_have_text('0 ₽')
            page.locator('#changeCategory').click();page.locator('#categoryGrid').get_by_role('button',name='Транспорт',exact=True).click()
            field.fill('123');field.fill('124');field.fill('1000');expect(val).to_have_text('150 ₽');expect(field).to_be_focused()
            card_id = saved.json()['cardId']
            limits = page.request.put(base+f'/api/me/cards/{card_id}/monthly', data={'limitKopecks':50000,'usedKopecks':40000})
            assert limits.ok
            field.fill('2500')
            expect(val).to_have_text('100 ₽')
            winner = page.locator('.advice-winner')
            expect(winner).to_contain_text('По ставке 375 ₽. Остаток месяца — 100 ₽.')
            winner.get_by_text('Условия', exact=True).click()
            expect(winner.locator('dt').get_by_text('Остаток месяца', exact=True).locator('xpath=following-sibling::dd[1]')).to_have_text('100 ₽')
            expect(winner.locator('dt').get_by_text('Ожидаемый кэшбэк', exact=True).locator('xpath=following-sibling::dd[1]')).to_have_text('100 ₽')
            assert not errors, errors
        finally:
            browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('base_url');parser.add_argument('--chromium-executable');args=parser.parse_args()
    check(args.base_url.rstrip('/'),args.chromium_executable);print('Проверки граничных состояний покупки пройдены.')
