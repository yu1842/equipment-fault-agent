"""案例知识库测试：结构完整性、质量门禁、可检索性与索引同步。"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from efa.config import DATA_DIR
from efa.casecheck import verify as verify_cases
from efa.knowledge import KnowledgeBase

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = DATA_DIR / "fault_cases.json"


class TestCaseStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase(CASES_PATH)
        cls.raw = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    def test_case_count_and_equipment(self):
        self.assertGreaterEqual(len(self.kb), 20)
        self.assertGreaterEqual(len(self.kb.equipment_names()), 15)

    def test_ids_unique_and_formatted(self):
        ids = [c.id for c in self.kb.cases]
        self.assertEqual(len(ids), len(set(ids)))
        for cid in ids:
            self.assertRegex(cid, r"^EFA-\d{3}$")

    def test_required_fields_filled(self):
        for case in self.kb.cases:
            self.assertTrue(case.equipment, case.id)
            self.assertTrue(case.symptom, case.id)
            self.assertGreaterEqual(len(case.causes), 2, case.id)
            self.assertGreaterEqual(len(case.steps), 4, case.id)
            self.assertGreaterEqual(len(case.keywords), 4, case.id)
            self.assertIn(case.risk, ("高", "中", "低"), case.id)
            self.assertTrue(case.source, case.id)

    def test_id_matches_position_order(self):
        """案例按编号排序存放，便于人工翻阅。"""
        ids = [c.id for c in self.kb.cases]
        self.assertEqual(ids, sorted(ids))


class TestCaseQuality(unittest.TestCase):
    def test_verify_reports_no_error(self):
        issues, summary = verify_cases(ROOT)
        errors = [str(i) for i in issues if i.level == "E"]
        self.assertEqual(errors, [], f"案例库存在错误：{errors}")
        self.assertGreaterEqual(summary["cases"], 20)

    def test_every_case_searchable(self):
        kb = KnowledgeBase(CASES_PATH)
        missing = []
        for case in kb.cases:
            hits = kb.search(case.symptom, top_k=1)
            if not hits or hits[0].case.id != case.id:
                missing.append(case.id)
        self.assertEqual(missing, [], f"以下案例用自身现象检索不到：{missing}")

    def test_new_cases_present(self):
        kb = KnowledgeBase(CASES_PATH)
        for cid in ("EFA-013", "EFA-014", "EFA-015", "EFA-016", "EFA-017",
                    "EFA-018", "EFA-019", "EFA-020", "EFA-021", "EFA-022",
                    "EFA-023", "EFA-024"):
            self.assertIsNotNone(kb.get(cid), f"缺少新增案例 {cid}")

    def test_general_ops_cases(self):
        kb = KnowledgeBase(CASES_PATH)
        faq = [c for c in kb.cases if c.equipment == "通用运维"]
        self.assertGreaterEqual(len(faq), 4, "通用运维问答类案例不足")

    def test_covers_new_equipment(self):
        names = set(KnowledgeBase(CASES_PATH).equipment_names())
        for name in ("注塑机", "六轴工业机器人", "AGV 搬运机器人", "桥式起重机", "循环水泵", "伺服驱动器"):
            self.assertIn(name, names)


class TestCaseIndex(unittest.TestCase):
    def test_case_index_fresh(self):
        kb = KnowledgeBase(CASES_PATH)
        self.assertEqual(kb.index_status, "fresh")

    def test_index_matches_linear_search(self):
        indexed = KnowledgeBase(CASES_PATH)
        linear = KnowledgeBase(CASES_PATH)
        linear._postings = None
        for query in ("液压站压力上不去", "注塑机模温", "AGV 原地打转", "点检周期", "压缩空气含水"):
            a = [h.case.id for h in indexed.search(query, top_k=3)]
            b = [h.case.id for h in linear.search(query, top_k=3)]
            self.assertEqual(a, b, query)

    def test_stale_case_index_detected(self):
        tmp = Path(tempfile.mkdtemp(prefix="efa-case-index-"))
        try:
            shutil.copy(CASES_PATH, tmp / "fault_cases.json")
            shutil.copy(DATA_DIR / "case_index.json", tmp / "case_index.json")
            raw = json.loads((tmp / "fault_cases.json").read_text(encoding="utf-8"))
            raw["updated_at"] = "2099-01-01"
            (tmp / "fault_cases.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            kb = KnowledgeBase(tmp / "fault_cases.json")
            self.assertEqual(kb.index_status, "stale")
            self.assertIsNone(kb._postings)
            self.assertTrue(kb.search("液压站", top_k=1))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
