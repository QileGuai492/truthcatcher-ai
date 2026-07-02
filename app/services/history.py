"""分析历史记录 -- SQLite 持久化存储"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.models.analysis import AnalysisResult

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "history.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表"""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            news_text TEXT NOT NULL,
            source_name TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            truth_probability REAL DEFAULT 50.0,
            confidence_level TEXT DEFAULT '',
            background TEXT DEFAULT '',
            reasoning TEXT DEFAULT '',
            warnings_json TEXT DEFAULT '[]',
            propagation_json TEXT DEFAULT '[]',
            rumor_match INTEGER DEFAULT 0,
            rumor_reference TEXT DEFAULT '',
            core_claims_json TEXT DEFAULT '[]',
            evidence_json TEXT DEFAULT '[]',
            search_sources_count INTEGER DEFAULT 0,
            reliable_sources_count INTEGER DEFAULT 0,
            content_type TEXT DEFAULT 'text',
            result_html TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    # 向前兼容
    for col, def_val in [("warnings_json", "'[]'"), ("propagation_json", "'[]'"),
                          ("rumor_match", "0"), ("rumor_reference", "''"),
                          ("result_html", "''")]:
        try:
            conn.execute(f"SELECT {col} FROM analyses LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute(f"ALTER TABLE analyses ADD COLUMN {col} DEFAULT {def_val}")
    conn.commit()
    conn.close()


def save_result(news_text: str, result: AnalysisResult, content_type: str = "text", source_name: str = "", result_html: str = ""):
    """保存分析结果"""
    init_db()
    conn = _get_conn()
    conn.execute(
        """INSERT INTO analyses
           (news_text, source_name, summary, truth_probability, confidence_level,
            background, reasoning, warnings_json, propagation_json, rumor_match, rumor_reference,
            core_claims_json, evidence_json,
            search_sources_count, reliable_sources_count, content_type, result_html, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            news_text[:5000],
            source_name,
            result.summary,
            result.truth_probability,
            result.confidence_level,
            result.background,
            result.reasoning,
            json.dumps(result.warnings, ensure_ascii=False),
            json.dumps([p.model_dump() for p in result.propagation], ensure_ascii=False),
            int(result.rumor_match),
            result.rumor_reference,
            json.dumps([c.model_dump() for c in result.core_claims], ensure_ascii=False),
            json.dumps([e.model_dump() for e in result.evidence_list], ensure_ascii=False),
            result.search_sources_count,
            result.reliable_sources_count,
            content_type,
            result_html,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    logger.info("分析结果已保存到历史记录")


def list_history(limit: int = 20) -> list[dict]:
    """列出最近的历史记录（仅摘要信息）"""
    init_db()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, summary, truth_probability, confidence_level, source_name, content_type, created_at "
        "FROM analyses ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_history_detail(analysis_id: int) -> Optional[dict]:
    """获取单条历史记录的完整信息"""
    init_db()
    conn = _get_conn()
    row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["core_claims"] = json.loads(d.get("core_claims_json", "[]"))
    d["evidence_list"] = json.loads(d.get("evidence_json", "[]"))
    return d


def get_history_html(analysis_id: int) -> Optional[str]:
    """获取历史记录中缓存的 HTML"""
    init_db()
    conn = _get_conn()
    row = conn.execute("SELECT result_html FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    conn.close()
    if row and row["result_html"]:
        return row["result_html"]
    return None


def list_history_for_dropdown(limit: int = 20) -> list[str]:
    """列出历史记录，格式化为下拉选项"""
    init_db()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, summary, truth_probability, created_at FROM analyses ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [f"#{r['id']} [{r['truth_probability']:.0f}%] {r['summary'][:40]} ({r['created_at'][:16]})" for r in rows]


def delete_history(analysis_id: int):
    """删除单条记录"""
    init_db()
    conn = _get_conn()
    conn.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
    conn.commit()
    conn.close()


def save_feedback(rating: str, summary: str = ""):
    """存储用户反馈"""
    init_db()
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rating TEXT NOT NULL,
            summary TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO feedback (rating, summary, created_at) VALUES (?, ?, ?)",
        (rating, summary, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    logger.info(f"用户反馈已记录: {rating}")
