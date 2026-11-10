"""界面测试：窗口可构建、控件尺寸正常、回答渲染链路可用。

无 Tkinter 的环境自动跳过，避免 CI 失败。
"""

import unittest

try:
    import tkinter  # noqa: F401

    HAS_TK = True
except ImportError:  # pragma: no cover
    HAS_TK = False


@unittest.skipUnless(HAS_TK, "当前 Python 未包含 Tkinter")
class TestMainWindow(unittest.TestCase):
    def setUp(self):
        from efa.ui import FaultAgentApp

        self.app = FaultAgentApp()
        self.app.update_idletasks()
        self.app.update()

    def tearDown(self):
        try:
            self.app.destroy()
        except Exception:  # noqa: BLE001
            pass

    def test_kb_tree_matches_knowledge_base(self):
        self.assertEqual(len(self.app.kb_tree.get_children()), len(self.app.agent.kb))

    def test_layout_has_positive_size(self):
        self.assertGreaterEqual(self.app.winfo_width(), 900)
        self.assertGreater(self.app.chat.winfo_width(), 300)
        self.assertGreater(self.app.chat.winfo_height(), 150)
        self.assertGreater(self.app.input.winfo_height(), 30)

    def test_render_answer_fills_tool_panel(self):
        answer = self.app.agent.ask("液压站压力上不去")
        self.app._render_answer(answer)
        self.assertGreater(len(self.app.tool_tree.get_children()), 0)
        content = self.app.chat.get("1.0", "end")
        self.assertIn("故障助手", content)
        self.assertIn("EFA-001", content)

    def test_clear_chat_resets_panels(self):
        answer = self.app.agent.ask("皮带输送机跑偏")
        self.app._render_answer(answer)
        self.app.clear_chat()
        self.assertEqual(len(self.app.tool_tree.get_children()), 0)
        self.assertEqual(self.app.chat.get("1.0", "end").strip(), "")


if __name__ == "__main__":
    unittest.main()
