import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
import httpx

from catalog import connect
from cashback_planner import mount_planner


def rule(label, category, rate, *, cap=None, minimum=1, **extra):
    return dict(label=label, categoryId=category, rateBps=rate, limitKopecks=cap,
                minAmountKopecks=minimum, **extra)


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.db = Path(self.enterContext(tempfile.TemporaryDirectory())) / 'test.db'
        with connect(self.db) as db:
            db.executescript('''CREATE TABLE cashback_sets (session,card_id,bank_id,month,mode,slots,rules_json,
                 PRIMARY KEY(session,card_id,month,mode));
                 CREATE TABLE purchases (session,bought_on,category_id,amount_kopecks);''')
        app = FastAPI()
        mount_planner(app, self.db, lambda req: req.headers.get('x-test-user'))
        self.transport = httpx.ASGITransport(app=app)

    def save(self, card, mode, rules, slots=1, user='u', month='2026-12'):
        with connect(self.db) as db:
            db.execute('INSERT INTO cashback_sets VALUES (?,?,?,?,?,?,?)',
                       (user, card, 'bank-' + card, month, mode, slots, json.dumps(rules)))

    def purchase(self, category, amount, user='u', day='2026-11-10'):
        with connect(self.db) as db:
            db.execute('INSERT INTO purchases VALUES (?,?,?,?)', (user, day, category, amount))

    def post(self, body=None, user='u'):
        async def request():
            async with httpx.AsyncClient(transport=self.transport, base_url='http://test') as client:
                return await client.post('/api/me/cashback-plan', headers={'x-test-user':user}, json={
                    'month':'2026-12', 'spendingMonth':'2026-11', **(body or {})})
        return asyncio.run(request())

    def plan(self, *items):
        body = {'spending':[dict(categoryId=c, amountKopecks=a) for c,a in items]} if items else {}
        response = self.post(body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_cross_bank_tie_and_winner(self):
        self.save('A','offer',[rule('Продукты 5%','food',500), rule('Кино / билеты','cinema',1000)])
        self.save('B','active',[rule('Продукты','food',400,selected=True)])
        result = self.plan(('food',2000000), ('cinema',200000))
        self.assertEqual((result['baseKopecks'],result['projectedKopecks'],result['gainKopecks']),
                         (80000,100000,20000))
        self.assertTrue(any('равноцен' in w.lower() for w in result['warnings']))
        winner = self.plan(('food',2000000), ('cinema',300000))
        self.assertEqual(winner['projectedKopecks'],110000)
        self.assertEqual(winner['choices'],[{'cardId':'A','bankId':'bank-A','labels':['Кино / билеты']}])

    def test_locked_slots_and_nonselected_active_rules(self):
        self.save('A','active',[rule('Уже выбрано','food',500,selected=True),
                                rule('Нет','cinema',9999,selected=False)])
        self.save('A','offer',[rule('Уже выбрано','food',500),rule('Кино','cinema',1000)])
        result = self.plan(('cinema',100000))
        self.assertEqual((result['gainKopecks'],result['choices']),(0,[]))

    def test_history_isolation_and_explicit_empty_replaces_history(self):
        self.save('A','active',[rule('Кино','cinema',1000)])
        self.save('X','active',[rule('Не для меня','cinema',10000)],user='other')
        self.save('Y','active',[rule('Не в этом месяце','cinema',9999)],month='2026-11')
        self.purchase('cinema',105); self.purchase('cinema',99999,user='other'); self.purchase('cinema',99999,day='2026-10-10')
        self.assertEqual(self.plan()['baseKopecks'],11)
        self.assertEqual(self.plan(('cinema',95))['baseKopecks'],10)
        self.assertEqual(self.post({'spending':[]}).json()['projectedKopecks'],0)
        result = self.post(user='stranger').json()
        self.assertFalse(result['choices']); self.assertTrue(any('вручную' in w for w in result['warnings']))

    def test_threshold_fallback_precedence_and_cumulative_cap(self):
        self.save('A','active',[rule('Все','all',100,minimum=10000),rule('Кино','cinema',500,cap=600)])
        for c,a in [('cinema',10000),('cinema',10000),('cinema',10000),('food',9999),('food',10000)]:
            self.purchase(c,a)
        self.assertEqual(self.plan()['baseKopecks'],700)

    def test_small_capped_routing_is_not_myopic(self):
        self.save('A','active',[rule('Все','all',1000,cap=1000)])
        self.save('B','active',[rule('Продукты','food',900)])
        result = self.plan(('food',10000),('cinema',10000))
        self.assertEqual(result['baseKopecks'],1900)

    def test_unknowns_deselected_offers_and_literal_private_categories(self):
        self.save('A','offer',[rule('Кино / билеты','Афиша',1000),
                               rule('Не выбрать','Афиша',9999,selected=False),
                               rule('Ставка не видна','Афиша',None,selected=True)])
        result = self.plan(('Афиша',10000), ('fuel',50000))
        self.assertEqual(result['projectedKopecks'],1000)
        self.assertEqual(result['choices'][0]['labels'],['Кино / билеты'])
        self.assertTrue(any('не распознана' in w for w in result['warnings']))
        self.assertTrue(any('1 из 2' in w for w in result['warnings']))

    def test_threshold_allows_fallback_but_exact_zero_blocks_it(self):
        self.save('A','active',[rule('Все','all',1000), rule('Билеты','cinema',0,minimum=10000)])
        self.assertEqual(self.plan(('cinema',9999),('cinema',10000))['projectedKopecks'],1000)

    def test_read_only_offer_plans_are_repeatable(self):
        self.save('A','offer',[rule('Кино','cinema',500,selected=True)])
        self.purchase('cinema',100000)
        def snapshot():
            with connect(self.db) as db:
                return tuple(db.iterdump())
        before = snapshot()
        result = self.plan()
        self.assertEqual(result['baseKopecks'],0)
        self.assertEqual(result['projectedKopecks'],5000)
        self.assertEqual(self.plan(),result)
        self.assertEqual(snapshot(),before)

    def test_bad_request_and_auth(self):
        for body in [{'month':'2026-00'}, {'spendingMonth':'2026-1'}, {'spending':None},
                     {'spending':[{'categoryId':'food','amountKopecks':True}]}]:
            self.assertEqual(self.post(body).status_code,422)
        self.assertEqual(self.post(user='').status_code,401)

    def test_oversized_search_reports_partial_not_false_maximum(self):
        self.save('A','offer',[rule('Категория '+str(i),'c'+str(i),100) for i in range(22)],slots=11)
        result=self.plan(*[('c'+str(i),10000) for i in range(22)])
        self.assertTrue(any('перебор' in w.lower() for w in result['warnings']))
        self.assertLessEqual(result['projectedKopecks'],1100)
