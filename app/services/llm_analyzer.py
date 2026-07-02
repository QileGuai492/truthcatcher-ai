"""LLM 分析引擎 -- 核心分析流水线"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional

from app.config import settings
from app.models.analysis import (
    AnalysisProgress,
    AnalysisResult,
    AnalysisStatus,
    CoreClaim,
    Evidence,
    NewsInput,
    PropagationEvent,
    SearchResult,
    SourceLevel,
)
from app.prompts.analysis import SYSTEM_PROMPT, build_analysis_prompt
from app.services.crawler import batch_extract
from app.services.llm_client import get_llm_client
from app.services.search import generate_search_queries, multi_search
from app.services.source_rater import rate_all

logger = logging.getLogger(__name__)


class LLMAnalyzer:
    """新闻真伪分析流水线"""

    def __init__(self):
        self.llm = get_llm_client()

    async def analyze_stream(self, news_input: NewsInput):
        """流式分析 -- 渐进 yield (stage, data)，前端逐步渲染"""

        # -- Step 1: 搜索 --
        yield ("searching", "正在解析新闻内容...")
        queries = await generate_search_queries(news_input.content)
        yield ("searching", f"正在搜索 {len(queries)} 组关键词...<br><small>{' · '.join(queries[:5])}</small>")

        search_results = await multi_search(queries)
        if not search_results:
            yield ("error", "无法获取搜索数据，请检查网络或API配置。")
            return

        yield ("searching", f"搜索完成，找到 {len(search_results)} 条相关结果，正在评级...")

        # -- Step 2: 信源评级 --
        rated_results = rate_all(search_results)
        a_b_count = sum(1 for r in rated_results if r.source_level in (SourceLevel.A, SourceLevel.B))
        yield ("searching", f"信源评级完成：A/B级 {a_b_count} 条，共 {len(rated_results)} 条")

        # -- Step 3: 抓取正文 --
        urls_to_crawl = [r.url for r in rated_results[:8]]
        yield ("extracting", f"正在提取 {len(urls_to_crawl)} 个网页正文...")
        extracted = await batch_extract(urls_to_crawl)
        success = sum(1 for v in extracted.values() if v)
        yield ("extracting", f"正文提取完成（{success}/{len(urls_to_crawl)} 成功）")

        # -- Step 4: 准备 prompt --
        search_text = self._format_search_results(rated_results, extracted)
        rating_summary = self._format_rating_summary(rated_results)
        analysis_prompt = build_analysis_prompt(
            original_news=news_input.content,
            search_results_text=search_text,
            source_rating_summary=rating_summary,
        )

        # -- Step 5: 流式 LLM 分析 --
        yield ("analyzing", "AI 正在分析中...")
        accumulated = ""
        async for chunk in self.llm.chat_stream(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=analysis_prompt,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        ):
            accumulated += chunk
            # 每积累一定量就尝试解析，看是否已有完整论据
            yield ("streaming", accumulated)

        # -- Step 6: 解析最终结果 --
        yield ("parsing", "正在整理分析结果...")
        result = self._parse_result(accumulated)
        result.search_sources_count = len(rated_results)
        result.reliable_sources_count = sum(1 for r in rated_results if r.source_level in (SourceLevel.A, SourceLevel.B))
        yield ("done", result)

    async def analyze(
        self,
        news_input: NewsInput,
        progress_callback: Optional[callable] = None,
    ) -> AnalysisResult:
        """执行完整的分析流水线"""
        start_time = time.time()

        # -- Step 1: 状态更新 --
        await self._progress(progress_callback, AnalysisStatus.SEARCHING, "正在生成搜索关键词...", 5)

        # -- Step 2: 生成搜索关键词 --
        queries = await generate_search_queries(news_input.content)
        await self._progress(progress_callback, AnalysisStatus.SEARCHING, f"正在搜索 ({len(queries)}组关键词)...", 15)

        # -- Step 3: 多引擎搜索 --
        search_results = await multi_search(queries)
        if not search_results:
            return self._empty_result("无法获取搜索数据，请检查网络或API配置。")

        await self._progress(progress_callback, AnalysisStatus.EXTRACTING, f"正在对{len(search_results)}条搜索结果进行信源评级...", 35)

        # -- Step 4: 信源评级 --
        rated_results = rate_all(search_results)

        # -- Step 5: 抓取正文 --
        urls_to_crawl = [r.url for r in rated_results[:8]]  # 抓取前8条
        await self._progress(progress_callback, AnalysisStatus.EXTRACTING, f"正在提取{len(urls_to_crawl)}个网页正文...", 45)

        extracted = await batch_extract(urls_to_crawl)

        # -- Step 6: 整理搜索结果文本 --
        await self._progress(progress_callback, AnalysisStatus.ANALYZING, "正在整理搜索材料...", 65)

        search_text = self._format_search_results(rated_results, extracted)
        rating_summary = self._format_rating_summary(rated_results)

        # -- Step 7: LLM 分析 --
        await self._progress(progress_callback, AnalysisStatus.ANALYZING, "正在进行AI综合分析...", 75)

        analysis_prompt = build_analysis_prompt(
            original_news=news_input.content,
            search_results_text=search_text,
            source_rating_summary=rating_summary,
        )

        result = await self._call_llm(analysis_prompt)

        # 补充元信息
        result.search_sources_count = len(rated_results)
        result.reliable_sources_count = sum(1 for r in rated_results if r.source_level in (SourceLevel.A, SourceLevel.B))

        await self._progress(progress_callback, AnalysisStatus.COMPLETED, "分析完成！", 100, result)

        elapsed = time.time() - start_time
        logger.info(f"分析完成，耗时 {elapsed:.1f}s，结果概率: {result.truth_probability}%")

        return result

    async def _call_llm(self, prompt: str) -> AnalysisResult:
        """调用 LLM 进行分析（同步版）"""
        try:
            raw_text = await self.llm.chat(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
            )
            return self._parse_result(raw_text)
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise

    def _parse_result(self, raw_text: str) -> AnalysisResult:
        """解析 LLM 返回的 JSON 为 AnalysisResult"""
        try:
            json_text = self._extract_json(raw_text)
            data = json.loads(json_text)

            confidence = data.get("confidence_level", "未知")
            if len(confidence) > 30:
                confidence = confidence[:28] + "…"

            # 解析 core_claims
            core_claims_data = data.get("core_claims", [])
            core_claims: list[CoreClaim] = []
            for c in core_claims_data:
                raw_score = float(c.get("truth_score", 50.0))
                raw_weight = float(c.get("weight", 1.0 / max(len(core_claims_data), 1)))
                core_claims.append(CoreClaim(
                    claim=c.get("claim", ""),
                    truth_score=raw_score,
                    weight=raw_weight,
                ))

            # 总概率 = core_claims 加权平均
            if core_claims:
                all_scores = [cc.truth_score for cc in core_claims]
                if all(0 <= s <= 1 for s in all_scores) and max(all_scores) <= 1:
                    logger.warning(f"检测到分数为0-1小数制，自动×100。原始: {all_scores}")
                    for cc in core_claims:
                        cc.truth_score = round(cc.truth_score * 100, 1)

                total_w = sum(cc.weight for cc in core_claims)
                if total_w > 0:
                    for cc in core_claims:
                        cc.weight = cc.weight / total_w

                weighted_sum = sum(cc.truth_score * cc.weight for cc in core_claims)
                prob = round(weighted_sum, 1)

                detail = " | ".join(
                    f"[{cc.truth_score:.0f}% x{cc.weight:.0%}] {cc.claim[:30]}" for cc in core_claims
                )
                logger.info(f"加权计算: prob={prob}%")
                logger.info(f"各主张: {detail}")
            else:
                prob = float(data.get("truth_probability", 50.0))
                if prob == 0.0 and not self._is_definitely_false(confidence):
                    estimated = self._estimate_prob_from_evidence(data.get("evidence_list", []))
                    prob = estimated if estimated is not None else 50.0
                    confidence = f"{confidence}（概率值经系统修正，原输出为0）"

            return AnalysisResult(
                background=data.get("background", ""),
                summary=data.get("summary", ""),
                truth_probability=prob,
                confidence_level=confidence,
                warnings=data.get("warnings", []),
                propagation=[
                    PropagationEvent(
                        time=p.get("time", ""),
                        platform=p.get("platform", ""),
                        description=p.get("description", ""),
                    )
                    for p in data.get("propagation", [])
                ],
                core_claims=core_claims,
                evidence_list=[
                    Evidence(
                        content=e.get("content", ""),
                        stance=e.get("stance", "中立"),
                        source_url=e.get("source_url", ""),
                        source_name=e.get("source_name", ""),
                        source_level=SourceLevel(e.get("source_level", "未知")),
                        cross_verified=bool(e.get("cross_verified", False)),
                        verified_by=e.get("verified_by", []),
                        credibility_note=e.get("credibility_note", ""),
                        bias_disclosure=e.get("bias_disclosure", ""),
                    )
                    for e in data.get("evidence_list", [])
                ],
                reasoning=data.get("reasoning", ""),
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"LLM 返回解析失败: {e}\n原始文本: {raw_text[:500]}")
            return self._empty_result(f"AI分析结果解析失败，请重试。错误: {e}")

    @staticmethod
    def _extract_json(text: str) -> str:
        """从可能包含markdown代码块的文本中提取JSON"""
        # 尝试匹配 ```json ... ``` 内的内容
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            return match.group(1)
        # 尝试匹配第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return text[start:end + 1]
        return text

    @staticmethod
    def _format_search_results(
        results: list[SearchResult],
        extracted_content: dict[str, Optional[str]],
    ) -> str:
        """将搜索结果格式化为LLM可读的文本"""
        lines: list[str] = []

        for i, r in enumerate(results[:15], 1):
            content = extracted_content.get(r.url)
            lines.append(f"## 来源{i} [{r.source_level}级]")
            lines.append(f"标题: {r.title}")
            lines.append(f"链接: {r.url}")
            lines.append(f"来源: {r.source_name}")
            if r.published_date:
                lines.append(f"时间: {r.published_date}")
            lines.append(f"摘要: {r.snippet}")

            if content:
                lines.append(f"正文内容:\n{content[:3000]}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _format_rating_summary(results: list[SearchResult]) -> str:
        """生成信源评级摘要"""
        level_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "未知": 0}
        for r in results:
            level_counts[r.source_level.value] = level_counts.get(r.source_level.value, 0) + 1

        lines = [
            f"共搜索到{len(results)}条结果，信源评级分布：",
            f"  A级（官方/学术）: {level_counts['A']}条",
            f"  B级（知名媒体）: {level_counts['B']}条",
            f"  C级（中小媒体/博客）: {level_counts['C']}条",
            f"  D级（自媒体/论坛）: {level_counts['D']}条",
            f"  未知: {level_counts['未知']}条",
        ]

        # 列出A/B级来源
        high = [r for r in results if r.source_level in (SourceLevel.A, SourceLevel.B)]
        if high:
            lines.append("\n高可信信源:")
            for r in high[:10]:
                lines.append(f"  - [{r.source_level.value}] {r.source_name}: {r.url[:60]}...")

        return "\n".join(lines)

    @staticmethod
    async def _progress(
        callback: Optional[callable],
        status: AnalysisStatus,
        message: str,
        percentage: int,
        result: Optional[AnalysisResult] = None,
    ):
        if callback:
            progress = AnalysisProgress(
                status=status,
                message=message,
                percentage=percentage,
                result=result,
            )
            await callback(progress)

    @staticmethod
    def _is_definitely_false(confidence: str) -> bool:
        """检查置信度文字是否明确表示新闻为假"""
        false_keywords = ["明确为假", "确认为假", "完全虚假", "辟谣", "造谣", "纯属虚构"]
        return any(kw in confidence for kw in false_keywords)

    @staticmethod
    def _estimate_prob_from_evidence(evidence_list: list[dict]) -> float | None:
        """根据论据正反比例估算真实概率，返回None表示无法估算"""
        support = sum(1 for e in evidence_list if e.get("stance") == "支持")
        oppose = sum(1 for e in evidence_list if e.get("stance") == "反对")
        total = support + oppose
        if total == 0:
            return None
        return round(50.0 + (support - oppose) / total * 50.0, 1)

    @staticmethod
    def _empty_result(reason: str) -> AnalysisResult:
        """返回空结果"""
        return AnalysisResult(
            background="分析失败",
            summary=f"无法完成分析: {reason}",
            truth_probability=50.0,
            confidence_level=f"低 - {reason}",
            evidence_list=[],
            reasoning=reason,
        )
