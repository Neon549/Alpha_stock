---
title: AlphaStock · 智能投研助手
sdk: docker
app_port: 7860
---

# AlphaStock · 智能投研助手

分析基本面、技术面、情绪面，结合Alpha因子回测，辅助A股交易决策。

## 项目简介

这是一个面向 A股场景的智能交易分析系统，融合了 AI Agent 技术栈与量化交易技术栈，核心能力包括：

**智能分析模块**
- 基本面分析（PE/PB/ROE/营收增长等财务指标）
- 技术面分析（历史K线、趋势、量价关系）
- 情绪分析（RAG新闻检索 + 市场热度）
- 多智能体并行协作决策（ThreadPoolExecutor并行）
- 历史决策长期记忆（SQLite持久化）
- 数据校验节点（防止幻觉传播）

**量化回测模块（新增）**

- 多策略回测引擎（KDJ_MACD / RSI / 布林带）
- Tushare Pro 真实A股历史数据接入（本地CSV缓存）
- quantstats 专业绩效报告（夏普比率、最大回撤、月度热力图）
- RAG知识库增强解读（策略理论知识检索 + LLM专业分析）
- 参数网格搜索优化（自动搜索最优参数组合）
- 回测历史记录（SQLite长期存储，支持历史对比）

## 系统架构

```text
用户请求
   │
   ├── 股票分析流程
   │     analysts_node（并行）
   │     ├── FundamentalAnalyst  基本面分析
   │     ├── TechnicalAnalyst    技术面分析
   │     └── SentimentAnalyst    情绪分析（RAG新闻检索）
   │     validation_node         数据校验
   │     researcher_node         多空辩论
   │     trader_node             最终决策 + 存入记忆
   │
   └── 量化回测流程（独立子图）
         backtest_node           数据拉取 + backtrader回测
         interpreter_node        RAG策略知识检索 + LLM解读
         optimizer_node          参数网格搜索 + 最优参数输出
```

## 技术栈

| 模块 | 技术 |
|------|------|
| Agent编排 | LangGraph + LangChain |
| LLM | Qwen-Plus / Qwen-Turbo（DashScope） |
| 回测引擎 | backtrader |
| 绩效分析 | quantstats |
| 历史数据 | Tushare Pro |
| 实时行情 | AKShare + yfinance |
| RAG向量库 | ChromaDB + HuggingFace Embeddings |
| 长期记忆 | SQLite |
| 后端API | FastAPI |
| 部署 | Docker + Hugging Face Spaces |

## 项目结构

```text
.
├── agents/
│   ├── fundamental_analyst.py   基本面分析Agent
│   ├── technical_analyst.py     技术面分析Agent
│   ├── sentiment_analyst.py     情绪分析Agent
│   └── trader.py                交易决策Agent
├── backtest/                    量化回测模块（新增）
│   ├── data_loader.py           Tushare数据接入 + 缓存
│   ├── strategies.py            KDJ_MACD / RSI / BOLL策略
│   ├── engine.py                回测引擎 + quantstats报告
│   ├── optimizer.py             参数网格搜索优化器
│   └── data_cache/              本地CSV缓存
├── api/
│   └── routes.py                FastAPI路由（含回测接口）
├── config/
│   └── llm_config.py            LLM配置
├── graph/
│   ├── state.py                 全局State定义
│   └── trading_graph.py         LangGraph工作流编排
├── memory/
│   └── long_term.py             SQLite长期记忆
├── rag/
│   ├── indexer.py               新闻RAG索引构建
│   ├── retriever.py             新闻检索工具
│   ├── strategy_indexer.py      策略知识库索引（新增）
│   └── strategy_docs.py         量化策略知识文档（新增）
├── tools/
│   ├── akshare_tools.py         行情数据工具
│   ├── backtest_tools.py        回测工具（新增）
│   └── stock_name_dict.py       A股名称本地字典（新增）
├── reports/                     quantstats HTML报告输出
├── main.py
├── requirements.txt
├── README.md
└── Dockerfile
```

## 快速开始

### 环境配置

```bash
pip install -r requirements.txt
```

在 `.env` 文件中配置：

```
DASHSCOPE_API_KEY=your_qwen_api_key
TUSHARE_TOKEN=your_tushare_token
```

### 启动服务

```bash
python main.py
```

### API 使用

**股票分析**
```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"stock_code": "600487"}'
```

**量化回测**
```bash
curl -X POST http://localhost:8000/api/v1/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "stock_code": "600487",
    "strategy": "rsi",
    "start_date": "20220101",
    "end_date": "20241231",
    "initial_cash": 100000
  }'
```

**查看可用策略**
```bash
curl http://localhost:8000/api/v1/backtest/strategies
```

**查看历史回测记录**
```bash
curl http://localhost:8000/api/v1/backtest/history/600487
```

## 回测策略说明

| 策略 | 买入信号 | 卖出信号 | 适用行情 |
|------|---------|---------|---------|
| kdj_macd | KDJ金叉 且 MACD柱由负转正 | KDJ死叉 或 MACD柱由正转负 | 趋势行情 |
| rsi | RSI < 30（超卖） | RSI > 70（超买） | 震荡行情 |
| boll | 价格上穿布林下轨 | 价格下穿布林上轨 | 区间震荡 |

## 设计亮点

**幻觉防控**：股票名称使用本地字典（1500只A股），不依赖LLM推断；分析结果强制要求`[ANALYSIS_OK]`/`[ANALYSIS_ABORT]`标记，非法格式直接拦截。

**RAG双轨**：新闻RAG用于情绪分析，策略知识RAG用于回测解读，两套索引独立互不干扰。

**回测与Agent融合**：回测引擎封装为LangGraph工具节点，实现自然语言驱动回测——"帮我回测600487的RSI策略"直接触发完整分析链路。

**参数自动优化**：网格搜索覆盖36种参数组合，按夏普比率排序，输出Top3最优参数，辅助策略调优。