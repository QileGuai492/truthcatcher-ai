"""分析结果数据模型 -- 定义输入输出的 Pydantic Schema"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# 输入模型
# ============================================================


class NewsInput(BaseModel):
    """用户输入的新闻"""

    content_type: str = Field(default="text", description="输入类型: text / url")
    content: str = Field(description="新闻文本或URL")
    source_name: Optional[str] = Field(default=None, description="新闻来源名称（若已知）")


# ============================================================
# 中间模型
# ============================================================


class SourceLevel(str, Enum):
    """信源可信度等级"""
    A = "A"  # 官方政府网站、权威学术期刊
    B = "B"  # 知名媒体、行业研究报告
    C = "C"  # 中小媒体、行业博客
    D = "D"  # 自媒体、论坛、匿名来源
    UNKNOWN = "未知"


class SearchResult(BaseModel):
    """单条搜索结果"""
    title: str
    url: str
    snippet: str
    source_name: str = ""
    published_date: Optional[str] = None
    source_level: SourceLevel = SourceLevel.UNKNOWN


class Evidence(BaseModel):
    """单条论据"""
    content: str
    stance: str = Field(description="支持 / 反对 / 中立")
    source_url: str
    source_name: str
    source_level: SourceLevel
    cross_verified: bool = Field(default=False, description="是否被≥2个独立信源交叉确认")
    verified_by: list[str] = Field(default_factory=list, description="交叉确认该论据的其他信源名称")
    credibility_note: str = Field(default="", description="关于该证据可信度的补充说明")
    bias_disclosure: str = Field(default="", description="信源立场倾向标注")


class PropagationEvent(BaseModel):
    """传播路径中的单个节点"""
    time: str = Field(description="时间描述")
    platform: str = Field(description="平台/媒体名称")
    description: str = Field(description="事件描述")


class CoreClaim(BaseModel):
    """新闻中提炼的核心信息主张及其真实度"""
    claim: str = Field(description="核心主张简述")
    truth_score: float = Field(ge=0.0, le=100.0, description="该主张的真实度 0-100%")
    weight: float = Field(ge=0.0, le=1.0, description="该主张在整体结论中的权重，越核心的主张权重越高")


# ============================================================
# 输出模型 -- 完整分析结果
# ============================================================


class AnalysisResult(BaseModel):
    """最终返回给用户的分析结果"""

    # 新闻来龙去脉
    background: str = Field(description="事件的前因后果与完整背景")

    # 新闻摘要
    summary: str = Field(description="200字以内核心事实概括")

    # 真实概率
    truth_probability: float = Field(ge=0.0, le=100.0, description="真实性概率 0-100%")
    confidence_level: str = Field(description="置信度说明: 高/中/低 及原因")

    # 论据列表
    evidence_list: list[Evidence] = Field(default_factory=list, description="正反论据列表")

    # 虚假信号预警
    warnings: list[str] = Field(default_factory=list, description="检测到的虚假/可疑信号列表")

    # 传播路径
    propagation: list[PropagationEvent] = Field(default_factory=list, description="新闻传播路径时间线")

    # 谣言匹配
    rumor_match: bool = Field(default=False, description="是否匹配已知谣言数据库")
    rumor_reference: str = Field(default="", description="匹配到的已知谣言说明")

    # 核心主张拆解
    core_claims: list[CoreClaim] = Field(default_factory=list, description="新闻核心主张及其各自真实度")

    # 论证过程
    reasoning: str = Field(description="从论据到结论的完整逻辑推理链")

    # 元信息
    analyzed_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="分析时间戳")
    search_sources_count: int = Field(default=0, description="搜索到的信源总数")
    reliable_sources_count: int = Field(default=0, description="筛选后的可靠信源数")


# ============================================================
# 分析请求追踪
# ============================================================


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    SEARCHING = "searching"
    EXTRACTING = "extracting"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisProgress(BaseModel):
    """分析进度 -- 用于SSE推送"""
    status: AnalysisStatus
    message: str
    percentage: int = Field(ge=0, le=100)
    result: Optional[AnalysisResult] = None
