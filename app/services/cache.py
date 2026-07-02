"""分析结果缓存 -- 同输入短时间内复用"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Optional

from app.models.analysis import AnalysisResult

logger = logging.getLogger(__name__)

# {input_hash: (timestamp, result)}
_cache: dict[str, tuple[float, AnalysisResult]] = {}
CACHE_TTL = 300  # 300秒 = 5分钟


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def get(text: str) -> Optional[AnalysisResult]:
    """获取缓存的分析结果，超时返回None"""
    key = _hash(text)
    if key in _cache:
        ts, result = _cache[key]
        if time.time() - ts < CACHE_TTL:
            logger.info(f"命中缓存 (剩余 {CACHE_TTL - (time.time() - ts):.0f}秒)")
            return result
        del _cache[key]
    return None


def put(text: str, result: AnalysisResult):
    """存入缓存"""
    key = _hash(text[:5000])
    _cache[key] = (time.time(), result)
    # 清理过期项
    expired = [k for k, (ts, _) in _cache.items() if time.time() - ts > CACHE_TTL]
    for k in expired:
        del _cache[k]
