# agents/technical_analyst.py

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from config.llm_config import quick_llm
from tools.akshare_tools import get_stock_price, get_stock_history

SYSTEM_PROMPT = """你是一位专业的A股技术面分析师，专注于通过价格和成交量数据判断股票的短中期走势。

你必须严格遵守以下规则：

【硬性规则】
1. 只能基于工具返回的真实K线/价格数据分析，禁止补充、猜测、脑补任何未出现的数据。
2. 如果 get_stock_history 或 get_stock_price 返回 [TOOL_ERROR]，必须立即停止分析。
3. 如果历史价格字段存在空值、NaN、字段不完整、样本不足，也必须停止分析。
4. 禁止在数据不足时编造：
   - 支撑位
   - 压力位
   - 目标价
   - 止损位
   - 趋势判断
5. 你必须在最终输出第一行写出：
   - [ANALYSIS_OK]
   或
   - [ANALYSIS_ABORT]

【执行步骤】
1. 先调用 get_stock_history(symbol, days=30)
2. 再调用 get_stock_price 做最新价格核验
3. 若任一步失败，直接中止

【输出要求】
- 如果可以分析，严格输出：

[ANALYSIS_OK]
## 技术面分析报告

### 1. 股票信息核验
股票代码：[代码]
股票名称：[仅可填写工具明确返回的名称；若未验证则写“名称未验证”]
数据可靠性：[高/中/低]

### 2. 趋势分析
[只基于工具返回的历史数据分析]

### 3. 量价关系
[只基于工具返回的成交量与价格关系分析]

### 4. 关键价位
支撑位：[仅在数据充分时填写]
压力位：[仅在数据充分时填写]

### 5. 短期展望
方向：[看多/看空/中性]
目标价：[若无法可靠判断则写“暂不设定”]
止损位：[若无法可靠判断则写“暂不设定”]

- 如果不能分析，严格输出：

[ANALYSIS_ABORT]
原因：[明确说明是历史数据不足、关键价格字段空值、或工具报错]
结论：数据不足，无法分析。禁止基于假设生成支撑位、压力位、目标价和止损位。
"""

TECHNICAL_TOOLS = [
    get_stock_price,
    get_stock_history,
]


def create_technical_analyst():
    return create_react_agent(
        model=quick_llm,
        tools=TECHNICAL_TOOLS,
        prompt=SYSTEM_PROMPT,
    )


def _post_check_technical_output(text: str, stock_code: str) -> str:
    text = (text or "").strip()

    if not text:
        return (
            "[ANALYSIS_ABORT]\n"
            "原因：技术面分析师未返回任何内容。\n"
            "结论：数据不足，无法分析。禁止基于假设生成支撑位、压力位、目标价和止损位。"
        )

    if "[TOOL_ERROR]" in text or "数据不足，禁止基于假设继续分析" in text:
        return (
            "[ANALYSIS_ABORT]\n"
            "原因：技术面分析过程中关键工具返回错误或历史数据不足。\n"
            "结论：数据不足，无法分析。禁止基于假设生成支撑位、压力位、目标价和止损位。"
        )

    if text.startswith("[ANALYSIS_ABORT]"):
        return text

    if not text.startswith("[ANALYSIS_OK]"):
        return (
            "[ANALYSIS_ABORT]\n"
            "原因：技术面分析结果未遵循规定格式，可信度不足。\n"
            "结论：数据不足，无法分析。禁止基于假设生成支撑位、压力位、目标价和止损位。"
        )

    if stock_code not in text:
        return (
            "[ANALYSIS_ABORT]\n"
            "原因：技术面分析结果未正确引用股票代码，存在一致性风险。\n"
            "结论：数据不足，无法分析。禁止基于假设生成支撑位、压力位、目标价和止损位。"
        )

    return text


def run_technical_analysis(stock_code: str) -> str:
    agent = create_technical_analyst()

    result = agent.invoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        f"请对股票 {stock_code} 进行技术面分析，获取最近30天K线数据。"
                        f"如果历史价格字段空值、NaN、字段不完整或任一工具报错，必须输出 [ANALYSIS_ABORT]。"
                    )
                )
            ]
        }
    )

    final_text = result["messages"][-1].content
    return _post_check_technical_output(final_text, stock_code)