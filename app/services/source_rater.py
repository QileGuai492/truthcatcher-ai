"""信源可信度评级服务 -- 对搜索结果进行可信度评估"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from app.models.analysis import SearchResult, SourceLevel

logger = logging.getLogger(__name__)

# ============================================================
# 已知域名评级规则
# ============================================================

# A级：官方政府、权威学术
LEVEL_A_DOMAINS = {
    "gov.cn", "gov.hk", "gov.mo",
    "nasa.gov", "who.int", "un.org", "worldbank.org",
    "nature.com", "science.org", "cell.com", "lancet.com",
    "pnas.org", "springer.com", "ieee.org", "acm.org",
    "xinhuanet.com", "people.com.cn", "cctv.com", "chinadaily.com.cn",
    "cns.cn", "gmw.cn", "youth.cn",
}

# B级：知名正规媒体
LEVEL_B_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
    "nytimes.com", "washingtonpost.com", "wsj.com", "economist.com",
    "theguardian.com", "bloomberg.com", "cnn.com", "npr.org",
    "sina.com.cn", "qq.com", "sohu.com", "163.com", "ifeng.com",
    "thepaper.cn", "caixin.com", "jiemian.com", "huxiu.com",
    "ft.com", "dw.com", "france24.com", "aljazeera.com",
    "nikkei.com", "nhk.or.jp",
}

# C级：中小媒体、行业博客
LEVEL_C_DOMAINS = {
    "36kr.com", "geekpark.net", "pingwest.com", "leiphone.com",
    "ithome.com", "cnbeta.com", "donews.com",
    "zhihu.com", "jianshu.com", "csdn.net", "juejin.cn",
    "medium.com", "substack.com",
}

# 已知不可靠/造谣网站（D级）
LEVEL_D_DOMAINS = set()


def rate_single_result(result: SearchResult) -> SearchResult:
    """对单条搜索结果进行信源评级"""
    url = result.url
    domain = _extract_domain(url).lower()

    if domain in LEVEL_A_DOMAINS:
        result.source_level = SourceLevel.A
    elif domain in LEVEL_B_DOMAINS:
        result.source_level = SourceLevel.B
    elif domain in LEVEL_C_DOMAINS:
        result.source_level = SourceLevel.C
    elif domain in LEVEL_D_DOMAINS:
        result.source_level = SourceLevel.D
    else:
        # 根据域名特征推断
        result.source_level = _infer_level_from_domain(domain)

    if not result.source_name:
        result.source_name = domain

    return result


def rate_all(results: list[SearchResult]) -> list[SearchResult]:
    """批量评级"""
    return [rate_single_result(r) for r in results]


def _extract_domain(url: str) -> str:
    """提取域名（去除www前缀）"""
    try:
        netloc = urlparse(url).netloc.lower()
        return re.sub(r"^www\d?\.", "", netloc)
    except Exception:
        return url


def _infer_level_from_domain(domain: str) -> SourceLevel:
    """根据域名特征推断可信度等级"""
    # .gov / .edu 结尾的默认A级
    if domain.endswith((".gov", ".gov.cn", ".edu", ".edu.cn", ".ac.cn", ".org.cn")):
        return SourceLevel.A
    # .org 结尾的默认B级
    if domain.endswith(".org"):
        return SourceLevel.B
    # 有备案号的.cn域名默认B级
    # 无法判断的默认C级
    return SourceLevel.C
