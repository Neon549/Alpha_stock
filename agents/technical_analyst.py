# agents/technical_analyst.py

from langchain_core.messages import HumanMessage

from config.llm_config import quick_llm
from tools.akshare_tools import get_stock_price, get_stock_history


SYSTEM_PROMPT = """你是一位专业的A股技术面分析师，专注于通过价格和成交量数据判断股票的短中期走势。

你必须严格遵守以下规则：

【硬性规则】
1. 你只能基于下方“工具已返回结果”中的真实K线/价格数据分析。
2. 禁止补充、猜测、脑补任何未出现的数据。
3. 禁止编造支撑位、压力位、目标价、止损位。
4. 若工具结果中存在 [TOOL_ERROR]，必须停止分析。
5. 你必须在最终输出第一行写：
   - [ANALYSIS_OK]
   或
   - [ANALYSIS_ABORT]

【输出要求】
- 如果可以分析，严格输出：

[ANALYSIS_OK]
## 技术面分析报告

### 1. 股票信息核验
股票代码：[代码]
股票名称：[仅填写工具明确返回的名称]
数据可靠性：[高/中/低]

### 2. 趋势分析
[只基于工具返回的历史价格数据分析]

### 3. 量价关系
[只基于工具返回的成交量与价格关系分析]

### 4. 关键价位
支撑位：[如果无法可靠判断，写“暂不设定”]
压力位：[如果无法可靠判断，写“暂不设定”]

### 5. 短期展望
方向：[看多/看空/中性]
目标价：[若无法可靠判断则写“暂不设定”]
止损位：[若无法可靠判断则写“暂不设定”]

- 如果不能分析，严格输出：

[ANALYSIS_ABORT]
原因：[明确说明原因]
结论：数据不足，无法分析。禁止基于假设生成支撑位、压力位、目标价和止损位。
"""


def _abort(reason: str) -> str:
    return (
        "[ANALYSIS_ABORT]\n"
        f"原因：{reason}\n"
        "结论：数据不足，无法分析。禁止基于假设生成支撑位、压力位、目标价和止损位。"
    )


def _post_check_technical_output(text: str, stock_code: str) -> str:
    text = (text or "").strip()

    if not text:
        return _abort("技术面分析师未返回任何内容。")

    if text.startswith("[ANALYSIS_ABORT]"):
        return text

    if not text.startswith("[ANALYSIS_OK]"):
        return _abort("技术面分析结果未遵循规定格式，可信度不足。")

    if stock_code not in text:
        return _abort("技术面分析结果未正确引用股票代码，存在一致性风险。")

    return text


def run_technical_analysis(stock_code: str) -> str:
    # 1) 先程序化调用工具，并做一次重试，降低外部数据源瞬时失败的影响
    history_result = get_stock_history.invoke({"symbol": stock_code, "days": 30})
    if "[TOOL_ERROR]" in history_result:
        history_result = get_stock_history.invoke({"symbol": stock_code, "days": 30})

    price_result = get_stock_price.invoke({"symbol": stock_code})
    if "[TOOL_ERROR]" in price_result:
        price_result = get_stock_price.invoke({"symbol": stock_code})

    # 2) 工具仍失败则直接中止
    if "[TOOL_ERROR]" in history_result:
        return _abort("历史K线工具返回错误，无法完成技术面分析。")

    if "[TOOL_ERROR]" in price_result:
        return _abort("行情核验工具返回错误，无法完成股票信息交叉核验。")

    # 3) 工具成功后，只让 LLM 总结，不再让模型自己判断工具健康性
    prompt = f"""{SYSTEM_PROMPT}

以下是工具已返回结果，请严格基于这些内容输出最终报告：

## 股票代码
{stock_code}

## 工具结果一：历史K线
{history_result}

## 工具结果二：行情核验
{price_result}
"""

    response = quick_llm.invoke([HumanMessage(content=prompt)])
    final_text = response.content

    return _post_check_technical_output(final_text, stock_code)