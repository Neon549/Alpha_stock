---
title: AlphaStock · 智能投研助手
sdk: docker
app_port: 7860
---

# AlphaStock · 智能投研助手

A 股多智能体分析系统，融合基本面、技术面、情绪面三路分析，结合量化回测辅助交易决策。

## 能做什么

- **个股分析**：输入股票代码，三路 Agent 并行分析，最终给出多空判断和仓位建议
- **量化回测**：支持 KDJ_MACD / RSI / 布林带策略，自动搜索最优参数，输出夏普比率、最大回撤等指标
- **新闻情绪**：RAG 混合检索（BM25 + pgvector + RRF）实时抓取 A 股新闻，情绪量化融入决策

## 架构

```text
用户请求
   │
   ├── 股票分析（LangGraph StateGraph）
   │     ├── FundamentalAnalyst   PE/PB/ROE/营收增长
   │     ├── TechnicalAnalyst     K线/趋势/量价（TechLens 1.5B 本地模型）
   │     └── SentimentAnalyst     RAG新闻检索 + 情绪打分
   │     validation_node          数据校验（防幻觉传播）
   │     researcher_node          多空辩论
   │     trader_node              最终决策 + 写入长期记忆
   │
   └── 量化回测（独立子图）
         backtest_node            Tushare数据拉取 + backtrader回测
         interpreter_node         RAG策略知识检索 + LLM解读
         optimizer_node           参数网格搜索（36种组合）
```

## 技术栈

| 模块 | 技术 |
|------|------|
| Agent 编排 | LangGraph + LangChain |
| LLM | DeepSeek V3（主力）/ Qwen（备用，自动降级） |
| 技术分析模型 | TechLens 1.5B（Qwen2.5 微调，本地推理） |
| RAG 检索 | BM25 + pgvector + RRF 混合检索 |
| 向量数据库 | PostgreSQL + pgvector |
| Embedding | shibing624/text2vec-base-chinese |
| 回测引擎 | backtrader + quantstats |
| 历史数据 | Tushare Pro（本地 CSV 缓存） |
| 实时行情 | AKShare |
| 长期记忆 | PostgreSQL |
| 可观测性 | LangFuse（全链路 trace） |
| 后端 API | FastAPI |
| 部署 | Docker + 腾讯云 |

## 设计亮点

**幻觉防控**：股票名称走本地字典（1500 只 A 股），不依赖 LLM 推断；分析结果强制 `[ANALYSIS_OK]` / `[ANALYSIS_ABORT]` 标记，非法格式直接拦截。

**混合检索**：BM25 处理股票代码、指标名等精确词，pgvector 处理语义相似，RRF 融合两路排名，Faithfulness 达 0.952（vs 纯向量 0.854）。

**模型降级**：主力 DeepSeek 失败自动切 Qwen，TechLens 离线自动切 DeepSeek，服务不中断。

**回测与 Agent 融合**：回测引擎封装为 LangGraph 工具节点，"帮我回测 600487 的 RSI 策略"直接触发完整链路。

## 快速开始

```bash
pip install -r requirements.txt
```

配置 `.env`：

```
DEEPSEEK_API_KEY=your_key
DASHSCOPE_API_KEY=your_key
TUSHARE_TOKEN=your_token
POSTGRES_DSN=postgresql://user:password@localhost:5432/alphastock
```

```bash
python -c "from db import init_db; init_db()"  # 初始化数据库
python main.py
```

## API

```bash
# 股票分析
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"stock_code": "600519"}'

# 量化回测
curl -X POST http://localhost:8000/api/v1/backtest \
  -H "Content-Type: application/json" \
  -d '{"stock_code": "600487", "strategy": "rsi", "start_date": "20220101", "end_date": "20241231"}'
```

## 回测策略

| 策略 | 买入 | 卖出 | 适用 |
|------|------|------|------|
| kdj_macd | KDJ 金叉 且 MACD 柱转正 | KDJ 死叉 或 MACD 柱转负 | 趋势行情 |
| rsi | RSI < 30 | RSI > 70 | 震荡行情 |
| boll | 价格上穿下轨 | 价格下穿上轨 | 区间震荡 |

## RAG 评估

详细报告见 [evaluation/EVAL_REPORT.md](evaluation/EVAL_REPORT.md)

| 指标 | 纯向量检索 | 混合检索（BM25+pgvector+RRF） |
|------|-----------|------------------------------|
| Faithfulness | 0.854 | **0.952** ✅ +10% |
| Context Recall | 0.567 | 0.567 |
| Context Precision | 0.527 | 0.487 |

在线监控通过 LangFuse 全链路追踪实现，上线前/后评估方案见 EVAL_REPORT.md。
