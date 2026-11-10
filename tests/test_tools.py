"""工具层单元测试：参数校验、异常兜底、结构化返回。"""

import unittest

from efa.config import DATA_DIR
from efa.knowledge import KnowledgeBase
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


if __name__ == "__main__":
    unittest.main()
