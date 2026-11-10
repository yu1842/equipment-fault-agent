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


class TestContentCompleteness(unittest.TestCase):
    """v2.0 新增字段的完整性：背景、步骤、排障、最佳实践、交叉引用。"""

    @classmethod
    def setUpClass(cls):
        cls.kb = ProjectKB(KB_PATH)

    def test_every_entry_has_v2_fields(self):
        for entry in self.kb.entries:
            self.assertTrue(entry.aliases, f"{entry.id} 缺别名")
            self.assertGreaterEqual(len(entry.background), 12, f"{entry.id} 背景过短")
            self.assertGreaterEqual(len(entry.steps), 2, f"{entry.id} 缺实操步骤")
            self.assertGreaterEqual(len(entry.troubleshooting), 1, f"{entry.id} 缺排障项")
            self.assertGreaterEqual(len(entry.best_practices), 2, f"{entry.id} 缺最佳实践")
            self.assertGreaterEqual(len(entry.related), 2, f"{entry.id} 缺交叉引用")

    def test_troubleshooting_items_are_actionable(self):
        for entry in self.kb.entries:
            for item in entry.troubleshooting:
                for key in ("symptom", "check", "fix"):
                    self.assertTrue(str(item.get(key, "")).strip(), f"{entry.id} 排障项缺 {key}")

    def test_related_is_symmetric(self):
        for entry in self.kb.entries:
            for rid in entry.related:
                target = self.kb.get(rid)
                self.assertIsNotNone(target, f"{entry.id} 的 related 指向不存在的 {rid}")
                self.assertIn(entry.id, target.related, f"{entry.id} 与 {rid} 未双向引用")
                self.assertNotEqual(entry.id, rid, f"{entry.id} 引用了自己")

    def test_stats_coverage_is_full(self):
        stats = self.kb.stats()
        self.assertEqual(stats["entries"], len(self.kb))
        for name, ratio in stats["coverage"].items():
            self.assertEqual(ratio, 1.0, f"{name} 覆盖率不足")

    def test_guide_category_present(self):
        stats = {item["id"]: item for item in self.kb.category_stats()}
        self.assertIn("guide", stats)
        self.assertGreaterEqual(stats["guide"]["entries"], 5)

    def test_related_entries_resolves(self):
        entry = self.kb.get("KB-ARCH-001")
        related = self.kb.related_entries(entry)
        self.assertTrue(related)
        self.assertTrue(all(item.id.startswith("KB-") for item in related))

    def test_alias_and_symptom_search(self):
        """别名与排障症状都应能命中，验证两步扩召回生效。"""
        alias_hits = self.kb.search("怎么加功能", top_k=3)
        self.assertTrue(alias_hits)
        self.assertIn("KB-ARCH-003", [h.entry.id for h in alias_hits])

        symptom_hits = self.kb.search("打不开程序怎么办", top_k=3)
        self.assertTrue(symptom_hits)
        self.assertEqual(symptom_hits[0].entry.id, "KB-GUIDE-003")


class TestIndexSync(unittest.TestCase):
    """索引与数据必须同版本，且不改变检索结果。"""

    def test_index_is_fresh(self):
        kb = ProjectKB(KB_PATH)
        self.assertEqual(kb.index_status, "fresh")
        self.assertGreater(kb.stats()["index_terms"], 1000)

    def test_index_matches_linear_search(self):
        indexed = ProjectKB(KB_PATH)
        linear = ProjectKB(KB_PATH)
        linear._postings = None  # 强制线性扫描
        for query in ("打不开程序怎么办", "配置优先级", "新增工具", "校验错误码", "日志格式"):
            a = indexed.search(query, top_k=3)
            b = linear.search(query, top_k=3)
            self.assertEqual([h.entry.id for h in a], [h.entry.id for h in b], query)

    def test_stale_index_is_detected(self):
        tmp = Path(tempfile.mkdtemp(prefix="efa-index-"))
        try:
            shutil.copy(KB_PATH, tmp / "project_kb.json")
            shutil.copy(DATA_DIR / "kb_index.json", tmp / "kb_index.json")
            # 只改数据、不重建索引 -> 状态应为 stale，且仍能线性检索
            raw = json.loads((tmp / "project_kb.json").read_text(encoding="utf-8"))
            raw["updated_at"] = "2099-01-01"
            (tmp / "project_kb.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            kb = ProjectKB(tmp / "project_kb.json")
            self.assertEqual(kb.index_status, "stale")
            self.assertIsNone(kb._postings)
            self.assertTrue(kb.search("索引", top_k=1))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_index_falls_back(self):
        tmp = Path(tempfile.mkdtemp(prefix="efa-index-"))
        try:
            shutil.copy(KB_PATH, tmp / "project_kb.json")
            kb = ProjectKB(tmp / "project_kb.json")
            self.assertEqual(kb.index_status, "missing")
            self.assertTrue(kb.search("异常降级", top_k=1))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestMaintenanceResult(unittest.TestCase):
    """v2.1 维护结果：新增在、删除不在、全部可检索。"""

    @classmethod
    def setUpClass(cls):
        cls.kb = ProjectKB(KB_PATH)

    def test_new_entries_present(self):
        for eid in ("KB-API-014", "KB-DATA-007", "KB-ERR-005", "KB-CONV-006", "KB-DEP-005", "KB-GUIDE-007"):
            self.assertIsNotNone(self.kb.get(eid), f"缺少新增条目 {eid}")

    def test_deleted_entries_absent(self):
        for eid in ("KB-DATA-002", "KB-DATA-005"):
            self.assertIsNone(self.kb.get(eid), f"应已删除 {eid}，内容应并入目标条目")
        merged = self.kb.get("KB-API-003")
        self.assertIn("SearchHit", " ".join(merged.aliases) + merged.outputs)

    def test_every_entry_searchable(self):
        missing = []
        for entry in self.kb.entries:
            hits = self.kb.search(entry.title, top_k=1)
            if not hits or hits[0].entry.id != entry.id:
                missing.append(entry.id)
        self.assertEqual(missing, [], f"以下条目用标题检索不到自己：{missing}")


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


    def test_checker_detects_dangling_related(self):
        tmp = Path(tempfile.mkdtemp(prefix="efa-kbcheck-"))
        try:
            shutil.copytree(ROOT / "src", tmp / "src")
            shutil.copy(ROOT / "app.py", tmp / "app.py")
            (tmp / "data").mkdir()
            shutil.copy(KB_PATH, tmp / "data" / "project_kb.json")
            shutil.copy(DATA_DIR / "fault_cases.json", tmp / "data" / "fault_cases.json")

            raw = json.loads((tmp / "data" / "project_kb.json").read_text(encoding="utf-8"))
            for entry in raw["entries"]:
                if entry["id"] == "KB-ARCH-001":
                    entry["related"] = ["KB-NOT-EXIST"]
                    entry["version"] = "1.0"
            (tmp / "data" / "project_kb.json").write_text(
                json.dumps(raw, ensure_ascii=False), encoding="utf-8"
            )

            codes = {i.code for i in verify(tmp)[0]}
            self.assertIn("DANGLING_RELATED", codes)
            self.assertIn("BAD_VERSION", codes)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
