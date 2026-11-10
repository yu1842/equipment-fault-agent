"""项目知识库测试：结构完整性、检索行为、与源码的一致性。

最后一组用例会故意篡改副本中的条目，验证校验器确实能发现“文档与代码漂移”，
避免校验器本身变成永远通过的摆设。
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from efa.config import DATA_DIR
from efa.kbcheck import verify
from efa.project_kb import ProjectKB

ROOT = Path(__file__).resolve().parents[1]
KB_PATH = DATA_DIR / "project_kb.json"


class TestProjectKBStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = ProjectKB(KB_PATH)
        cls.raw = json.loads(KB_PATH.read_text(encoding="utf-8"))

    def test_loads_without_error(self):
        self.assertEqual(self.kb.load_error, "")
        self.assertGreaterEqual(len(self.kb), 30)

    def test_categories_resolve(self):
        stats = self.kb.category_stats()
        self.assertEqual(len(stats), len(self.raw["categories"]))
        self.assertEqual(sum(item["entries"] for item in stats), len(self.kb))

    def test_ids_unique_and_prefixed(self):
        ids = [e.id for e in self.kb.entries]
        self.assertEqual(len(ids), len(set(ids)))
        for entry in self.kb.entries:
            self.assertTrue(entry.id.startswith("KB-"), entry.id)

    def test_required_content_present(self):
        for entry in self.kb.entries:
            self.assertTrue(entry.title, entry.id)
            self.assertTrue(entry.summary, entry.id)
            self.assertTrue(entry.when_to_use, f"{entry.id} 缺少调用条件")
            self.assertTrue(entry.cautions, f"{entry.id} 缺少注意事项")
            self.assertTrue(entry.scope, f"{entry.id} 缺少适用范围")
            self.assertTrue(entry.version, f"{entry.id} 缺少版本约束")

    def test_every_category_has_entries(self):
        for item in self.kb.category_stats():
            self.assertGreater(item["entries"], 0, f"分类 {item['id']} 为空")


class TestProjectKBSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = ProjectKB(KB_PATH)

    def test_symbol_query_hits_module_entry(self):
        hits = self.kb.search("ToolRegistry 怎么扩展", top_k=3)
        self.assertTrue(hits)
        ids = [h.entry.id for h in hits]
        self.assertIn("KB-ARCH-003", ids)

    def test_natural_language_query(self):
        hits = self.kb.search("配置的优先级是怎么定的", top_k=3)
        self.assertTrue(hits)
        self.assertIn("config", [h.entry.category for h in hits])

    def test_category_filter(self):
        hits = self.kb.search("异常", category="error", top_k=3)
        self.assertTrue(hits)
        self.assertTrue(all(h.entry.category == "error" for h in hits))

    def test_unknown_category_returns_empty(self):
        self.assertEqual(self.kb.search("异常", category="not-exist"), [])

    def test_empty_query_returns_empty(self):
        self.assertEqual(self.kb.search("  "), [])

    def test_get_is_case_insensitive(self):
        self.assertIsNotNone(self.kb.get("kb-api-001"))
        self.assertIsNotNone(self.kb.get("KB-API-001"))
        self.assertIsNone(self.kb.get("KB-999"))

    def test_missing_file_is_reported(self):
        kb = ProjectKB(Path("data/__no_project_kb__.json"))
        self.assertEqual(len(kb), 0)
        self.assertIn("不存在", kb.load_error)


class TestConsistencyWithCode(unittest.TestCase):
    def test_no_drift_in_repository(self):
        issues, summary = verify(ROOT)
        errors = [str(i) for i in issues if i.level == "E"]
        self.assertEqual(errors, [], f"知识库与源码不一致：{errors}")
        self.assertGreater(summary["entries"], 30)

    def test_checker_detects_signature_drift(self):
        """篡改副本参数名，校验器必须报 BAD_SIGNATURE。"""
        tmp = Path(tempfile.mkdtemp(prefix="efa-kbcheck-"))
        try:
            shutil.copytree(ROOT / "src", tmp / "src")
            shutil.copy(ROOT / "app.py", tmp / "app.py")
            (tmp / "data").mkdir()
            shutil.copy(KB_PATH, tmp / "data" / "project_kb.json")
            shutil.copy(DATA_DIR / "fault_cases.json", tmp / "data" / "fault_cases.json")

            raw = json.loads((tmp / "data" / "project_kb.json").read_text(encoding="utf-8"))
            for entry in raw["entries"]:
                if entry["id"] == "KB-API-001":
                    entry["signature"] = "ask(self, prompt: str) -> Answer"
            (tmp / "data" / "project_kb.json").write_text(
                json.dumps(raw, ensure_ascii=False), encoding="utf-8"
            )

            issues, _ = verify(tmp)
            codes = {i.code for i in issues}
            self.assertIn("BAD_SIGNATURE", codes)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_checker_detects_missing_symbol(self):
        tmp = Path(tempfile.mkdtemp(prefix="efa-kbcheck-"))
        try:
            shutil.copytree(ROOT / "src", tmp / "src")
            shutil.copy(ROOT / "app.py", tmp / "app.py")
            (tmp / "data").mkdir()
            shutil.copy(KB_PATH, tmp / "data" / "project_kb.json")
            shutil.copy(DATA_DIR / "fault_cases.json", tmp / "data" / "fault_cases.json")

            raw = json.loads((tmp / "data" / "project_kb.json").read_text(encoding="utf-8"))
            for entry in raw["entries"]:
                if entry["id"] == "KB-MOD-005":
                    entry["symbol"] = "Agent.does_not_exist"
            (tmp / "data" / "project_kb.json").write_text(
                json.dumps(raw, ensure_ascii=False), encoding="utf-8"
            )

            issues, _ = verify(tmp)
            self.assertIn("BAD_SYMBOL", {i.code for i in issues})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
