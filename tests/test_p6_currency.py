"""Pakistan budget boundaries: currency is part of the fact, never an FX guess."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from agents.matching import money, match_requirement
from agents.evidence import normalized
from agents.follow_up import answer_follow_up
from models.request import Requirement
from models.product import Spec
from models.comparison import Comparison


class CurrencyTests(unittest.IsolatedAsyncioTestCase):
    def test_pkr_matching_and_cross_currency_unknown(self):
        req = Requirement(key='budget', operator='<', value='250000 PKR', priority='must')
        for value, expected in [('239,999 PKR', '✓'), ('250000 PKR', '✕'), ('1000 USD', '?')]:
            spec = Spec(key='budget', value=value, status='supported', evidence_ids=['listing'])
            self.assertEqual(match_requirement(req, [spec])[0], expected)
        self.assertEqual(money('Rs. 239,999'), (239999, 'PKR'))
        for value in ['-100 PKR', '250000 EUR', 'PKR 100 USD', 'NaN PKR', '100-200 PKR']:
            self.assertIsNone(money(value))

    def test_evidence_keeps_currency(self):
        self.assertEqual(normalized('budget', 'PKR 239,999'), normalized('budget', '239999 PKR'))
        self.assertNotEqual(normalized('budget', '1000 PKR'), normalized('budget', '1000 USD'))

    async def test_follow_up_retains_active_currency(self):
        comparison = Comparison(request_id='test', requirements=[Requirement(key='budget', operator='<=', value='250000 PKR', priority='must')])
        for question in ['What if budget is 300000?', 'Increase budget to PKR 300,000']:
            result = await answer_follow_up(comparison, question)
            self.assertEqual(result.suggested_requirements_patch[0]['value'], '300000 PKR')
        result = await answer_follow_up(comparison, 'What if budget is $1000?')
        self.assertEqual(result.suggested_requirements_patch, [])
        result = await answer_follow_up(comparison, 'What if budget is under PKR 300000?')
        self.assertEqual(result.suggested_requirements_patch[0]['operator'], '<')
        result = await answer_follow_up(comparison, 'What if budget is PKR 1000 USD?')
        self.assertEqual(result.suggested_requirements_patch, [])
