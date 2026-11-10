"""工具层单元测试：参数校验、异常兜底、结构化返回。"""

import unittest

from efa.config import DATA_DIR
from efa.knowledge import KnowledgeBase
from efa.project_kb import ProjectKB
from efa.tools import ToolRegistry


class TestToolRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ToolRegistry(KnowledgeBase(DATA_DIR / "fault_cases.json"))

    def test_specs_declare_three_tools(self):
        names = [item["function"]["name"] for item in self.registry.specs()]
        self.assertEqual(names, ["search_fault_cases", "get_case_detail", "list_equipment"])

    def test_search_returns_structured_hits(self):
        result, record = self.registry.execute(
            "search_fault_cases", '{"query": "空压机排气温度高"}'
        )
        self.assertTrue(record.ok)
        self.assertTrue(result["ok"])
        self.assertEqual(result["coverage"], "有依据")
        self.assertEqual(result["hits"][0]["case_id"], "EFA-003")

    def test_search_empty_query_is_rejected(self):
        result, record = self.registry.execute("search_fault_cases", {"query": "  "})
        self.assertFalse(record.ok)
        self.assertIn("为空", result["error"])

    def test_unknown_case_id_returns_error(self):
        result, record = self.registry.execute("get_case_detail", {"case_id": "EFA-404"})
        self.assertFalse(record.ok)
        self.assertIn("不存在", result["error"])

    def test_unknown_tool_returns_error(self):
        result, record = self.registry.execute("delete_all_cases", {})
        self.assertFalse(record.ok)
        self.assertIn("未定义", result["error"])

    def test_invalid_json_arguments_do_not_crash(self):
        result, record = self.registry.execute("search_fault_cases", "{not-json")
        self.assertFalse(record.ok)
        self.assertIn("error", result)

    def test_list_equipment(self):
        result, record = self.registry.execute("list_equipment", {})
        self.assertTrue(record.ok)
        self.assertGreaterEqual(result["count"], 5)

    def test_top_k_is_clamped(self):
        result, _ = self.registry.execute(
            "search_fault_cases", {"query": "报警", "top_k": 99}
        )
        self.assertLessEqual(len(result["hits"]), 5)


class TestProjectTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkb = ProjectKB(DATA_DIR / "project_kb.json")
        cls.registry = ToolRegistry(
            KnowledgeBase(DATA_DIR / "fault_cases.json"), project_kb=cls.pkb
        )

    def test_specs_expose_six_tools(self):
        names = [item["function"]["name"] for item in self.registry.specs()]
        self.assertEqual(len(names), 6)
        for required in (
            "search_fault_cases",
            "get_case_detail",
            "list_equipment",
            "search_project_kb",
            "get_kb_entry",
            "list_kb_categories",
        ):
            self.assertIn(required, names)

    def test_search_project_kb(self):
        result, record = self.registry.execute(
            "search_project_kb", {"query": "异常怎么降级"}
        )
        self.assertTrue(record.ok)
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["hit_count"], 1)
        self.assertTrue(result["hits"][0]["entry_id"].startswith("KB-"))

    def test_search_project_kb_with_category(self):
        result, _ = self.registry.execute(
            "search_project_kb", {"query": "参数", "category": "api"}
        )
        self.assertTrue(result["ok"])
        self.assertTrue(all(h["category"] == "api" for h in result["hits"]))

    def test_bad_category_is_rejected(self):
        result, record = self.registry.execute(
            "search_project_kb", {"query": "异常", "category": "unknown"}
        )
        self.assertFalse(record.ok)
        self.assertIn("分类不存在", result["error"])

    def test_get_kb_entry(self):
        result, record = self.registry.execute("get_kb_entry", {"entry_id": "kb-api-001"})
        self.assertTrue(record.ok)
        self.assertEqual(result["entry"]["id"], "KB-API-001")
        self.assertIn("inputs", result["entry"])
        self.assertTrue(result["entry"]["steps"])
        self.assertTrue(result["related"], "条目应返回关联条目，便于导航")

    def test_get_unknown_entry(self):
        result, record = self.registry.execute("get_kb_entry", {"entry_id": "KB-999"})
        self.assertFalse(record.ok)
        self.assertIn("不存在", result["error"])

    def test_list_kb_categories(self):
        result, record = self.registry.execute("list_kb_categories", {})
        self.assertTrue(record.ok)
        self.assertEqual(result["count"], 11)
        self.assertTrue(all(item["entries"] > 0 for item in result["categories"]))

    def test_registry_without_project_kb_hides_project_tools(self):
        plain = ToolRegistry(KnowledgeBase(DATA_DIR / "fault_cases.json"))
        names = [item["function"]["name"] for item in plain.specs()]
        self.assertEqual(len(names), 3)
        result, _ = plain.execute("search_project_kb", {"query": "配置"})
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
