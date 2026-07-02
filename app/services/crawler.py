"""网页正文提取服务 -- 从URL获取干净文本内容"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import quote, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from readability import Document

from app.config import settings

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    """标准化URL：对含中文的非ASCII路径自动编码"""
    parsed = urlparse(url)
    # 对路径和查询参数做编码，保留已编码的%
    encoded_path = quote(parsed.path, safe="/%")
    encoded_query = quote(parsed.query, safe="=&%")
    return urlunparse((
        parsed.scheme, parsed.netloc, encoded_path,
        parsed.params, encoded_query, parsed.fragment,
    ))


async def extract_content(url: str) -> Optional[str]:
    """从URL提取网页正文内容

    策略: 先用 readability 提取正文，失败则回退到 body 文本
    """
    url = _normalize_url(url)

    try:
        async with httpx.AsyncClient(timeout=settings.crawl_timeout) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
                follow_redirects=True,
            )
            resp.raise_for_status()

        html = resp.text
        if len(html) < 500:
            return None

        # 方法一：readability 提取正文
        doc = Document(html)
        summary_html = doc.summary()
        if summary_html:
            soup = BeautifulSoup(summary_html, "lxml")
            text = soup.get_text(separator="\n", strip=True)
            if len(text) > 200:
                return text[:settings.crawl_max_chars]

        # 方法二：回退到 body 纯文本
        soup = BeautifulSoup(html, "lxml")
        # 移除干扰元素
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        body = soup.find("body")
        if body:
            text = body.get_text(separator="\n", strip=True)
            # 清理多余空行
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            return "\n".join(lines)[:settings.crawl_max_chars]

        return None

    except httpx.TimeoutException:
        logger.warning(f"抓取超时: {url}")
        return None
    except Exception as e:
        logger.warning(f"抓取失败: {url} -- {e}")
        return None


async def batch_extract(urls: list[str], max_concurrent: int = 5) -> dict[str, Optional[str]]:
    """并发提取多个URL的正文，返回 {url: content} 字典"""
    import asyncio

    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded(url: str) -> tuple[str, Optional[str]]:
        async with semaphore:
            content = await extract_content(url)
            return url, content

    tasks = [bounded(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output: dict[str, Optional[str]] = {}
    for r in results:
        if isinstance(r, tuple):
            output[r[0]] = r[1]
        elif isinstance(r, Exception):
            logger.warning(f"并发提取异常: {r}")

    return output
