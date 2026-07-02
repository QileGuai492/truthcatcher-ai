"""网页正文提取服务 -- 从URL获取干净文本内容"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import quote, urlparse, urlunparse
import urllib3

import httpx

# 禁用 SSL 警告（某些网络环境下证书被替换）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from bs4 import BeautifulSoup
from readability import Document

from app.config import settings

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    """标准化URL：对含中文的非ASCII路径自动编码"""
    parsed = urlparse(url)
    encoded_path = quote(parsed.path, safe="/%")
    encoded_query = quote(parsed.query, safe="=&%")
    return urlunparse((
        parsed.scheme, parsed.netloc, encoded_path,
        parsed.params, encoded_query, parsed.fragment,
    ))


async def extract_content(url: str) -> Optional[str]:
    """从URL提取网页正文内容

    策略: httpx+readability → Jina Reader API（处理JS渲染页面）
    """
    url = _normalize_url(url)

    # 方法一：httpx 静态抓取
    text = await _extract_static(url)
    if text and len(text) > 200:
        return text[:settings.crawl_max_chars]

    # 方法二：Jina Reader API（免费，专门处理JS渲染页面如MSN）
    logger.info(f"静态抓取内容不足，尝试 Jina Reader: {url[:60]}")
    text = await _extract_jina(url)
    if text and len(text) > 200:
        return text[:settings.crawl_max_chars]

    # 方法三：Playwright 兜底
    logger.info(f"Jina Reader 失败，尝试 Playwright: {url[:60]}")
    text = await _extract_playwright(url)
    if text:
        return text[:settings.crawl_max_chars]

    return text


async def _extract_static(url: str) -> Optional[str]:
    """httpx + readability 静态提取"""
    try:
        async with httpx.AsyncClient(timeout=settings.crawl_timeout, verify=False) as client:
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

        doc = Document(html)
        summary_html = doc.summary()
        if summary_html:
            soup = BeautifulSoup(summary_html, "lxml")
            text = soup.get_text(separator="\n", strip=True)
            if len(text) > 200:
                return text

        # 回退1：找常见正文容器
        soup = BeautifulSoup(html, "lxml")
        for selector in ["article", "[class*=article]", "[class*=content]", "[class*=post]", "main", "[role=main]"]:
            el = soup.select_one(selector)
            if el:
                for tag in el(["script", "style", "nav"]):
                    tag.decompose()
                text = el.get_text(separator="\n", strip=True)
                if len(text) > 200:
                    return text

        # 回退2：全body文本
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        body = soup.find("body")
        if body:
            text = body.get_text(separator="\n", strip=True)
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            return "\n".join(lines) if lines else None

        return None

    except httpx.TimeoutException:
        logger.warning(f"抓取超时: {url}")
        return None
    except Exception as e:
        logger.warning(f"抓取失败: {url} -- {e}")
        return None


async def _extract_jina(url: str) -> Optional[str]:
    """通过 Jina Reader API 提取正文（免费，处理JS渲染页面）"""
    try:
        jina_url = f"https://r.jina.ai/{url}"
        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            resp = await client.get(
                jina_url,
                headers={"Accept": "text/markdown"},
            )
            resp.raise_for_status()
            text = resp.text
            if text and len(text) > 200:
                # Jina Reader 返回Markdown，直接清理
                import re
                text = re.sub(r'\[.*?\]\(.*?\)', '', text)  # 去掉markdown链接
                lines = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith("#")]
                return "\n".join(lines)
            return None
    except Exception as e:
        logger.warning(f"Jina Reader 失败: {e}")
        return None


async def _extract_playwright(url: str) -> Optional[str]:
    """Playwright 无头浏览器 JS 渲染提取"""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                locale="zh-CN",
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)
            html = await page.content()
            await browser.close()

        # 用同样的策略提取
        doc = Document(html)
        summary_html = doc.summary()
        if summary_html:
            soup = BeautifulSoup(summary_html, "lxml")
            text = soup.get_text(separator="\n", strip=True)
            if len(text) > 200:
                return text

        soup = BeautifulSoup(html, "lxml")
        for selector in ["article", "[class*=article]", "[class*=content]", "[class*=post]", "main"]:
            el = soup.select_one(selector)
            if el:
                for tag in el(["script", "style", "nav"]):
                    tag.decompose()
                text = el.get_text(separator="\n", strip=True)
                if len(text) > 200:
                    return text

        return None

    except ImportError:
        logger.warning("Playwright 未安装，跳过JS渲染。安装: pip install playwright && playwright install chromium")
        return None
    except Exception as e:
        logger.warning(f"Playwright 抓取失败: {url} -- {e}")
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
