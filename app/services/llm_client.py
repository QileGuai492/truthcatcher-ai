"""统一 LLM 客户端 -- 支持 Anthropic / DeepSeek / OpenAI 兼容接口"""

from __future__ import annotations

import logging
from enum import Enum

from app.config import settings

logger = logging.getLogger(__name__)


class Provider(str, Enum):
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    OPENAI_COMPATIBLE = "openai_compatible"


class LLMClient:
    """统一 LLM 调用封装"""

    def __init__(self):
        self.provider = self._detect_provider()

    def _detect_provider(self) -> Provider:
        """根据配置自动检测 Provider"""
        if settings.llm_provider:
            return Provider(settings.llm_provider)
        # 自动检测：有 Anthropic key 优先用 Anthropic
        if settings.anthropic_api_key:
            return Provider.ANTHROPIC
        if settings.deepseek_api_key:
            return Provider.DEEPSEEK
        if settings.openai_api_key and settings.openai_base_url:
            return Provider.OPENAI_COMPATIBLE
        return Provider.ANTHROPIC  # 默认

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        """发送对话请求，返回完整文本响应"""

        if self.provider == Provider.ANTHROPIC:
            return await self._chat_anthropic(system_prompt, user_prompt, max_tokens, temperature)
        else:
            return await self._chat_openai_compatible(system_prompt, user_prompt, max_tokens, temperature)

    async def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ):
        """流式对话，逐块 yield 文本增量"""
        if self.provider == Provider.ANTHROPIC:
            async for chunk in self._stream_anthropic(system_prompt, user_prompt, max_tokens, temperature):
                yield chunk
        else:
            async for chunk in self._stream_openai_compatible(system_prompt, user_prompt, max_tokens, temperature):
                yield chunk

    async def _chat_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text if response.content else ""

    async def _chat_openai_compatible(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        from openai import AsyncOpenAI

        # 根据 provider 选择 base_url 和 api_key
        if self.provider == Provider.DEEPSEEK:
            base_url = "https://api.deepseek.com"
            api_key = settings.deepseek_api_key
        else:
            base_url = settings.openai_base_url
            api_key = settings.openai_api_key

        client = AsyncOpenAI(base_url=base_url, api_key=api_key)

        response = await client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""


    async def _stream_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ):
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        async with client.messages.stream(
            model=settings.llm_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield event.delta.text

    async def _stream_openai_compatible(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ):
        from openai import AsyncOpenAI

        if self.provider == Provider.DEEPSEEK:
            base_url = "https://api.deepseek.com"
            api_key = settings.deepseek_api_key
        else:
            base_url = settings.openai_base_url
            api_key = settings.openai_api_key

        client = AsyncOpenAI(base_url=base_url, api_key=api_key)

        stream = await client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content


# 全局单例
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
