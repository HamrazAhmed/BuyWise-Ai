"""Grounded discovery must reject unrelated or unsupported product claims."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from data.online import SearchProducts, checked_products, source_segments
from agents.research import select_candidates
from agents.matching import match_requirement
from models.product import Spec
from models.request import Requirement

class OnlineTests(unittest.TestCase):
    def test_claims_require_same_identity_and_literal_evidence(self):
        segments = [{'text': 'Dell G16 7630 brand Dell GPU NVIDIA RTX 5060 8 GB RAM 16 GB',
                     'sources': [{'url': 'https://www.dell.com/laptops', 'title': 'Dell'}]}]
        data = {'name': 'Invented marketing name', 'brand': 'Dell', 'model_number': 'G16 7630',
                'facts': [{'key': 'brand', 'value': 'Dell', 'segment': 0},
                          {'key': 'gpu', 'value': 'NVIDIA RTX 5060 8 GB', 'segment': 0},
                          {'key': 'storage', 'value': '2 TB', 'segment': 0}]}
        products, chunks = checked_products(SearchProducts(products=[data]), segments)
        self.assertEqual(products[0]['name'], 'Dell G16 7630')
        self.assertNotIn('storage', products[0]['specs'])
        self.assertEqual(chunks[0].origin, 'search')
        self.assertEqual(chunks[0].fetched_at, '')
        data['model_number'] = 'Alienware 9999'
        self.assertEqual(checked_products(SearchProducts(products=[data]), segments), ([], []))

    def test_unapproved_sources_and_invalid_indices_are_rejected(self):
        result = {'metadata': {'grounding_chunks': [{'web': {'uri': 'http://127.0.0.1/admin'}}],
                  'grounding_supports': [{'segment': {'text': 'Dell G16 GPU RTX 5060'},
                                          'grounding_chunk_indices': [0, -1, True, 50]}]}}
        self.assertEqual(source_segments(result), [])

    def test_required_gpu_vram_and_brand_are_not_relaxed(self):
        requirements = [Requirement(key='brand', operator='=', value='Dell', priority='must'),
                        Requirement(key='gpu', operator='=', value='RTX 5060', priority='must'),
                        Requirement(key='vram', operator='>=', value='8 GB', priority='must')]
        good = {'id': 'dell', 'brand': 'Dell', 'specs': {'gpu': 'NVIDIA RTX 5060 8 GB', 'vram': '8 GB'}}
        wrong = {'id': 'hp', 'brand': 'HP', 'specs': good['specs']}
        self.assertEqual([p['id'] for p in select_candidates([wrong, good], requirements)], ['dell'])
        self.assertEqual(select_candidates([wrong], requirements), [])
        spec = Spec(key='gpu', value='RTX 5060 Ti 8 GB', status='supported', evidence_ids=['source'])
        self.assertEqual(match_requirement(requirements[1], [spec])[0], '✕')
