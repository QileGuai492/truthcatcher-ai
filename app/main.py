"""FastAPI 后端主程序 -- 提供 REST API"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.config import settings
from app.models.analysis import AnalysisProgress, AnalysisResult, NewsInput
from app.services.llm_analyzer import LLMAnalyzer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

# 全局分析器实例
analyzer: LLMAnalyzer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global analyzer
    # 启动时
    missing = settings.missing_keys()
    if missing:
        logger.warning(f"缺少必要的环境变量: {', '.join(missing)}，请在 .env 文件中配置")
    analyzer = LLMAnalyzer()
    logger.info("真相捕手 API 服务启动完成")
    yield
    # 关闭时
    analyzer = None
    logger.info("服务已关闭")


app = FastAPI(
    title="真相捕手 API",
    description="AI驱动的实时新闻真伪辨别工具",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok" if settings.is_configured() else "not_configured",
        "version": "0.1.0",
        "missing_keys": settings.missing_keys(),
    }


# 暂存最新报告数据
_latest_report: AnalysisResult | None = None


@app.post("/report")
async def save_report(result: AnalysisResult):
    """保存最新分析结果，供 GET /report/latest 下载"""
    global _latest_report
    _latest_report = result
    return {"status": "ok"}


@app.get("/report/latest")
async def download_latest_report():
    """下载最新的 HTML 分析报告"""
    from fastapi.responses import HTMLResponse

    global _latest_report
    if not _latest_report:
        return HTMLResponse(content="<p>No analysis result yet</p>", status_code=404)

    result = _latest_report
    prob = result.truth_probability
    color = "#22c55e" if prob >= 70 else "#f59e0b" if prob >= 40 else "#ef4444"

    evidence_rows = ""
    for ev in result.evidence_list:
        icon = {"支持": "✅", "反对": "❌", "中立": "➖"}.get(ev.stance, "➖")
        cv = "✅ 已交叉验证" if ev.cross_verified else "⚠️ 单一信源"
        evidence_rows += f"""
        <tr>
            <td>{icon} {ev.stance}</td>
            <td>{ev.content}</td>
            <td>{ev.source_name} [{ev.source_level.value}级] {cv}</td>
        </tr>"""

    claims_rows = ""
    for cc in result.core_claims:
        claims_rows += f"<tr><td>{cc.claim}</td><td>{cc.truth_score:.0f}%</td><td>权重 {cc.weight:.0%}</td></tr>"

    warnings_html = ""
    if result.warnings:
        warnings_html = "<h3>⚠️ 可疑信号</h3><ul>" + "".join(f"<li>{w}</li>" for w in result.warnings) + "</ul>"

    propagation_html = ""
    if result.propagation:
        propagation_html = "<h3>📡 传播路径</h3><ol>" + "".join(
            f"<li>{p.time} · {p.platform} · {p.description}</li>" for p in result.propagation
        ) + "</ol>"

    report = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>TruthCatcher 分析报告</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; color: #1f2937; }}
  h1 {{ font-size: 24px; margin-bottom: 4px; }} h2 {{ font-size: 18px; margin-top: 24px; }}
  .prob {{ font-size: 48px; font-weight: 700; color: {color}; }} .meta {{ color: #9ca3af; font-size: 14px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
  th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e5e7eb; font-size: 14px; }}
  th {{ background: #f9fafb; }}
  .section {{ background: #f9fafb; padding: 16px; border-radius: 8px; margin: 12px 0; }}
  .warning {{ background: #fef2f2; padding: 16px; border-radius: 8px; border-left: 4px solid #ef4444; }}
  footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af; }}
</style></head>
<body>
  <h1>TruthCatcher 新闻真伪分析报告</h1>
  <p class="meta">生成时间: {result.analyzed_at} · 搜索信源: {result.search_sources_count}条 · 可靠信源: {result.reliable_sources_count}条</p>

  <div style="text-align:center; margin: 24px 0;">
    <div class="prob">{prob:.0f}%</div>
    <p>真实概率 · 置信度: {result.confidence_level}</p>
  </div>

  {propagation_html}
  {warnings_html}

  <h2>📋 新闻摘要</h2>
  <div class="section">{result.summary}</div>

  <h2>📖 来龙去脉</h2>
  <div class="section">{result.background}</div>

  <h2>🎯 核心主张</h2>
  <table><tr><th>主张</th><th>真实度</th><th>权重</th></tr>{claims_rows}</table>

  <h2>🔍 论据列表</h2>
  <table><tr><th>立场</th><th>内容</th><th>来源</th></tr>{evidence_rows}</table>

  <h2>🧠 论证过程</h2>
  <div class="section">{result.reasoning}</div>

  <footer>本报告由 TruthCatcher AI 自动生成，仅供参考。分析结果受搜索数据质量影响，不构成事实认定。</footer>
</body></html>"""

    return HTMLResponse(content=report, headers={"Content-Disposition": "attachment; filename=TruthCatcher_Report.html"})


@app.post("/feedback")
async def submit_feedback(rating: str, summary: str = ""):
    """提交用户反馈: rating='up' 或 'down'"""
    from app.services.history import save_feedback
    save_feedback(rating, summary)
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalysisResult)
async def analyze_news(news_input: NewsInput):
    """分析新闻真伪 -- 同步模式"""
    if not settings.is_configured():
        raise HTTPException(
            status_code=503,
            detail=f"服务未配置: 缺少 {', '.join(settings.missing_keys())}",
        )

    if not analyzer:
        raise HTTPException(status_code=503, detail="服务未就绪")

    try:
        result = await analyzer.analyze(news_input)
        return result
    except Exception as e:
        logger.exception("分析失败")
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")


@app.post("/analyze/stream")
async def analyze_news_stream(news_input: NewsInput):
    """分析新闻真伪 -- SSE流式模式（前端可实时展示进度）"""
    if not settings.is_configured():
        raise HTTPException(
            status_code=503,
            detail=f"服务未配置: 缺少 {', '.join(settings.missing_keys())}",
        )
    if not analyzer:
        raise HTTPException(status_code=503, detail="服务未就绪")

    import json
    import asyncio

    queue: asyncio.Queue = asyncio.Queue()

    async def progress_callback(progress: AnalysisProgress):
        await queue.put(progress)

    async def event_generator():
        try:
            # 启动分析任务
            task = asyncio.create_task(analyzer.analyze(news_input, progress_callback))

            while not task.done():
                try:
                    progress = await asyncio.wait_for(queue.get(), timeout=30)
                    event_data = progress.model_dump_json()
                    # 对 result 做特殊处理，因为里面可能有复杂对象
                    yield f"data: {event_data}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'status': 'searching', 'message': '等待中...', 'percentage': 50})}\n\n"

            # 获取最终结果
            result = task.result()
            final = AnalysisProgress(
                status="completed",
                message="分析完成",
                percentage=100,
                result=result,
            )
            yield f"data: {final.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            error_data = json.dumps({"status": "failed", "message": str(e), "percentage": 0})
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
