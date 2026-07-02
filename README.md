# TruthCatcher - AI 实时新闻真伪辨别工具

基于大语言模型的实时新闻事实核查平台。输入新闻文本或链接，系统自动搜索全网信息、交叉验证信源、加权评分，给出客观公正的真伪判断。

## 核心功能

- **核心主张加权评分** — AI 提炼 3-5 条核心主张，分配权重，加权计算总体真实概率
- **信源可信度评级** — A/B/C/D 四级自动评级，覆盖 100+ 已知域名
- **多源交叉验证** — 每条论据标注"已交叉验证"或"单一信源"
- **传播路径追踪** — 追溯新闻首发来源和跨平台传播时间线
- **虚假信号检测** — 自动识别标题党、情绪煽动、信源缺失、逻辑矛盾
- **谣言数据库** — 已知谣言快速匹配，新谣言自动入库
- **浏览器插件** — Edge/Chrome 扩展，选中页面文字一键分析
- **流式分析展示** — 搜索→提取→分析→结果，渐进式渲染
- **分析历史记录** — SQLite 持久化存储，下拉框回顾过往分析
- **URL 自动抓取** — 粘贴新闻链接自动提取正文（httpx / Jina Reader / Playwright 三级兜底）
- **一键下载报告** — 导出 TXT 格式分析报告
- **多 Provider 支持** — DeepSeek V4-Flash / Anthropic Claude / OpenAI 兼容接口

## 快速开始

### 1. 环境准备

- Python 3.10+
- DeepSeek API Key（或 Anthropic / OpenAI）
- SerpAPI Key

### 2. 安装配置

```bash
git clone https://github.com/QileGuai492/truthcatcher-ai.git
cd truthcatcher-ai

cp .env.example .env
# 编辑 .env，填入 API Key：
#   DEEPSEEK_API_KEY=sk-xxx
#   SERPAPI_KEY=xxx

pip install -r requirements.txt

# 安装 Playwright 浏览器（URL 抓取 JS 渲染页面需要）
playwright install chromium

# 启动
python run.py
```

浏览器访问 `http://127.0.0.1:7860`。

### 3. 安装浏览器插件

1. 打开 Edge/Chrome，地址栏输入 `edge://extensions` 或 `chrome://extensions`
2. 开启"开发者模式"
3. 点击"加载已解压的扩展程序"，选择 `extension/` 文件夹
4. 打开任意新闻页面，选中文字，点击插件图标 → 获取页面选中文字

## 项目结构

```
truthcatcher-ai/
├── run.py                   # 启动入口
├── start.bat                # Windows 一键启动
├── requirements.txt         # Python 依赖
├── extension/               # 浏览器插件
│   ├── manifest.json
│   ├── popup.html
│   └── popup.js
├── app/
│   ├── config.py            # 配置管理（多Provider）
│   ├── main.py              # FastAPI REST API
│   ├── models/
│   │   └── analysis.py      # Pydantic 数据模型
│   ├── prompts/
│   │   └── analysis.py      # Prompt 模板
│   ├── services/
│   │   ├── llm_client.py    # 统一LLM客户端
│   │   ├── llm_analyzer.py  # 核心分析流水线
│   │   ├── search.py        # SerpAPI 搜索 + 关键词生成
│   │   ├── crawler.py       # 网页正文提取（三级兜底）
│   │   ├── source_rater.py  # 信源评级
│   │   ├── history.py       # 分析历史记录
│   │   ├── rumor_db.py      # 谣言数据库
│   │   └── cache.py         # 结果缓存
│   └── ui/
│       └── gradio_app.py    # Gradio Web 界面
├── .env.example             # 环境变量模板
└── .gitignore
```

## 技术栈

- **前端**: Gradio 5.x（响应式，PC/移动端适配）
- **后端**: Python 3.13 + FastAPI
- **AI 服务**: DeepSeek V4-Flash（主力）/ Anthropic Claude / OpenAI
- **搜索**: SerpAPI（Google）
- **网页抓取**: httpx + readability + Jina Reader + Playwright
- **数据**: SQLite（历史记录 + 谣言库 + 缓存）

## License

MIT
