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
