# TruthCatcher - AI 实时新闻真伪辨别工具

基于大语言模型的实时新闻事实核查平台。输入新闻文本或链接，系统自动搜索全网信息、交叉验证信源、流式生成分析结果，给出客观公正的真伪判断。

## 核心功能

- **全网信息采集** — 多搜索引擎并发检索（SerpAPI + DuckDuckGo），自动抓取网页正文
- **信源可信度评级** — A/B/C/D 四级自动评级，覆盖 100+ 已知域名
- **多源交叉验证** — 每条论据需 ≥2 个独立信源确认，单一信源自动标记
- **加权真实度评分** — AI 提炼核心主张并分配权重，加权计算总体真实概率
- **传播路径追踪** — 追溯新闻首发来源和跨平台传播时间线
- **虚假信号检测** — 自动识别标题党、情绪煽动、信源缺失、逻辑矛盾
- **谣言数据库** — 已确认谣言快速匹配，新谣言自动入库
- **流式分析展示** — 渐进式渲染搜索→分析→结果全过程
- **历史记录** — SQLite 持久化存储，支持回顾过往分析
- **URL 自动抓取** — 粘贴新闻链接自动提取正文并分析

## 快速开始

### 1. 环境准备

- Python 3.10+
- DeepSeek API Key（或 Anthropic / OpenAI 兼容）
- SerpAPI Key

### 2. 安装配置

```bash
# 克隆仓库
git clone https://github.com/你的用户名/TruthCatcher.git
cd TruthCatcher

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key：
#   DEEPSEEK_API_KEY=sk-xxx
#   SERPAPI_KEY=xxx

# 安装依赖
pip install -r requirements.txt

# 启动（Windows 可直接双击 start.bat）
python run.py
```

浏览器访问 `http://127.0.0.1:7860` 即可使用。

### 3. API 模式

```bash
python run.py --api
# API 文档: http://127.0.0.1:7860/docs
```

## 项目结构

```
TruthCatcher/
├── run.py                  # 启动入口
├── start.bat               # Windows 一键启动脚本
├── requirements.txt        # Python 依赖
├── app/
│   ├── config.py           # 配置管理（多Provider支持）
│   ├── main.py             # FastAPI REST API
│   ├── models/
│   │   └── analysis.py     # Pydantic 数据模型
│   ├── prompts/
│   │   └── analysis.py     # Prompt 模板
│   ├── services/
│   │   ├── search.py       # 多引擎搜索（SerpAPI/DuckDuckGo/Bing）
│   │   ├── crawler.py      # 网页正文提取
│   │   ├── source_rater.py # 信源可信度评级
│   │   ├── llm_client.py   # 统一LLM客户端（Anthropic/DeepSeek/OpenAI）
│   │   ├── llm_analyzer.py # 核心分析流水线
│   │   ├── history.py      # 分析历史记录
│   │   ├── rumor_db.py     # 谣言数据库
│   │   └── cache.py        # 结果缓存
│   └── ui/
│       └── gradio_app.py   # Gradio Web 界面
├── .env.example            # 环境变量模板
└── .gitignore
```

## 技术栈

- **后端**: Python 3.13 + FastAPI
- **AI 服务**: DeepSeek V4-Flash / Anthropic Claude / OpenAI 兼容接口
- **搜索**: SerpAPI + DuckDuckGo（免费）
- **前端**: Gradio 5.x（响应式，PC/移动端适配）
- **数据**: SQLite（历史记录 + 谣言库）

## License

MIT
