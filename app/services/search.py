"""搜索引擎服务 -- 多引擎并发检索（SerpAPI主 + DuckDuckGo备 + Bing可选）"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx
from serpapi import GoogleSearch

from app.config import settings
from app.models.analysis import SearchResult, SourceLevel

logger = logging.getLogger(__name__)


async def search_serpapi(query: str, num: int = 10) -> list[SearchResult]:
    """通过 SerpAPI 搜索 Google（支持中文，需要 API Key）"""
    if not settings.serpapi_key:
        return []

    try:
        params = {
            "q": query,
            "hl": "zh-CN",
            "gl": "cn",
            "num": min(num, 10),
            "api_key": settings.serpapi_key,
        }
        loop = asyncio.get_running_loop()
        search = GoogleSearch(params)
        results_dict = await loop.run_in_executor(None, search.get_dict)

        results: list[SearchResult] = []
        for r in results_dict.get("organic_results", [])[:num]:
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("link", ""),
                snippet=r.get("snippet", ""),
                source_name=r.get("source", ""),
                published_date=r.get("date"),
                source_level=SourceLevel.UNKNOWN,
            ))
        return results

    except Exception as e:
        logger.warning(f"SerpAPI 搜索失败 (query={query[:50]}): {e}")
        return []


async def search_duckduckgo(query: str, num: int = 10) -> list[SearchResult]:
    """通过 DuckDuckGo 搜索（免费，无需 API Key）"""
    try:
        from duckduckgo_search import DDGS

        loop = asyncio.get_running_loop()
        raw_results = await loop.run_in_executor(
            None,
            lambda: list(DDGS().text(query, region="cn-zh", max_results=num)),
        )

        results: list[SearchResult] = []
        for r in raw_results[:num]:
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("href", ""),
                snippet=r.get("body", ""),
                source_name="",
                published_date=r.get("date"),
                source_level=SourceLevel.UNKNOWN,
            ))
        return results

    except ImportError:
        logger.debug("duckduckgo_search 未安装，跳过 DuckDuckGo")
        return []
    except Exception as e:
        logger.warning(f"DuckDuckGo 搜索失败 (query={query[:50]}): {e}")
        return []


async def search_bing(query: str, num: int = 10) -> list[SearchResult]:
    """通过 Bing Web Search API 搜索（备用，需要 Azure Key）"""
    if not settings.bing_search_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=settings.search_timeout) as client:
            resp = await client.get(
                "https://api.bing.microsoft.com/v7.0/search",
                params={"q": query, "count": num, "mkt": "zh-CN"},
                headers={"Ocp-Apim-Subscription-Key": settings.bing_search_key},
            )
            resp.raise_for_status()
            data = resp.json()

        results: list[SearchResult] = []
        for r in data.get("webPages", {}).get("value", [])[:num]:
            results.append(SearchResult(
                title=r.get("name", ""),
                url=r.get("url", ""),
                snippet=r.get("snippet", ""),
                source_name=r.get("name", ""),
                published_date=r.get("dateLastCrawled"),
                source_level=SourceLevel.UNKNOWN,
            ))
        return results

    except Exception as e:
        logger.warning(f"Bing 搜索失败 (query={query[:50]}): {e}")
        return []


async def multi_search(queries: list[str], results_per_query: int = 5) -> list[SearchResult]:
    """多关键词并发搜索，去重合并（SerpAPI + DuckDuckGo + Bing）"""
    all_tasks = []
    for q in queries:
        all_tasks.append(search_serpapi(q, results_per_query))

    nested = await asyncio.gather(*all_tasks, return_exceptions=True)

    seen_urls: set[str] = set()
    merged: list[SearchResult] = []
    for result_list in nested:
        if not isinstance(result_list, list):
            continue
        for r in result_list:
            normalized = r.url.rstrip("/").lower()
            if normalized not in seen_urls:
                seen_urls.add(normalized)
                merged.append(r)

    return merged


async def generate_search_queries(news_content: str) -> list[str]:
    """根据新闻内容，由 LLM 生成多组搜索关键词"""
    from app.services.llm_client import get_llm_client

    llm = get_llm_client()

    system_prompt = "你是一个专业的信息检索专家，擅长生成精准的搜索关键词。只输出搜索关键词，每行一个，不要编号或其他内容。"

    user_prompt = f"""根据以下新闻内容，生成搜索关键词用于检索验证。

要求：
- 生成3-4组中文关键词 + 3-4组英文关键词
- 英文关键词用英文写，用于在Google/Bing上搜索英文信息来源
- 覆盖：核心主张、关键参与方、权威来源声明、反对/质疑、时间地点背景

新闻内容：
---
{news_content[:2000]}
---

每行一组关键词，中英文混排，不要编号。"""

    try:
        text = await llm.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=600,
            temperature=settings.llm_search_temperature,
        )

        queries = [line.strip() for line in text.strip().split("\n") if line.strip()]
        queries = [q.lstrip("0123456789.-)） ") for q in queries if len(q) > 3]
        logger.info(f"生成搜索关键词 (中+英): {queries}")
        return queries[:10]

    except Exception as e:
        logger.error(f"生成搜索关键词失败: {e}")
        # 回退：直接用原新闻内容作为搜索词（取前200字符）
        return [news_content[:200]]
