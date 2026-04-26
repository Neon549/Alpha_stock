# agents/fundamental_analyst.py

from langchain_core.messages import HumanMessage

from config.llm_config import deep_llm
from tools.akshare_tools import get_stock_price, get_financial_indicator


SYSTEM_PROMPT = """你是一位专业的A股基本面分析师，专注于通过财务数据评估股票的内在价值。

你必须严格遵守以下规则：

【硬性规则】
1. 你只能基于下方“工具已返回结果”中的内容分析。
2. 禁止补充、猜测、脑补任何未出现的数据。
3. 禁止编造公司名称、财务指标、评级依据、接口状态。
4. 若工具结果中存在 [TOOL_ERROR]，必须停止分析。
5. 你必须在最终输出第一行写：
   - [ANALYSIS_OK]
   或
   - [ANALYSIS_ABORT]

【输出要求】
- 如果可以分析，严格输出：

[ANALYSIS_OK]
## 基本面分析报告

### 1. 股票信息核验
股票代码：[代码]
股票名称：[仅填写工具明确返回的名称]
数据可靠性：[高/中/低]
核验结论：[简述]

### 2. 估值分析
[只分析工具返回的PE/PB/市值等]

### 3. 盈利能力
[只分析工具返回的ROE/营收增长率/毛利率等]

### 4. 财务健康
[只分析工具返回的负债率/现金流相关信息；若缺失必须明确写“未提供”]

### 5. 综合评级
评级：[强烈买入/买入/中性/卖出/强烈卖出]
理由：[基于已验证数据]
风险提示：[主要风险]

- 如果不能分析，严格输出：

[ANALYSIS_ABORT]
原因：[明确说明原因]
结论：数据不足，无法分析。禁止基于假设给出评级或投资建议。
"""


def _abort(reason: str) -> str:
    return (
        "[ANALYSIS_ABORT]\n"
        f"原因：{reason}\n"
        "结论：数据不足，无法分析。禁止基于假设给出评级或投资建议。"
    )


def _post_check_fundamental_output(text: str, stock_code: str) -> str:
    text = (text or "").strip()

    if not text:
        return _abort("基本面分析师未返回任何内容。")

    if text.startswith("[ANALYSIS_ABORT]"):
        return text

    if not text.startswith("[ANALYSIS_OK]"):
        return _abort("基本面分析结果未遵循规定格式，可信度不足。")

    if stock_code not in text:
        return _abort("基本面分析结果未正确引用股票代码，存在一致性风险。")

    return text


def run_fundamental_analysis(stock_code: str) -> str:
    # 1. 先程序化调用工具
    financial_result = get_financial_indicator.invoke({"symbol": stock_code})
    price_result = get_stock_price.invoke({"symbol": stock_code})

    # 2. 工具失败则直接中止
    if "[TOOL_ERROR]" in financial_result:
        return _abort("财务指标工具返回错误或关键财务数据不足。")

    if "[TOOL_ERROR]" in price_result:
        return _abort("行情核验工具返回错误，无法完成股票信息交叉核验。")

    # 3. 工具成功后，让 LLM 只负责总结，不再让它自己调工具
    prompt = f"""{SYSTEM_PROMPT}

以下是工具已返回结果，请严格基于这些内容输出最终报告：

## 股票代码
{stock_code}

## 工具结果一：财务指标
{financial_result}

## 工具结果二：行情核验
{price_result}
"""

    response = deep_llm.invoke([HumanMessage(content=prompt)])
    final_text = response.content

    return _post_check_fundamental_output(final_text, stock_code)