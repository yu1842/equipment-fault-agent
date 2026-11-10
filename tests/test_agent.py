"""Agent 行为测试：正常问答、未覆盖问题、异常输入、模型不可用降级。"""

import unittest

from efa.agent import Agent
from efa.config import DATA_DIR, Settings
from efa.knowledge import KnowledgeBase


def offline_settings(**overrides) -> Settings:
    settings = Settings()
    settings.force_offline = True
    settings.api_key = ""
    settings.kb_path = str(DATA_DIR / "fault_cases.json")
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


class TestAgentOffline(unittest.TestCase):
    def setUp(self):
        self.agent = Agent(offline_settings())

    def test_normal_question_produces_answer_with_tool_calls(self):
        answer = self.agent.ask("数控车床主轴有异响，转速越高越明显")
        self.assertEqual(answer.mode, "offline")
        self.assertTrue(answer.ok)
        self.assertIn("EFA-002", answer.text)
        self.assertGreaterEqual(len(answer.tool_records), 1)
        self.assertTrue(all(r.ok for r in answer.tool_records))
        self.assertIn("EFA-002", answer.citations)

    def test_tool_call_record_contains_arguments(self):
        answer = self.agent.ask("变频器报过流跳闸")
        first = answer.tool_records[0]
        self.assertEqual(first.name, "search_fault_cases")
        self.assertIn("query", first.arguments)

    def test_uncovered_question_admits_missing_basis(self):
        answer = self.agent.ask("注塑机模具冷却水路堵塞，模温降不下来")
        self.assertIn("暂无该故障的案例依据", answer.text)
        self.assertNotIn("EFA-", answer.text.split("【判断】")[1].split("\n")[0])

    def test_empty_input_is_handled(self):
        answer = self.agent.ask("   ")
        self.assertEqual(answer.error, "empty_input")
        self.assertIn("请输入", answer.text)
        self.assertEqual(answer.tool_records, [])

    def test_broken_knowledge_base_is_reported(self):
        agent = Agent(offline_settings(kb_path="data/__missing__.json"))
        answer = agent.ask("液压站压力不足")
        self.assertEqual(answer.error, "kb_unavailable")
        self.assertIn("知识库未能加载", answer.text)

    def test_history_is_trimmed(self):
        for _ in range(10):
            self.agent.ask("液压站压力上不去")
        self.assertLessEqual(len(self.agent.history), Agent.MAX_HISTORY_MESSAGES)

    def test_reset_clears_history(self):
        self.agent.ask("液压站压力上不去")
        self.agent.reset()
        self.assertEqual(self.agent.history, [])


class TestAgentOnlineFallback(unittest.TestCase):
    """配置了无法连接的接口时，必须自动降级且仍然给出有依据的回答。"""

    def test_bad_endpoint_falls_back_to_offline(self):
        settings = offline_settings(
            force_offline=False,
            api_key="sk-test-invalid",
            base_url="http://127.0.0.1:9/v1",
            timeout=2,
        )
        answer = Agent(settings).ask("风机振动大，轴承温度高")
        self.assertEqual(answer.mode, "offline")
        self.assertTrue(answer.error.startswith("llm_failed"))
        self.assertIn("EFA-012", answer.text)
        self.assertIn("已自动切换", answer.text)


if __name__ == "__main__":
    unittest.main()
