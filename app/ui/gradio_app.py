"""Gradio Web UI for TruthCatcher"""

from __future__ import annotations

import logging
import re
import urllib.parse
from urllib.parse import unquote

import gradio as gr

from app.config import settings
from app.models.analysis import AnalysisResult, NewsInput
from app.services.llm_analyzer import LLMAnalyzer

logger = logging.getLogger(__name__)
analyzer = LLMAnalyzer()

CUSTOM_CSS = """
* { font-family: 'Microsoft YaHei', 'PingFang SC', 'Hiragino Sans GB', 'Segoe UI', sans-serif !important; }
.progress-container { margin: 12px 0; }
.progress-bar { height: 8px; border-radius: 4px; background: linear-gradient(90deg, #ef4444, #f59e0b, #22c55e); }
.evidence-card { border-left: 4px solid #6b7280; padding: 8px 12px; margin: 8px 0; border-radius: 6px; background: #f9fafb; }
.evidence-support { border-left-color: #22c55e; }
.evidence-oppose { border-left-color: #ef4444; }
.evidence-neutral { border-left-color: #6b7280; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 600; margin-right: 4px; }
.badge-A { background: #dcfce7; color: #166534; }
.badge-B { background: #dbeafe; color: #1e40af; }
.badge-C { background: #fef3c7; color: #92400e; }
.badge-D { background: #fee2e2; color: #991b1b; }
@media (max-width: 640px) { .evidence-card { padding: 6px 10px; } }
.history-dropdown input { padding-right: 32px !important; }
"""


def _truth_color(prob):
    if prob >= 70: return "#22c55e"
    if prob >= 40: return "#f59e0b"
    return "#ef4444"


def _level_badge(level):
    c = f"badge-{level}" if level in "ABCD" else "badge-C"
    return f'<span class="badge {c}">{level}级</span>'


def _report_text(result, prob):
    lines = [
        "TruthCatcher 分析报告",
        "=" * 20,
        f"分析时间: {result.analyzed_at}",
        f"真实概率: {prob:.0f}%  置信度: {result.confidence_level}",
        f"搜索信源: {result.search_sources_count}条  可靠信源: {result.reliable_sources_count}条",
        "", f"摘要: {result.summary}",
        "", f"来龙去脉: {result.background}", "",
        "核心主张:",
    ]
    for cc in result.core_claims:
        lines.append(f"  [{cc.truth_score:.0f}% x{cc.weight:.0%}] {cc.claim}")
    lines.append("")
    lines.append("论据列表:")
    for ev in result.evidence_list:
        cv = "已交叉验证" if ev.cross_verified else "单一信源"
        lines.append(f"  [{ev.stance}] {ev.content} | {ev.source_name} [{ev.source_level.value}级] {cv}")
    lines.append("")
    lines.append(f"论证过程: {result.reasoning}")
    lines.append("")
    lines.append("本报告由 TruthCatcher AI 自动生成，仅供参考。")
    return urllib.parse.quote("\n".join(lines), safe="")


def _format_result_html(result):
    prob = result.truth_probability
    color = _truth_color(prob)

    claims_html = ""
    if result.core_claims:
        claims_html = '<div style="flex:1; display:flex; flex-direction:column; justify-content:space-around; gap:10px; min-width:0;">'
        for cc in result.core_claims:
            sc = _truth_color(cc.truth_score)
            claims_html += (
                f'<div style="display:flex; flex-direction:column; gap:3px;">'
                f'<span style="font-size:12px; line-height:1.4; word-break:break-all;">{cc.claim}</span>'
                f'<div style="display:flex; align-items:center; gap:6px;">'
                f'<div style="width:200px; height:12px; background:#e5e7eb; border-radius:6px; overflow:hidden; flex-shrink:0;">'
                f'<div style="width:{cc.truth_score:.0f}%; height:100%; background:{sc}; border-radius:6px; transition:width 0.8s;"></div>'
                f'</div>'
                f'<span style="font-size:12px; font-weight:600; width:34px; text-align:right; flex-shrink:0;">{cc.truth_score:.0f}%</span>'
                f'<span style="font-size:10px; color:#9ca3af; flex-shrink:0;">权重{cc.weight:.0%}</span>'
                f'</div></div>'
            )
        claims_html += '</div>'

    gauge = f"""<div style="display:flex; align-items:stretch; gap:24px; margin-bottom:24px; flex-wrap:wrap;">
        <div style="flex:0 0 auto; display:flex; flex-direction:column; align-items:center; justify-content:center; min-width:140px;">
            <div style="position:relative; width:140px; height:140px; border-radius:50%; background:conic-gradient({color} {prob}%, #e5e7eb {prob}%);">
                <div style="position:absolute; top:15px; left:15px; width:110px; height:110px; border-radius:50%; background:white; display:flex; flex-direction:column; align-items:center; justify-content:center;">
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
        {claims_html}
    </div>"""

    parts = [gauge]

    if result.warnings:
        w_html = '<div style="background:#fef2f2; border-left:4px solid #ef4444; padding:12px 16px; border-radius:0 8px 8px 0; margin-bottom:16px;"><h3 style="margin:0 0 8px; color:#dc2626;">可疑信号检测</h3>'
        for w in result.warnings:
            w_html += f'<div style="font-size:13px; color:#991b1b; padding:3px 0;">{w}</div>'
        w_html += '</div>'
        parts.append(w_html)

    if result.rumor_match:
        parts.append(f'<div style="background:#fee2e2; border-left:4px solid #dc2626; padding:12px 16px; border-radius:0 8px 8px 0; margin-bottom:16px;"><h3 style="margin:0 0 4px; color:#dc2626;">已知谣言</h3><p style="font-size:13px; color:#991b1b; margin:0;">{result.rumor_reference}</p></div>')

    if result.propagation:
        p_html = '<h3>传播路径</h3><div style="margin-bottom:16px;">'
        for i, p in enumerate(result.propagation):
            tag = '首发' if i == 0 else '转发'
            p_html += f'<div style="display:flex; gap:12px; padding:6px 0; font-size:13px;"><span style="color:#6b7280; min-width:40px;">{tag}</span><span style="min-width:120px; color:#374151;">{p.platform}</span><span style="min-width:100px; color:#9ca3af;">{p.time}</span><span style="color:#6b7280;">{p.description}</span></div>'
        p_html += '</div>'
        parts.append(p_html)

    parts.append(f'<h3 style="margin-top:0;">新闻摘要</h3><div style="background:#f3f4f6; padding:16px; border-radius:8px; margin-bottom:16px;">{result.summary}</div>')
    parts.append(f'<h3>来龙去脉</h3><div style="background:#f0fdf4; padding:16px; border-radius:8px; margin-bottom:16px;">{result.background}</div>')

    ev_html = '<h3>论据列表</h3>'
    for ev in result.evidence_list:
        icon = ev.stance
        sc = "evidence-support" if ev.stance == "支持" else ("evidence-oppose" if ev.stance == "反对" else "evidence-neutral")
        cv_badge = '<span style="background:#dcfce7; color:#166534; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600;">已交叉验证</span>' if ev.cross_verified else '<span style="background:#fef3c7; color:#92400e; padding:2px 8px; border-radius:10px; font-size:11px;">单一信源</span>'
        ev_html += f'<div class="evidence-card {sc}"><div style="display:flex; justify-content:space-between; align-items:start; flex-wrap:wrap; gap:4px;"><strong>{icon}</strong><div style="display:flex; gap:4px;">{cv_badge}{_level_badge(ev.source_level.value)}</div></div><p style="margin:8px 0;">{ev.content}</p><div style="font-size:13px; color:#6b7280;"><span>来源: {ev.source_name}</span>'
        if ev.source_url:
            ev_html += f' <a href="{ev.source_url}" target="_blank">查看原文</a>'
        if ev.verified_by:
            ev_html += f' 交叉确认: {", ".join(ev.verified_by[:3])}'
        if ev.credibility_note:
            ev_html += f'<br>{ev.credibility_note}'
        if ev.bias_disclosure:
            ev_html += f'<br>立场提示: {ev.bias_disclosure}'
        ev_html += '</div></div>'
    parts.append(ev_html)

    parts.append(f'<h3>论证过程</h3><div style="background:#fefce8; padding:16px; border-radius:8px; margin-bottom:16px;">{result.reasoning}</div>')
    parts.append(f'<div style="display:flex; justify-content:space-between; align-items:center; margin-top:16px; flex-wrap:wrap; gap:8px;"><div style="font-size:12px; color:#9ca3af;">分析时间: {result.analyzed_at} 搜索: {result.search_sources_count}条 可靠信源: {result.reliable_sources_count}条</div><a href="data:text/plain;charset=utf-8,{_report_text(result, prob)}" download="TruthCatcher_Report.txt" style="text-decoration:none;"><button style="padding:6px 14px; background:#3b82f6; color:#fff; border:none; border-radius:6px; font-size:12px; cursor:pointer;">下载报告</button></a></div>')

    return "".join(parts)


def _progress_html(msg):
    return f"""<div style="display:flex; flex-direction:column; align-items:center; justify-content:center; padding:60px 20px; text-align:center;">
        <div style="width:48px; height:48px; border:4px solid #e5e7eb; border-top-color:#3b82f6; border-radius:50%; animation:spin 0.8s linear infinite; margin-bottom:20px;"></div>
        <p style="font-size:16px; font-weight:500; color:#374151;">{msg}</p>
    </div>
    <style>@keyframes spin {{ to {{ transform: rotate(360deg); }} }}</style>"""


async def analyze_handler(news_text, source_name=""):
    if not news_text.strip():
        yield '<div style="color:#ef4444; text-align:center; padding:40px;">请输入新闻内容</div>'
        return

    raw_input = news_text.strip()
    content_type = "text"
    url_source = source_name.strip() or ""
    from app.services.cache import get as cache_get, put as cache_put

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
                yield '<div style="color:#ef4444; text-align:center; padding:40px;">网页抓取失败，建议直接在浏览器选中文章文字复制粘贴。</div>'
                return
            raw_input = extracted
            yield _progress_html(f"网页抓取成功，已提取 {len(raw_input)} 字符，开始分析...")
        except Exception as e:
            yield f'<div style="color:#ef4444; text-align:center; padding:40px;">抓取出错: {e}</div>'
            return

    try:
        from app.services.rumor_db import check_rumor
        rumor = check_rumor(raw_input)
        if rumor:
            r = AnalysisResult(background="匹配已知谣言数据库。", summary=f"谣言匹配: {rumor['verdict']}", truth_probability=rumor["truth_probability"], confidence_level=f"高 - 匹配已知谣言", warnings=["内容已识别为已知谣言/虚假信息"], reasoning=rumor["reference"], rumor_match=True, rumor_reference=rumor["reference"], search_sources_count=0, reliable_sources_count=0)
            yield _format_result_html(r)
            return
    except Exception:
        pass

    if content_type == "text":
        cached = cache_get(raw_input)
        if cached:
            yield _format_result_html(cached)
            return

    news_input = NewsInput(content_type=content_type, content=raw_input, source_name=url_source or None)

    async for stage, data in analyzer.analyze_stream(news_input):
        logger.info(f"分析阶段: {stage}")
        if stage == "error":
            logger.error(f"分析失败: {data}")
            yield f'<div style="color:#ef4444; text-align:center; padding:40px;">{data}</div>'
            return
        if stage in ("searching", "extracting", "analyzing", "parsing"):
            yield _progress_html(data)
        elif stage == "streaming":
            yield f"""<div style="display:flex; flex-direction:column; align-items:center; justify-content:center; padding:60px 20px; text-align:center;">
                <div style="width:48px; height:48px; border:4px solid #e5e7eb; border-top-color:#3b82f6; border-radius:50%; animation:spin 0.8s linear infinite; margin-bottom:20px;"></div>
                <p style="font-size:16px; font-weight:500; color:#374151;">AI 正在分析中...</p>
                <p style="font-size:13px; color:#9ca3af;">已生成 {len(data)} 字符 约 {data.count('"stance"')} 条论据</p>
            </div>
            <style>@keyframes spin {{ to {{ transform: rotate(360deg); }} }}</style>"""
        elif stage == "done":
            logger.info("分析完成，正在保存...")
            try:
                cache_put(raw_input, data)
                html = _format_result_html(data)
                from app.services.history import save_result
                logger.info(f"准备保存: {data.summary[:50]}...")
                save_result(raw_input, data, content_type, url_source, html)
                logger.info("保存成功")
                from app.services.rumor_db import add_rumor
                add_rumor(raw_input, data)
            except Exception:
                logger.exception("保存结果失败")
            yield _format_result_html(data)


def _format_history_dropdown():
    try:
        from app.services.history import list_history_for_dropdown
        result = list_history_for_dropdown(20)
        logger.info(f"加载历史列表: {len(result)} 条")
        return result
    except Exception as e:
        logger.exception(f"加载历史失败: {e}")
        return []


def refresh_history():
    choices = _format_history_dropdown()
    return gr.update(choices=choices, value=choices[0] if choices else None)


def load_history_detail(selection):
    if not selection:
        return '<div style="color:#9ca3af; text-align:center; padding:60px;">请选择一条记录</div>'
    try:
        m = re.match(r'#(\d+)', selection)
        if not m:
            return '<div style="color:#ef4444; text-align:center; padding:60px;">无效的记录格式</div>'
        from app.services.history import get_history_html
        html = get_history_html(int(m.group(1)))
        return html or '<div style="color:#ef4444; text-align:center; padding:60px;">未找到该记录（旧版数据无缓存）</div>'
    except Exception as e:
        return f'<div style="color:#ef4444; text-align:center; padding:60px;">加载失败: {e}</div>'


def create_ui():
    head_js = """<script>
(function(){var v=null;var q=new URLSearchParams(window.location.search);v=q.get('url');if(!v){var h=window.location.hash;if(h.indexOf('#text=')===0){v=decodeURIComponent(h.substring(6));}}if(v){var t=setInterval(function(){var ta=document.querySelector('textarea');if(ta){ta.value=v;ta.dispatchEvent(new Event('input',{bubbles:true}));clearInterval(t);}},300);history.replaceState(null,'',window.location.pathname);}
setInterval(function(){var d=document.querySelector('.history-dropdown input');if(d&&!d.readOnly){d.readOnly=true;}},500);
})();
</script>"""

    with gr.Blocks(title="真相捕手 TruthCatcher", analytics_enabled=False, head=head_js) as demo:
        gr.Markdown("# 真相捕手 TruthCatcher\n### AI驱动的实时新闻真伪辨别工具")

        with gr.Row():
            with gr.Column(scale=1):
                news_input = gr.Textbox(label="输入新闻内容", placeholder="请粘贴新闻文本或URL...", lines=8, max_lines=20)
                source_input = gr.Textbox(label="新闻来源（可选）", placeholder="如：微博、朋友圈、某网站...", lines=1)
                analyze_btn = gr.Button("开始分析", variant="primary", size="lg")
                gr.Markdown("---\n**使用说明**\n- 支持粘贴完整新闻文本或URL\n- 分析过程实时流式展示\n- 结果包含：概率评分、正反论据、推理过程")

            with gr.Column(scale=2):
                result_html = gr.HTML(value='<div style="color:#9ca3af; text-align:center; padding:100px 20px; font-size:16px;">等待输入内容进行分析...</div>')
                with gr.Accordion("最近分析记录", open=False):
                    choices = _format_history_dropdown()
                    history_dropdown = gr.Dropdown(
                        label="选择记录",
                        choices=choices,
                        value=choices[0] if choices else None,
                        interactive=True,
                        allow_custom_value=False,
                        elem_classes="history-dropdown",
                    )
                    with gr.Row():
                        load_btn = gr.Button("加载选中记录", size="sm")
                        refresh_btn = gr.Button("刷新列表", size="sm")

        analyze_btn.click(fn=analyze_handler, inputs=[news_input, source_input], outputs=[result_html]).then(
            fn=refresh_history, inputs=[], outputs=[history_dropdown])
        load_btn.click(fn=load_history_detail, inputs=[history_dropdown], outputs=[result_html])
        refresh_btn.click(fn=refresh_history, inputs=[], outputs=[history_dropdown])

        # 页面加载时刷新历史列表
        demo.load(fn=refresh_history, inputs=[], outputs=[history_dropdown])

    return demo


def main():
    logging.basicConfig(level=logging.INFO)
    missing = settings.missing_keys()
    if missing:
        logger.warning(f"缺少环境变量: {', '.join(missing)}")
    demo = create_ui()
    demo.queue(default_concurrency_limit=1)
    demo.launch(server_name=settings.app_host, server_port=settings.app_port, share=False, css=CUSTOM_CSS, theme=gr.themes.Soft(primary_hue="blue", neutral_hue="slate"))


if __name__ == "__main__":
    main()
