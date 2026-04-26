from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

from graph.state import TradingState
from agents.fundamental_analyst import run_fundamental_analysis
from agents.technical_analyst import run_technical_analysis
from agents.sentiment_analyst import run_sentiment_analysis
from config.llm_config import deep_llm
from memory.long_term import LongTermMemory

import concurrent.futures
import re

memory = LongTermMemory()

ERROR_MARKERS = [
    "[TOOL_ERROR]",
    "[ANALYSIS_ABORT]",
    "数据不足，禁止基于假设继续分析",
    "数据不足，无法分析",
    "未找到股票代码",
    "获取股价失败",
    "获取财务指标失败",
    "获取历史数据失败",
    "检索失败",
    "NaN",
]

COMPANY_NAME_PATTERN = re.compile(r"股票名称[:：]\s*([^\n]+)")


def _contains_error(text: str | None) -> bool:
    if not text:
        return True
    return any(marker in text for marker in ERROR_MARKERS)


def _extract_company_names(*texts: str) -> set[str]:
    names = set()
    for text in texts:
        if not text:
            continue
        matches = COMPANY_NAME_PATTERN.findall(text)
        for m in matches:
            name = m.strip()
            if name and name != "名称未验证":
                names.add(name)
    return names


def analysts_node(state: TradingState) -> dict:
    """
    并行执行三个分析师
    """
    stock_code = state["stock_code"]
    print(f"\n🚀 三个分析师并行启动：{stock_code}")

    def run_fundamental():
        print("📊 [基本面分析师] 开始...")
        result = run_fundamental_analysis(stock_code)
        print("✅ 基本面分析完成")
        return result

    def run_technical():
        print("📈 [技术面分析师] 开始...")
        result = run_technical_analysis(stock_code)
        print("✅ 技术面分析完成")
        return result

    def run_sentiment():
        print("📰 [情绪分析师] 开始...")
        result = run_sentiment_analysis(stock_code)
        print("✅ 情绪分析完成")
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_fundamental = executor.submit(run_fundamental)
        future_technical = executor.submit(run_technical)
        future_sentiment = executor.submit(run_sentiment)

        fundamental_report = future_fundamental.result()
        technical_report = future_technical.result()
        sentiment_report = future_sentiment.result()

    print("\n✅ 三个分析师全部完成，进入校验节点")

    return {
        "fundamental_report": fundamental_report,
        "technical_report": technical_report,
        "sentiment_report": sentiment_report,
    }


def validation_node(state: TradingState) -> dict:
    """
    校验三个分析结果是否可继续进入研究员 / 交易员环节
    """
    print("\n🛡️ [校验节点] 检查分析结果可靠性...")

    fundamental_report = state.get("fundamental_report", "")
    technical_report = state.get("technical_report", "")
    sentiment_report = state.get("sentiment_report", "")

    errors = []

    if _contains_error(fundamental_report):
        errors.append("基本面分析存在工具错误或数据不足")
    if _contains_error(technical_report):
        errors.append("技术面分析存在工具错误或数据不足")
    if _contains_error(sentiment_report):
        errors.append("情绪分析存在工具错误或数据不足")

    # company_names = _extract_company_names(
    #     fundamental_report,
    #     technical_report,
    #     sentiment_report,
    # )
    # if len(company_names) > 1:
    #     errors.append(f"检测到公司名称不一致：{', '.join(sorted(company_names))}")

    if errors:
        print("❌ 校验失败，系统将中止后续决策")
        return {
            "risk_assessment": "\n".join(errors),
            "final_decision": (
                "### 交易决策\n"
                "决策：数据不足，停止分析\n"
                "原因：检测到工具错误、关键数据缺失或公司名称不一致。\n"
                "要求：禁止基于当前结果生成买入价、目标价、止损价和仓位建议。"
            ),
        }

    print("✅ 校验通过，进入研究员节点")
    return {
        "risk_assessment": "校验通过"
    }


def should_continue_after_validation(state: TradingState) -> str:
    """
    条件路由：
    - 如果 final_decision 已经被 validation_node 写入，说明要中止
    - 否则继续 researcher
    """
    if state.get("final_decision"):
        return "abort"
    return "researcher"


def abort_node(state: TradingState) -> dict:
    """
    中止节点：直接结束，不再进入 researcher / trader
    """
    print("\n⛔ [中止节点] 已拦截不可靠分析，终止流程")
    return {
        "bull_argument": "已中止：上游分析结果不可靠",
        "bear_argument": state.get("risk_assessment", "检测到数据问题"),
    }


def researcher_node(state: TradingState) -> dict:
    """
    研究员节点：综合三份报告，进行多空辩论
    """
    print(f"\n🔬 [研究员] 综合分析，进行多空辩论...")

    prompt = f"""你是一位资深A股研究员，需要基于以下三份分析报告进行多空辩论。

重要要求：
1. 只能基于下述报告中的已验证内容分析
2. 禁止补充未出现的数据
3. 若报告中存在明显数据不足，应偏向保守结论

## 基本面分析报告
{state['fundamental_report']}

## 技术面分析报告
{state['technical_report']}

## 情绪分析报告
{state['sentiment_report']}

请分别给出：
### 多方观点（看涨理由）
[从三份报告中提炼支持买入的核心论据，3-5条]

### 空方观点（看跌理由）
[从三份报告中提炼支持卖出/观望的核心论据，3-5条]

### 综合倾向
[多方占优/空方占优/势均力敌] - [简要理由]
"""

    response = deep_llm.invoke([HumanMessage(content=prompt)])
    result = response.content
    print("✅ 多空辩论完成")

    return {
        "bull_argument": result,
        "bear_argument": result,
        "debate_rounds": state.get("debate_rounds", 0) + 1,
    }


def trader_node(state: TradingState) -> dict:
    """
    交易员节点：做出最终决策
    """
    print(f"\n💼 [交易员] 综合所有信息，做出最终决策...")

    history = memory.get_history(state["stock_code"])

    prompt = f"""你是一位经验丰富的A股交易员，需要基于研究团队的分析做出最终交易决策。

重要要求：
1. 只能依据已提供内容决策
2. 禁止编造价格、仓位、目标价、止损价
3. 若证据不足，必须输出“持有观望”或“数据不足，停止分析”
4. 若上游分析存在明显保守结论，应维持保守策略

## 历史决策记录（避免重复犯错）
{history}

## 研究员综合分析
{state['bull_argument']}

## 决策要求
请给出明确的交易指令：

### 交易决策
决策：[强烈买入 / 买入 / 持有观望 / 减仓 / 卖出 / 数据不足，停止分析]
建议仓位：[如无法可靠判断则写“暂不设定”]
建议买入价位：[价格区间或条件；如无法可靠判断则写“暂不设定”]
目标价：[价格；如无法可靠判断则写“暂不设定”]
止损价：[价格；如无法可靠判断则写“暂不设定”]
持有周期：[短线1-2周 / 中线1-3月 / 暂不设定]

### 决策依据
[3条核心理由]

### 风险提示
[2-3条主要风险]
"""

    response = deep_llm.invoke([HumanMessage(content=prompt)])
    decision = response.content

    memory.save_decision(
        stock_code=state["stock_code"],
        decision=decision,
        fundamental_summary=(state.get("fundamental_report") or "")[:300],
        technical_summary=(state.get("technical_report") or "")[:300],
        sentiment_summary=(state.get("sentiment_report") or "")[:300],
    )

    print("✅ 交易决策完成并已存入记忆")
    return {"final_decision": decision}


def build_trading_graph():
    """
    工作流：
    analysts -> validation
    validation -> abort 或 researcher
    researcher -> trader
    trader -> END
    abort -> END
    """
    graph = StateGraph(TradingState)

    graph.add_node("analysts", analysts_node)
    graph.add_node("validation", validation_node)
    graph.add_node("abort", abort_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("trader", trader_node)

    graph.set_entry_point("analysts")

    graph.add_edge("analysts", "validation")
    graph.add_conditional_edges(
        "validation",
        should_continue_after_validation,
        {
            "abort": "abort",
            "researcher": "researcher",
        },
    )
    graph.add_edge("researcher", "trader")
    graph.add_edge("trader", END)
    graph.add_edge("abort", END)

    return graph.compile()


trading_graph = build_trading_graph()


def run_trading_analysis(stock_code: str) -> dict:
    initial_state = {
        "stock_code": stock_code,
        "fundamental_report": None,
        "technical_report": None,
        "sentiment_report": None,
        "bull_argument": None,
        "bear_argument": None,
        "debate_rounds": 0,
        "final_decision": None,
        "risk_assessment": None,
        "messages": [],
    }
    return trading_graph.invoke(initial_state)