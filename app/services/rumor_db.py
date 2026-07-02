"""谣言数据库 -- 已知谣言特征匹配与积累"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.models.analysis import AnalysisResult

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "rumors.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_rumor_db():
    """初始化谣言数据库"""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rumors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT UNIQUE NOT NULL,
            summary TEXT NOT NULL,
            verdict TEXT NOT NULL,
            truth_probability REAL DEFAULT 0.0,
            evidence_json TEXT DEFAULT '[]',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _simhash(text: str) -> str:
    """文本相似哈希：用于模糊匹配"""
    # 提取标题关键词做哈希
    keywords = text[:200].lower()
    return hashlib.md5(keywords.encode()).hexdigest()[:16]


def check_rumor(news_text: str) -> Optional[dict]:
    """检查输入文本是否匹配已知谣言"""
    init_rumor_db()
    conn = _get_conn()

    # 精确匹配
    exact_hash = hashlib.sha256(news_text[:5000].encode()).hexdigest()
    row = conn.execute(
        "SELECT * FROM rumors WHERE content_hash = ?", (exact_hash,)
    ).fetchone()

    if not row:
        # 模糊匹配：前200字符相似
        sim = _simhash(news_text)
        rows = conn.execute(
            "SELECT * FROM rumors ORDER BY id DESC LIMIT 50"
        ).fetchall()
        for r in rows:
            stored_sim = _simhash(json.dumps(r["summary"]))
            if stored_sim == sim:
                row = r
                break

    conn.close()

    if row:
        logger.info(f"匹配已知谣言 ID={row['id']}, 判定={row['verdict']}")
        return {
            "verdict": row["verdict"],
            "truth_probability": row["truth_probability"],
            "evidence": json.loads(row["evidence_json"]),
            "reference": f"该内容匹配已知谣言（ID:{row['id']}，首次记录于{row['created_at'][:10]}）",
        }
    return None


def add_rumor(news_text: str, result: AnalysisResult):
    """将分析结果添加到谣言数据库（仅当概率≤30%时认为是谣言）"""
    if result.truth_probability > 30:
        return  # 只存储确认为谣言的结果

    init_rumor_db()
    conn = _get_conn()
    content_hash = hashlib.sha256(news_text[:5000].encode()).hexdigest()

    # 避免重复
    existing = conn.execute(
        "SELECT id FROM rumors WHERE content_hash = ?", (content_hash,)
    ).fetchone()
    if existing:
        conn.close()
        return

    conn.execute(
        "INSERT INTO rumors (content_hash, summary, verdict, truth_probability, evidence_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            content_hash,
            result.summary,
            "虚假" if result.truth_probability <= 30 else "存疑",
            result.truth_probability,
            json.dumps([e.model_dump() for e in result.evidence_list], ensure_ascii=False),
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    logger.info(f"已添加谣言到数据库: {result.summary[:50]}")
