"""Gradio 前端界面 -- 响应式Web UI"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from urllib.parse import unquote

import gradio as gr

from app.config import settings
from app.models.analysis import AnalysisResult, AnalysisStatus, NewsInput, SourceLevel
from app.services.llm_analyzer import LLMAnalyzer

logger = logging.getLogger(__name__)

# 全局分析器
analyzer = LLMAnalyzer()

# CSS 主题
CUSTOM_CSS = """
/* 进度条样式 */
.progress-container { margin: 12px 0; }
.progress-bar {
    height: 8px; border-radius: 4px;
    background: linear-gradient(90deg, #ef4444, #f59e0b, #22c55e);
    transition: width 0.5s;
}
/* 概率值颜色 */
.prob-high { color: #22c55e; font-weight: bold; }
.prob-mid { color: #f59e0b; font-weight: bold; }
.prob-low { color: #ef4444; font-weight: bold; }
/* 论据卡片 */
.evidence-card {
    border-left: 4px solid #6b7280; padding: 8px 12px;
    margin: 8px 0; border-radius: 6px; background: #f9fafb;
}
.evidence-support { border-left-color: #22c55e; }
.evidence-oppose { border-left-color: #ef4444; }
.evidence-neutral { border-left-color: #6b7280; }
/* 信源等级标签 */
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px;
    font-size: 12px; font-weight: 600; margin-right: 4px; }
.badge-A { background: #dcfce7; color: #166534; }
.badge-B { background: #dbeafe; color: #1e40af; }
.badge-C { background: #fef3c7; color: #92400e; }
.badge-D { background: #fee2e2; color: #991b1b; }
/* 响应式 */
@media (max-width: 640px) {
    .evidence-card { padding: 6px 10px; }
}
"""


def _truth_color(prob: float) -> str:
    """根据概率返回颜色"""
    if prob >= 70:
        return "#22c55e"
    elif prob >= 40:
        return "#f59e0b"
    else:
        return "#ef4444"


def _level_badge(level: str) -> str:
    badge_class = f"badge-{level}" if level in "ABCD" else "badge-C"
    return f'<span class="badge {badge_class}">{level}级</span>'


def _format_result_html(result: AnalysisResult) -> str:
    """将分析结果格式化为HTML"""
    prob = result.truth_probability
    color = _truth_color(prob)

    # 构建核心主张进度条
    claims_html = ""
    if result.core_claims:
        claims_html = '<div style="flex:1; display:flex; flex-direction:column; justify-content:space-around; gap:10px; min-width:0;">'
        for cc in result.core_claims:
            sc = _truth_color(cc.truth_score)
            claims_html += f"""
            <div style="display:flex; flex-direction:column; gap:3px;">
                <span style="font-size:12px; line-height:1.4; word-break:break-all;">{cc.claim}</span>
                <div style="display:flex; align-items:center; gap:6px;">
                    <div style="width:200px; height:12px; background:#e5e7eb; border-radius:6px; overflow:hidden; flex-shrink:0;">
                        <div style="width:{cc.truth_score:.0f}%; height:100%; background:{sc}; border-radius:6px; transition: width 0.8s;"></div>
                    </div>
                    <span style="font-size:12px; font-weight:600; width:34px; text-align:right; flex-shrink:0;">{cc.truth_score:.0f}%</span>
                    <span style="font-size:10px; color:#9ca3af; flex-shrink:0;">权重{cc.weight:.0%}</span>
                </div>
            </div>"""
        claims_html += '</div>'

    html = f"""
    <!-- 概率仪表盘 + 核心主张 -->
    <div style="display:flex; align-items:stretch; gap:24px; margin-bottom:24px; flex-wrap:wrap;">
        <!-- 左侧：圆圈 -->
        <div style="flex:0 0 auto; display:flex; flex-direction:column; align-items:center; justify-content:center; min-width:140px;">
            <div style="position:relative; width:140px; height:140px; border-radius:50%;
                background: conic-gradient({color} {prob}%, #e5e7eb {prob}%);">
                <div style="position:absolute; top:15px; left:15px;
                    width:110px; height:110px; border-radius:50%;
                    background:white; display:flex; flex-direction:column;
                    align-items:center; justify-content:center;">
                    <span style="font-size:30px; font-weight:700; color:{color};">{prob:.0f}%</span>
                    <span style="font-size:11px; color:#6b7280;">真实概率</span>
                </div>
            </div>
            <p style="margin-top:8px; font-size:12px; color:#6b7280; text-align:center; line-height:1.6;">
                置信度: {result.confidence_level}<br>
                搜索质量: {result.reliable_sources_count}/{result.search_sources_count} 条可靠信源
                {'（信息充足）' if result.reliable_sources_count >= 3 else '（信息不足，结论仅供参考）' if result.reliable_sources_count <= 1 else ''}
            </p>
        </div>
        <!-- 右侧：核心主张进度条 -->
        {claims_html}
    </div>

    """

    # 虚假信号预警
    if result.warnings:
        warnings_html = '<div style="background:#fef2f2; border-left:4px solid #ef4444; padding:12px 16px; border-radius:0 8px 8px 0; margin-bottom:16px;">'
        warnings_html += '<h3 style="margin:0 0 8px; color:#dc2626;">⚠️ 可疑信号检测</h3>'
        for w in result.warnings:
            warnings_html += f'<div style="font-size:13px; color:#991b1b; padding:3px 0;">• {w}</div>'
        warnings_html += '</div>'
        html += warnings_html

    html += f"""
    """

    # 谣言匹配提示
    if result.rumor_match:
        html += f"""
        <div style="background:#fee2e2; border-left:4px solid #dc2626; padding:12px 16px; border-radius:0 8px 8px 0; margin-bottom:16px;">
            <h3 style="margin:0 0 4px; color:#dc2626;">🚫 已知谣言</h3>
            <p style="font-size:13px; color:#991b1b; margin:0;">{result.rumor_reference}</p>
        </div>"""

    # 传播路径
    if result.propagation:
        html += '<h3>📡 传播路径</h3><div style="margin-bottom:16px;">'
        for i, p in enumerate(result.propagation):
            html += f"""
            <div style="display:flex; gap:12px; padding:6px 0; font-size:13px;">
                <span style="color:#6b7280; min-width:40px;">{'🔴 首发' if i == 0 else '🔗 转发'}</span>
                <span style="min-width:120px; color:#374151;">{p.platform}</span>
                <span style="min-width:100px; color:#9ca3af;">{p.time}</span>
                <span style="color:#6b7280;">{p.description}</span>
            </div>"""
        html += '</div>'

    html += """
    <!-- 新闻摘要 -->
    <h3 style="margin-top:0;">📋 新闻摘要</h3>
    <div style="background:#f3f4f6; padding:16px; border-radius:8px; margin-bottom:16px;">
        {result.summary}
    </div>

    <!-- 来龙去脉 -->
    <h3>📖 来龙去脉</h3>
    <div style="background:#f0fdf4; padding:16px; border-radius:8px; margin-bottom:16px;">
        {result.background}
    </div>
    """

    # 论据列表
    html += '<h3>🔍 论据列表</h3>'
    for ev in result.evidence_list:
        stance_icon = {"支持": "✅", "反对": "❌", "中立": "➖"}.get(ev.stance, "➖")
        stance_class = {
            "支持": "evidence-support",
            "反对": "evidence-oppose",
            "中立": "evidence-neutral",
        }.get(ev.stance, "evidence-neutral")

        html += f"""
        <div class="evidence-card {stance_class}">
            <div style="display:flex; justify-content:space-between; align-items:start; flex-wrap:wrap; gap:4px;">
                <strong>{stance_icon} {ev.stance}</strong>
                <div style="display:flex; gap:4px;">
                    {f'<span style="background:#dcfce7; color:#166534; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600;">✅ 已交叉验证</span>' if ev.cross_verified else '<span style="background:#fef3c7; color:#92400e; padding:2px 8px; border-radius:10px; font-size:11px;">⚠️ 单一信源</span>'}
                    {_level_badge(ev.source_level.value)}
                </div>
            </div>
            <p style="margin:8px 0;">{ev.content}</p>
            <div style="font-size:13px; color:#6b7280;">
                <span>来源: {ev.source_name}</span>
        """
        if ev.source_url:
            html += f' · <a href="{ev.source_url}" target="_blank">查看原文</a>'
        if ev.verified_by:
            html += f' · 交叉确认: {", ".join(ev.verified_by[:3])}'
        if ev.credibility_note:
            html += f'<br>📝 {ev.credibility_note}'
        if ev.bias_disclosure:
            html += f'<br>⚠️ 立场提示: {ev.bias_disclosure}'
        html += "</div></div>"

    # 论证过程
    html += f"""
    <h3>🧠 论证过程</h3>
    <div style="background:#fefce8; padding:16px; border-radius:8px; margin-bottom:16px;">
        {result.reasoning}
    </div>

    <!-- 元信息 -->
    <div style="font-size:12px; color:#9ca3af; margin-top:16px;">
        分析时间: {result.analyzed_at} ·
        信息来源: {result.search_sources_count}条搜索 ·
        可靠信源: {result.reliable_sources_count}条
    </div>
    """

    return html


def _progress_html(message: str) -> str:
    """构建进度状态 HTML"""
    return f"""
    <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; padding:60px 20px; text-align:center;">
        <div style="width:48px; height:48px; border:4px solid #e5e7eb; border-top-color:#3b82f6; border-radius:50%; animation:spin 0.8s linear infinite; margin-bottom:20px;"></div>
        <p style="font-size:16px; font-weight:500; color:#374151;">{message}</p>
    </div>
    <style>@keyframes spin {{ to {{ transform: rotate(360deg); }} }}</style>
    """


async def analyze_handler(news_text: str, source_name: str = ""):
    """流式分析处理 -- 渐进 yield HTML，前端逐步渲染"""
    if not news_text.strip():
        yield '<div style="color:#ef4444; text-align:center; padding:40px;">请输入新闻内容</div>'
        return

    raw_input = news_text.strip()
    content_type = "text"
    url_source = source_name.strip() if source_name else ""

    from app.services.cache import get as cache_get, put as cache_put

    # URL 自动检测与抓取
    if raw_input.startswith(("http://", "https://")):
        content_type = "url"
        url_source = url_source or raw_input

        cached = cache_get(raw_input)
        if cached:
            yield _format_result_html(cached)
            return

        yield _progress_html(f"正在抓取网页内容: {unquote(raw_input)[:60]}...")
        try:
            from app.services.crawler import extract_content
            extracted = await extract_content(raw_input)
            if not extracted:
                yield '<div style="color:#ef4444; text-align:center; padding:40px;">网页抓取失败，请检查链接是否有效，或直接粘贴新闻文本。</div>'
                return
            raw_input = extracted
            yield _progress_html(f"网页抓取成功，已提取 {len(raw_input)} 字符，开始分析...")
        except Exception as e:
            yield f'<div style="color:#ef4444; text-align:center; padding:40px;">网页抓取出错: {e}</div>'
            return

    # 检查谣言数据库
    try:
        from app.services.rumor_db import check_rumor
        rumor = check_rumor(raw_input)
        if rumor:
            from app.models.analysis import AnalysisResult
            fake_result = AnalysisResult(
                background="该内容匹配已知谣言数据库。",
                summary=f"谣言匹配: {rumor['verdict']}",
                truth_probability=rumor["truth_probability"],
                confidence_level=f"高 - 匹配已知谣言 ({rumor['reference']})",
                warnings=["该内容已被识别为已知谣言/虚假信息"],
                reasoning=rumor["reference"],
                rumor_match=True,
                rumor_reference=rumor["reference"],
                search_sources_count=0,
                reliable_sources_count=0,
            )
            yield _format_result_html(fake_result)
            return
    except Exception:
        pass

    # 检查文本缓存
    if content_type == "text":
        cached = cache_get(raw_input)
        if cached:
            yield _format_result_html(cached)
            return

    news_input = NewsInput(
        content_type=content_type,
        content=raw_input,
        source_name=url_source or None,
    )

    async for stage, data in analyzer.analyze_stream(news_input):
        if stage == "error":
            yield f'<div style="color:#ef4444; text-align:center; padding:40px;">{data}</div>'
            return

        if stage in ("searching", "extracting", "analyzing", "parsing"):
            yield _progress_html(data)

        elif stage == "streaming":
            chars = len(data)
            # 尝试计算已生成的论据条数（粗略估计）
            evidence_count = data.count('"stance"')
            yield f"""
            <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; padding:60px 20px; text-align:center;">
                <div style="width:48px; height:48px; border:4px solid #e5e7eb; border-top-color:#3b82f6; border-radius:50%; animation:spin 0.8s linear infinite; margin-bottom:20px;"></div>
                <p style="font-size:16px; font-weight:500; color:#374151;">AI 正在分析中...</p>
                <p style="font-size:13px; color:#9ca3af;">已生成 {chars} 字符 · 约 {evidence_count} 条论据</p>
            </div>
            <style>@keyframes spin {{ to {{ transform: rotate(360deg); }} }}</style>
            """

        elif stage == "done":
            # 保存到缓存、历史记录、谣言数据库
            try:
                cache_put(raw_input, data)
                from app.services.history import save_result
                save_result(raw_input, data, content_type, url_source)
                from app.services.rumor_db import add_rumor
                add_rumor(raw_input, data)
            except Exception:
                pass
            yield _format_result_html(data)

    return


def create_ui() -> gr.Blocks:
    """创建 Gradio 界面"""

    with gr.Blocks(
        title="真相捕手 - 新闻真伪辨别",
        analytics_enabled=False,
    ) as demo:

        gr.Markdown("""
        # 🔍 真相捕手 TruthCatcher
        ### AI驱动的实时新闻真伪辨别工具

        输入任意新闻文本，系统将自动搜索网络、验证信源、综合分析，给出客观公正的真伪判断。
        """)

        with gr.Row():
            with gr.Column(scale=1):
                news_input = gr.Textbox(
                    label="输入新闻内容",
                    placeholder="请粘贴新闻文本...\n\n或输入URL，系统将自动抓取...",
                    lines=8,
                    max_lines=20,
                )
                source_input = gr.Textbox(
                    label="新闻来源（可选）",
                    placeholder="如：微博、朋友圈、某网站...",
                    lines=1,
                )

                analyze_btn = gr.Button(
                    "开始分析",
                    variant="primary",
                    size="lg",
                )

                gr.Markdown("""
                ---
                **ℹ️ 使用说明**
                - 支持粘贴完整新闻文本
                - 分析过程实时流式展示
                - 结果包含：概率评分、正反论据、推理过程
                """)

            with gr.Column(scale=2):
                result_html = gr.HTML(
                    value='<div style="color:#9ca3af; text-align:center; padding:100px 20px; font-size:16px;">等待输入内容进行分析...</div>',
                )

                with gr.Accordion("📋 最近分析记录", open=False):
                    refresh_btn = gr.Button("刷新列表", size="sm")
                    history_html = gr.HTML(value=_format_history_html())

        analyze_btn.click(
            fn=analyze_handler,
            inputs=[news_input, source_input],
            outputs=[result_html],
        )
        refresh_btn.click(
            fn=refresh_history,
            inputs=[],
            outputs=[history_html],
        )

    return demo


def _format_history_html() -> str:
    """渲染历史记录列表 HTML"""
    try:
        from app.services.history import list_history

        items = list_history(15)
        if not items:
            return '<p style="color:#9ca3af; text-align:center; padding:20px;">暂无分析记录</p>'

        html = '<div style="max-height:300px; overflow-y:auto;">'
        for item in items:
            prob = item["truth_probability"]
            color = "#22c55e" if prob >= 70 else "#f59e0b" if prob >= 40 else "#ef4444"
            summary = item["summary"][:60] or "(无摘要)"
            source = item["source_name"][:30] or "文本输入"
            date = item["created_at"][:16].replace("T", " ")
            html += f"""
            <div style="display:flex; align-items:center; gap:12px; padding:8px 12px; margin:4px 0; background:#f9fafb; border-radius:8px; cursor:default;">
                <span style="font-weight:700; color:{color}; font-size:16px; min-width:48px;">{prob:.0f}%</span>
                <div style="flex:1; min-width:0;">
                    <div style="font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{summary}</div>
                    <div style="font-size:11px; color:#9ca3af;">{source} · {date}</div>
                </div>
            </div>"""
        html += '</div>'
        return html
    except Exception as e:
        return f'<p style="color:#ef4444;">加载失败: {e}</p>'


def refresh_history() -> str:
    """刷新历史记录（非async，Gradio可直接调用）"""
    return _format_history_html()


def main():
    """启动 Gradio 服务"""
    logging.basicConfig(level=logging.INFO)

    missing = settings.missing_keys()
    if missing:
        logger.warning(f"缺少环境变量: {', '.join(missing)}，请先配置 .env 文件")

    demo = create_ui()
    demo.queue(default_concurrency_limit=3)
    demo.launch(
        server_name=settings.app_host,
        server_port=settings.app_port,
        share=False,
        css=CUSTOM_CSS,
        theme=gr.themes.Soft(primary_hue="blue", neutral_hue="slate"),
    )


if __name__ == "__main__":
    main()
