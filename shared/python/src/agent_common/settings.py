import json
import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    kind: str
    jc_url: str = field(
        default_factory=lambda: os.getenv(
            "JC_URL", "http://localhost:8090/internal/v1"
        ).rstrip("/")
    )
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    llm_base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "").rstrip("/")
    )
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_routed: bool = False
    llm_request_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "300"))
    )
    llm_default_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("LLM_DEFAULT_MAX_TOKENS", "4096"))
    )
    llm_synthesis_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("LLM_SYNTHESIS_MAX_TOKENS", "16384"))
    )
    llm_insight_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("LLM_INSIGHT_MAX_TOKENS", "1024"))
    )
    llm_pricing_json: str = field(
        default_factory=lambda: os.getenv("LLM_PRICING_JSON", "{}")
    )
    artifact_dir: str = field(
        default_factory=lambda: os.getenv("ARTIFACT_DIR", ".local/artifacts")
    )
    config_path: str = field(
        default_factory=lambda: os.getenv(
            "AGENT_CONFIG_FILE", "agents/config.example.json"
        )
    )
    nat_config_file: str = field(
        default_factory=lambda: os.getenv("NAT_CONFIG_FILE", "")
    )

    def model_for(self, stage):
        if self.llm_routed:
            return self.llm_model
        return os.getenv("LLM_MODEL_" + stage.upper(), "") or self.llm_model

    def profile(self):
        with open(self.config_path, encoding="utf-8") as f:
            profile = json.load(f)
        for key in (
            "max_queries",
            "max_rows",
            "max_bytes",
            "max_range_seconds",
            "max_followups",
            "deadline_seconds",
        ):
            if profile["limits"][key] <= 0:
                raise ValueError("positive explicit deployment limits required")
        return profile
