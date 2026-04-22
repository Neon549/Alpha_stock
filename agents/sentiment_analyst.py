# agents/sentiment_analyst.py

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from config.llm_config import quick_llm
from tools.akshare_tools import get_stock_price
from rag.retriever import retrieve_stock_news, refresh_news_index

SYSTEM_PROMPT = """你是一位专业的A股市场情绪分析师，专注于通过新闻资讯和市场数据判断市场情绪。

你必须严格遵守以下规则：

【硬性规则】
1. 只能基于工具返回的真实新闻检索结果和真实行情数据分析。
2. 如果新闻检索工具或行情工具返回 [TOOL_ERROR] / 检索失败 / 数据不足，则必须立即停止分析。
3. 禁止把新闻中的宣传性措辞、猜测性措辞、未来展望，直接当成已验证事实。
4. 禁止编造：
   - 订单
   - 政策利好
   - 资金流
   - 实时涨停逻辑
   - 买单规模
   - 未被工具直接返回的事件
5. 如果无法获取实时行情，不得对市场热度做确定性判断。
6. 你必须在最终输出第一行写出：
   - [ANALYSIS_OK]
   或
   - [ANALYSIS_ABORT]

【执行步骤】
1. 先分别检索：
   - 业绩
   - 订单
   - 政策
2. 再调用 get_stock_price 获取行情核验
3. 若新闻或行情任一关键环节失败，则中止分析

【输出要求】
- 如果可以分析，严格输出：

[ANALYSIS_OK]
## 情绪分析报告

### 1. 股票信息核验
股票代码：[代码]
股票名称：[仅可填写工具明确返回的名称；若未验证则写“名称未验证”]
数据可靠性：[高/中/低]

### 2. 新闻情绪
[只总结工具检索到的内容，并明确哪些是事实、哪些只是展望]

### 3. 市场热度
[只有在行情工具成功时才能分析；否则必须写“无法验证”]

### 4. 情绪评分
评分：[-2到+2]
理由：[必须基于工具返回内容]

### 5. 近期催化剂
正面：[只写已检索到的、且描述明确的事项；否则写“暂无可验证信息”]
负面：[只写已检索到的明确风险；否则写“暂无可验证信息”]

- 如果不能分析，严格输出：

[ANALYSIS_ABORT]
原因：[明确说明是新闻检索失败、行情数据不足、或存在无法验证的信息]
结论：数据不足，无法分析。禁止基于假设输出情绪评分、市场热度或催化剂判断。
"""

SENTIMENT_TOOLS = [
    retrieve_stock_news,
    refresh_news_index,
    get_stock_price,
]


def create_sentiment_analyst():
    return create_react_agent(
        model=quick_llm,
        tools=SENTIMENT_TOOLS,
        prompt=SYSTEM_PROMPT,
    )


def _post_check_sentiment_output(text: str, stock_code: str) -> str:
    text = (text or "").strip()

    if not text:
        return (
            "[ANALYSIS_ABORT]\n"
            "原因：情绪分析师未返回任何内容。\n"
            "结论：数据不足，无法分析。禁止基于假设输出情绪评分、市场热度或催化剂判断。"
        )

    # 这些都视为必须中止
    fatal_markers = [
        "[TOOL_ERROR]",
        "数据不足，禁止基于假设继续分析",
        "检索失败",
        "无法获取实时行情",
    ]
    if any(marker in text for marker in fatal_markers):
        return (
            "[ANALYSIS_ABORT]\n"
            "原因：情绪分析过程中新闻检索或行情核验失败。\n"
            "结论：数据不足，无法分析。禁止基于假设输出情绪评分、市场热度或催化剂判断。"
        )

    if text.startswith("[ANALYSIS_ABORT]"):
        return text

    if not text.startswith("[ANALYSIS_OK]"):
        return (
            "[ANALYSIS_ABORT]\n"
            "原因：情绪分析结果未遵循规定格式，可信度不足。\n"
            "结论：数据不足，无法分析。禁止基于假设输出情绪评分、市场热度或催化剂判断。"
        )

    if stock_code not in text:
        return (
            "[ANALYSIS_ABORT]\n"
            "原因：情绪分析结果未正确引用股票代码，存在一致性风险。\n"
            "结论：数据不足，无法分析。禁止基于假设输出情绪评分、市场热度或催化剂判断。"
        )

    return text


def run_sentiment_analysis(stock_code: str) -> str:
    agent = create_sentiment_analyst()

    result = agent.invoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        f"请对股票 {stock_code} 进行市场情绪分析。"
                        f"先检索最新的业绩、订单和政策相关新闻，再核验行情。"
                        f"如果新闻检索失败、行情不足、或无法验证市场热度，必须输出 [ANALYSIS_ABORT]。"
                    )
                )
            ]
        }
    )

    final_text = result["messages"][-1].content
    return _post_check_sentiment_output(final_text, stock_code)