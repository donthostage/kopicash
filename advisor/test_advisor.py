import unittest
from datetime import date

from advisor import recommend


class Calculation(unittest.TestCase):
    def query(self, category='supermarkets', amount=250000, day='2026-11-20'):
        return recommend(category, amount, date.fromisoformat(day))

    def test_supermarkets(self):
        result = self.query()
        self.assertEqual([(x['cardId'], x['cashbackKopecks']) for x in result['allMatches']],
                         [('B', 15000), ('A', 10000), ('C', 10000), ('D', 5000)])
        self.assertEqual(result['top3'], result['allMatches'][:3])
        self.assertTrue(result['top3'][1]['limitApplied'])

    def test_rounding(self):
        self.assertEqual(self.query(amount=105)['top3'][0]['cashbackKopecks'], 11)

    def test_category_and_minimum(self):
        self.assertEqual(self.query('cafe')['top3'][0]['cashbackKopecks'], 20000)
        self.assertEqual(self.query('cafe', 9999)['top3'], [])
        self.assertEqual(self.query('fuel')['top3'], [])

    def test_dates(self):
        self.assertTrue(self.query(day='2026-11-01')['top3'])
        self.assertFalse(self.query(day='2027-11-01')['top3'])

    def test_category_cap_and_half_up_rounding(self):
        from catalog import SEED

        result = recommend('supermarkets', 250000, date(2026, 11, 20), [SEED[0]])['top3'][0]
        self.assertEqual(result['cashbackKopecks'], 10000)
        self.assertTrue(result['limitApplied'])
        self.assertEqual(result['calculation']['beforeLimitsKopecks'], 25000)
        self.assertEqual(result['calculation']['afterCategoryLimitKopecks'], 10000)
        match = self.query(amount=105)['top3'][0]
        self.assertEqual(match['cashbackKopecks'], 11)
