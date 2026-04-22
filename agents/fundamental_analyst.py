# agents/fundamental_analyst.py

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from config.llm_config import deep_llm
from tools.akshare_tools import (
    get_stock_price,
    get_financial_indicator,
    get_stock_history,
)

SYSTEM_PROMPT = """你是一位专业的A股基本面分析师，专注于通过财务数据评估股票的内在价值。

你必须严格遵守以下规则：

【硬性规则】
1. 只能基于工具返回的真实内容分析，禁止补充、猜测、脑补任何未出现的数据。
2. 如果任一关键工具返回 [TOOL_ERROR]，或者出现“数据不足，禁止基于假设继续分析”，你必须立刻停止分析。
3. 若关键财务字段严重缺失，也必须停止分析。
4. 禁止编造：
   - 公司名称
   - 财务指标
   - 评级依据
   - 任何“稍后返回/队列中/等待数据”之类的接口状态
5. 你必须在最终输出的第一行明确写出以下两种之一：
   - [ANALYSIS_OK]
   - [ANALYSIS_ABORT]

【执行步骤】
1. 先调用 get_financial_indicator 获取财务指标
2. 再调用 get_stock_price 获取最新行情，用于交叉核对股票名称和价格
3. 必要时调用 get_stock_history 做基本趋势辅助判断，但基本面结论不得依赖纯技术信号

【输出要求】
- 如果可以分析，严格输出：

[ANALYSIS_OK]
## 基本面分析报告

### 1. 股票信息核验
股票代码：[代码]
股票名称：[仅可填写工具明确返回的名称；若未验证则写“名称未验证”]
数据可靠性：[高/中/低]
核验结论：[简述]

### 2. 估值分析
[只分析工具已返回的PE/PB/市值等，不得补全]

### 3. 盈利能力
[只分析工具已返回的ROE/营收增长率/毛利率等，不得补全]

### 4. 财务健康
[只分析工具已返回的负债率/现金流相关信息；若缺失必须明确指出]

### 5. 综合评级
评级：[强烈买入/买入/中性/卖出/强烈卖出]
理由：[基于已验证数据]
风险提示：[主要风险]

- 如果不能分析，严格输出：

[ANALYSIS_ABORT]
原因：[明确说明是哪一个工具失败，或哪些关键字段缺失]
结论：数据不足，无法分析。禁止基于假设给出评级或投资建议。
"""


FUNDAMENTAL_TOOLS = [
    get_stock_price,
    get_financial_indicator,
    get_stock_history,
]


def create_fundamental_analyst():
    return create_react_agent(
        model=deep_llm,
        tools=FUNDAMENTAL_TOOLS,
        prompt=SYSTEM_PROMPT,
    )


def _post_check_fundamental_output(text: str, stock_code: str) -> str:
    text = (text or "").strip()

    if not text:
        return (
            "[ANALYSIS_ABORT]\n"
            "原因：基本面分析师未返回任何内容。\n"
            "结论：数据不足，无法分析。禁止基于假设给出评级或投资建议。"
        )

    if "[TOOL_ERROR]" in text or "数据不足，禁止基于假设继续分析" in text:
        return (
            "[ANALYSIS_ABORT]\n"
            "原因：基本面分析过程中关键工具返回错误或数据不足。\n"
            "结论：数据不足，无法分析。禁止基于假设给出评级或投资建议。"
        )

    if text.startswith("[ANALYSIS_ABORT]"):
        return text

    if not text.startswith("[ANALYSIS_OK]"):
        # 如果模型没按格式输出，再做一次保守兜底
        return (
            "[ANALYSIS_ABORT]\n"
            "原因：基本面分析结果未遵循规定格式，可信度不足。\n"
            "结论：数据不足，无法分析。禁止基于假设给出评级或投资建议。"
        )

    # 基础一致性兜底：至少要提到股票代码
    if stock_code not in text:
        return (
            "[ANALYSIS_ABORT]\n"
            "原因：基本面分析结果未正确引用股票代码，存在一致性风险。\n"
            "结论：数据不足，无法分析。禁止基于假设给出评级或投资建议。"
        )

    return text


def run_fundamental_analysis(stock_code: str) -> str:
    agent = create_fundamental_analyst()

    result = agent.invoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        f"请对股票 {stock_code} 进行全面的基本面分析。"
                        f"如果财务指标缺失、名称无法核验、或任一关键工具报错，必须输出 [ANALYSIS_ABORT]。"
                    )
                )
            ]
        }
    )

    final_text = result["messages"][-1].content
    return _post_check_fundamental_output(final_text, stock_code)