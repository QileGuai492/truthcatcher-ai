"""应用配置管理 -- 从环境变量加载配置"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


class Settings:
    """全局配置单例"""

    # -- LLM Provider --
    llm_provider: str = os.getenv("LLM_PROVIDER", "")  # anthropic / deepseek / openai_compatible

    # -- Anthropic --
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # -- DeepSeek --
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")

    # -- OpenAI 兼容接口 --
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")

    # -- 模型配置 --
    llm_model: str = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    llm_max_tokens: int = 8192
    llm_temperature: float = 0.0  # 分析用温度：0=确定性输出，避免结果离散
    llm_search_temperature: float = 0.3  # 搜索关键词生成用温度：可稍高

    # -- 搜索配置 --
    serpapi_key: str = os.getenv("SERPAPI_KEY", "")
    bing_search_key: str = os.getenv("BING_SEARCH_KEY", "")
    search_max_results: int = 10
    search_timeout: int = 15

    # -- 正文提取配置 --
    crawl_timeout: int = 10
    crawl_max_chars: int = 8000

    # -- 服务配置 --
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "7860"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # -- 验证 --
    def is_configured(self) -> bool:
        return bool(self._get_active_api_key() and self.serpapi_key)

    def missing_keys(self) -> list[str]:
        missing = []
        if not self._get_active_api_key():
            provider = self.llm_provider or "anthropic"
            if provider == "deepseek":
                missing.append("DEEPSEEK_API_KEY")
            elif provider == "openai_compatible":
                missing.append("OPENAI_API_KEY")
            else:
                missing.append("ANTHROPIC_API_KEY")
        if not self.serpapi_key:
            missing.append("SERPAPI_KEY")
        return missing

    def _get_active_api_key(self) -> str:
        """根据当前 provider 返回对应的 API Key"""
        provider = self.llm_provider
        if provider == "deepseek":
            return self.deepseek_api_key
        if provider == "openai_compatible":
            return self.openai_api_key
        return self.anthropic_api_key


settings = Settings()
