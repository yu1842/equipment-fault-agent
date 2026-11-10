"""知识库与检索的单元测试。"""

import unittest
from pathlib import Path

from efa.config import DATA_DIR
from efa.knowledge import KnowledgeBase, bigrams, dice, normalize

KB_PATH = DATA_DIR / "fault_cases.json"


class TestKnowledgeBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase(KB_PATH)

    def test_loads_at_least_five_cases(self):
        self.assertEqual(self.kb.load_error, "")
        self.assertGreaterEqual(len(self.kb), 5)

    def test_case_required_fields(self):
        for case in self.kb.cases:
            self.assertTrue(case.id)
            self.assertTrue(case.equipment)
            self.assertTrue(case.symptom)
            self.assertGreaterEqual(len(case.causes), 1)
            self.assertGreaterEqual(len(case.steps), 1)

    def test_equipment_names_unique(self):
        names = self.kb.equipment_names()
        self.assertEqual(len(names), len(set(names)))

    def test_search_hydraulic_ranks_efa001(self):
        hits = self.kb.search("液压站压力上不去，油缸动作无力", top_k=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0].case.id, "EFA-001")
        self.assertGreater(hits[0].score, 0.4)

    def test_search_uncovered_returns_empty(self):
        hits = self.kb.search("注塑机模具冷却水路堵塞", top_k=3)
        self.assertEqual(hits, [])

    def test_search_empty_query(self):
        self.assertEqual(self.kb.search("   "), [])

    def test_get_case_by_id(self):
        case = self.kb.get("efa-001")
        self.assertIsNotNone(case)
        self.assertEqual(case.equipment, "液压站")
        self.assertIsNone(self.kb.get("EFA-999"))

    def test_missing_kb_file_is_reported(self):
        kb = KnowledgeBase(Path("data/__not_exists__.json"))
        self.assertEqual(len(kb), 0)
        self.assertIn("不存在", kb.load_error)


class TestTextUtils(unittest.TestCase):
    def test_normalize_strips_punctuation(self):
        self.assertEqual(normalize("液压站，压力上不去！"), "液压站压力上不去")

    def test_dice_similarity(self):
        self.assertEqual(dice(bigrams("液压站压力"), bigrams("液压站压力")), 1.0)
        self.assertEqual(dice(bigrams("液压站"), bigrams("激光切割")), 0.0)


if __name__ == "__main__":
    unittest.main()
