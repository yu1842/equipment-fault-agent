"""运行配置：环境变量优先，其次 config.json，最后内置默认值。

设计原则：
1. 只使用标准库，避免用户为"改个模型名"去装依赖。
2. API Key 永不写入代码、永不进入版本库（config.json 已被 .gitignore 忽略）。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
EXPORT_DIR = PROJECT_ROOT / "exports"
CONFIG_FILE = PROJECT_ROOT / "config.json"

API_KEY_ENV_NAMES = ("EFA_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY")


@dataclass
class Settings:
    """Agent 运行参数。"""

    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    api_key: str = ""
    temperature: float = 0.2
    timeout: int = 60
    max_rounds: int = 6
    top_k: int = 3
    min_score: float = 0.22
    force_offline: bool = False
    kb_path: str = field(default_factory=lambda: str(DATA_DIR / "fault_cases.json"))

    # ---------- 读写 ----------

    @classmethod
    def load(cls) -> "Settings":
        settings = cls()
        if CONFIG_FILE.exists():
            try:
                raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                for key, value in raw.items():
                    if hasattr(settings, key) and value is not None:
                        setattr(settings, key, value)
            except (OSError, ValueError):
                # 配置文件损坏时不让程序起不来，退回默认值
                pass

        env_map = {
            "EFA_BASE_URL": "base_url",
            "EFA_MODEL": "model",
            "EFA_TIMEOUT": "timeout",
        }
        for env_name, attr in env_map.items():
            value = os.environ.get(env_name)
            if value:
                setattr(settings, attr, value)

        if os.environ.get("EFA_FORCE_OFFLINE", "").lower() in {"1", "true", "yes"}:
            settings.force_offline = True

        for env_name in API_KEY_ENV_NAMES:
            value = os.environ.get(env_name)
            if value and value.strip():
                settings.api_key = value.strip()
                break

        if not isinstance(settings.timeout, int):
            try:
                settings.timeout = int(settings.timeout)
            except (TypeError, ValueError):
                settings.timeout = 60
        try:
            settings.top_k = max(1, min(5, int(settings.top_k)))
            settings.max_rounds = max(1, min(12, int(settings.max_rounds)))
        except (TypeError, ValueError):
            settings.top_k, settings.max_rounds = 3, 6
        return settings

    def save(self) -> Path:
        """保存到 config.json（不含任何硬编码密钥的兜底逻辑）。"""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        CONFIG_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return CONFIG_FILE

    # ---------- 状态 ----------

    @property
    def online_ready(self) -> bool:
        return bool(self.api_key) and not self.force_offline

    @property
    def mode_label(self) -> str:
        return "在线模型" if self.online_ready else "离线规则"

    def masked_key(self) -> str:
        if not self.api_key:
            return "（未配置）"
        if len(self.api_key) <= 8:
            return "*" * len(self.api_key)
        return f"{self.api_key[:4]}****{self.api_key[-4:]}"
