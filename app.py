import streamlit as st
import requests
import time
import pandas as pd
import sys
import os
import plotly.graph_objects as go
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=True)

API_BASE = "http://localhost:8000/api/v1"


st.set_page_config(
    page_title="A股量化分析系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ─────────────────────────────────────
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+SC:wght@300;400;500;700&display=swap');

.main-title {
    font-family: 'Inter', sans-serif;
    color: #1a1a1a;
    font-size: 26px;
    font-weight: 700;
}
.sub-title {
    font-family: 'Inter', sans-serif;
    color: #6b7280;
    font-size: 13px;
}
.section-title {
    font-family: 'Inter', sans-serif;
    color: #111827;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    border-left: 3px solid #f97316;
    padding-left: 10px;
    margin: 20px 0 12px;
}
.metric-card {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 14px;
    text-align: center;
}
.metric-label {
    color: #6b7280;
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-family: 'Inter', sans-serif;
}
</style>
""",
    unsafe_allow_html=True,
)

# ── Session State ────────────────────────────
for key, default in {
    "selected_code": "300236",
    "analysis_result": None,
    "backtest_result": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ── Header ───────────────────────────────────
st.markdown('<div class="main-title">📈 A股量化分析系统</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">LangGraph Multi-Agent + 量化回测 + RAG</div>',
    unsafe_allow_html=True,
)
st.markdown("---")

# ── 侧边栏 ───────────────────────────────────
with st.sidebar:
    st.markdown("### 🛠 系统设置")

    mode = st.radio(
        "功能模式",
        [
            "🤖 AI智能分析",
            "📊 量化回测",
            "🔍 板块筛选",
            "🎯 今日买点",  # 新增
        ],
    )

    st.markdown("---")

    # 后端状态
    try:
        r = requests.get(f"{API_BASE}/health", timeout=2)
        if r.status_code == 200:
            st.success("✅ 后端在线")
        else:
            st.error("❌ 后端异常")
    except:
        st.error("❌ 后端未启动")
        st.caption("请先运行: python main.py")

    st.markdown("---")

    # 板块选股
    st.markdown("**板块选股**")

    sectors_resp = None
    for _ in range(3):
        try:
            sectors_resp = requests.get(f"{API_BASE}/backtest/sectors", timeout=15)
            if sectors_resp.status_code == 200:
                break
        except:
            time.sleep(2)

    if sectors_resp and sectors_resp.status_code == 200:
        try:
            sectors_data = sectors_resp.json().get("sectors", {})
            sector_names = list(sectors_data.keys())
            selected_sector = st.selectbox(
                "一级板块",
                sector_names,
                label_visibility="collapsed",
                key="sidebar_sector",
            )
            sector_stocks = sectors_data.get(selected_sector, [])
            stock_options = {
                f"{s['name']} {s['code']}": s["code"] for s in sector_stocks
            }
            selected_stock_label = st.selectbox(
                "选择股票",
                ["自定义"] + list(stock_options.keys()),
                label_visibility="collapsed",
                key="sidebar_stock",
            )
            if selected_stock_label != "自定义":
                preview_code = stock_options[selected_stock_label]
                if st.session_state.selected_code != preview_code:
                    st.session_state.selected_code = preview_code
                    st.rerun()
        except Exception as e:
            st.warning(f"板块数据解析失败: {e}")
    else:
        st.warning("板块数据获取失败")

# ══════════════════════════════════════════════
# 模式1：AI智能分析
# ══════════════════════════════════════════════
if mode == "🤖 AI智能分析":
    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown('<div class="section-title">分析设置</div>', unsafe_allow_html=True)

        stock_code = st.session_state.selected_code
        st.text_input("股票代码", value=stock_code, disabled=True)
        st.session_state.selected_code = stock_code

        analyze_btn = st.button(
            "🚀 开始AI分析", type="primary", use_container_width=True
        )
        history_btn = st.button("📋 历史决策", use_container_width=True)

    with col2:
        if analyze_btn and stock_code:
            st.session_state.analysis_result = None
            steps = [
                ("📊 基本面分析师", "读取财务数据..."),
                ("📈 技术面分析师", "分析K线走势..."),
                ("📰 情绪分析师", "检索新闻资讯..."),
                ("🔬 研究员", "多空辩论中..."),
                ("💼 交易员", "生成交易决策..."),
            ]
            progress_bar = st.progress(0)
            status = st.empty()

            for i, (agent, action) in enumerate(steps):
                status.markdown(f"**{agent}** — {action}")
                progress_bar.progress((i + 1) / len(steps) * 0.8)
                time.sleep(0.4)

            status.markdown("**⏳ AI分析中...**")
            try:
                resp = requests.post(
                    f"{API_BASE}/analyze",
                    json={"stock_code": stock_code},
                    timeout=300,
                )
                if resp.status_code == 200:
                    st.session_state.analysis_result = resp.json()
                    progress_bar.progress(1.0)
                    status.markdown("**✅ 分析完成！**")
                else:
                    st.error(f"失败: {resp.json().get('detail', '未知错误')}")
            except Exception as e:
                st.error(f"请求失败: {e}")

        if st.session_state.analysis_result:
            result = st.session_state.analysis_result
            decision = result.get("decision", "")
            icon = "🟢" if "买入" in decision else "🔴" if "卖出" in decision else "🟡"
            st.subheader(f"{icon} {result['stock_code']} 分析结果")

            tab1, tab2, tab3, tab4, tab5 = st.tabs(
                ["💼 最终决策", "📊 基本面", "📈 技术面", "📰 情绪", "🔬 辩论"]
            )
            with tab1:
                st.markdown(decision)
            with tab2:
                st.markdown(result.get("fundamental_report", "暂无"))
            with tab3:
                st.markdown(result.get("technical_report", "暂无"))
            with tab4:
                st.markdown(result.get("sentiment_report", "暂无"))
            with tab5:
                st.markdown(result.get("researcher_analysis", "暂无"))

        if history_btn and stock_code:
            try:
                r = requests.get(f"{API_BASE}/history/{stock_code}", timeout=10)
                if r.status_code == 200:
                    st.markdown(r.json().get("history", ""))
            except Exception as e:
                st.error(f"获取失败: {e}")

        if not st.session_state.analysis_result:
            st.info("👈 输入股票代码，点击「开始AI分析」")


# ══════════════════════════════════════════════
# 模式2：量化回测
# ══════════════════════════════════════════════
elif mode == "📊 量化回测":
    st.markdown('<div class="section-title">量化回测设置</div>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        stock_code = st.session_state.selected_code
        st.text_input("股票代码", value=stock_code, disabled=True)
        st.session_state.selected_code = stock_code
    with col2:
        strategy = st.selectbox(
            "策略",
            ["kdj_oversold", "kdj_cross", "j_extreme", "rsi", "boll", "kdj_macd"],
            format_func=lambda x: {
                "kdj_oversold": "KDJ超卖",
                "kdj_cross": "KDJ金叉",
                "j_extreme": "J极值",
                "rsi": "RSI",
                "boll": "布林带",
                "kdj_macd": "KDJ+MACD",
            }[x],
        )
    with col3:
        start_date = st.text_input("开始日期", value="20240901")
    with col4:
        end_date = st.text_input("结束日期", value="20260530")

    bt_btn = st.button("🚀 开始回测", type="primary", use_container_width=True)

    if bt_btn and stock_code:
        with st.spinner(f"正在回测 {stock_code}..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/backtest",
                    json={
                        "stock_code": stock_code,
                        "strategy": strategy,
                        "start_date": start_date,
                        "end_date": end_date,
                        "initial_cash": 100000,
                    },
                    timeout=120,
                )
                if resp.status_code == 200:
                    st.session_state.backtest_result = resp.json()
                else:
                    st.error(f"回测失败: {resp.json().get('detail', '未知错误')}")
            except Exception as e:
                st.error(f"请求失败: {e}")

    if st.session_state.backtest_result:
        bt = st.session_state.backtest_result
        st.markdown(
            f'<div class="section-title">{bt["stock_code"]} — {bt["strategy"].upper()} 回测结果</div>',
            unsafe_allow_html=True,
        )

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("总收益率", f"{bt['total_return']:+.2f}%")
        c2.metric("夏普比率", str(bt["sharpe"]))
        c3.metric("最大回撤", f"-{bt['max_drawdown']:.2f}%")
        c4.metric("交易次数", str(bt["trade_count"]))
        c5.metric("胜率", f"{bt['win_rate']}%")

        st.markdown("---")

        # 收益曲线
        if bt.get("returns_data") and bt.get("dates_data"):
            returns = pd.Series(bt["returns_data"], index=bt["dates_data"])
            cumulative = ((1 + returns).cumprod() - 1) * 100

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=cumulative.index,
                    y=cumulative.values,
                    mode="lines",
                    name="策略收益",
                    line=dict(color="#f97316", width=2),
                    fill="tozeroy",
                    fillcolor="rgba(249, 115, 22, 0.08)",
                )
            )
            fig.add_hline(y=0, line_dash="dash", line_color="#9ca3af", line_width=1)
            fig.update_layout(
                title="累计收益曲线",
                paper_bgcolor="white",
                plot_bgcolor="white",
                font=dict(family="Inter", color="#374151"),
                xaxis=dict(gridcolor="#f3f4f6", title=""),
                yaxis=dict(gridcolor="#f3f4f6", ticksuffix="%", title="累计收益"),
                height=320,
                margin=dict(l=40, r=20, t=40, b=40),
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)

        # 交易明细
        if bt.get("trade_records"):
            st.markdown("#### 📋 交易明细")
            records = bt["trade_records"]
            df_trades = pd.DataFrame(records)
            buys = df_trades[df_trades["type"] == "买入"].reset_index(drop=True)
            sells = df_trades[df_trades["type"] == "卖出"].reset_index(drop=True)

            pairs = []
            for i in range(min(len(buys), len(sells))):
                buy_price = buys.iloc[i]["price"]
                sell_price = sells.iloc[i]["price"]
                pnl = (sell_price - buy_price) / buy_price * 100
                pairs.append(
                    {
                        "笔数": f"第{i+1}笔",
                        "买入日期": buys.iloc[i]["date"],
                        "买入价格": f"¥{buy_price}",
                        "卖出日期": sells.iloc[i]["date"],
                        "卖出价格": f"¥{sell_price}",
                        "盈亏": f"{pnl:+.2f}%",
                        "结果": "✅ 盈利" if pnl > 0 else "❌ 亏损",
                    }
                )

            if pairs:
                st.dataframe(
                    pd.DataFrame(pairs), use_container_width=True, hide_index=True
                )

            if len(buys) > len(sells):
                last_buy = buys.iloc[-1]
                st.info(
                    f"📌 当前持仓：{last_buy['date']} 买入 ¥{last_buy['price']}，尚未卖出"
                )

        st.markdown("---")
        st.markdown(bt["report_text"])

        # quantstats完整报告
        report_path = bt.get("report_path")
        if report_path and os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            with st.expander("📄 查看完整quantstats报告"):
                st.components.v1.html(html_content, height=600, scrolling=True)

        # 历史回测记录
        with st.expander("📋 历史回测记录"):
            try:
                r = requests.get(
                    f"{API_BASE}/backtest/history/{stock_code}", timeout=10
                )
                if r.status_code == 200:
                    st.text(r.json().get("history", ""))
            except:
                st.warning("获取历史失败")


# ══════════════════════════════════════════════
# 模式3：板块筛选
# ══════════════════════════════════════════════
elif mode == "🔍 板块筛选":
    st.markdown(
        '<div class="section-title">板块基本面筛选</div>', unsafe_allow_html=True
    )

    try:
        sectors_resp = requests.get(f"{API_BASE}/backtest/sectors", timeout=5)
        sectors_data = sectors_resp.json().get("sectors", {})
        sector_names = list(sectors_data.keys())
    except:
        sectors_data = {}
        sector_names = []

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        sector = st.selectbox("选择板块", sector_names)
    with col2:
        min_score = st.slider("最低评分", 50, 90, 65)
    with col3:
        top_n = st.slider("显示数量", 3, 10, 5)

    filter_btn = st.button("🔍 开始筛选", type="primary", use_container_width=True)

    if filter_btn and sector:
        with st.spinner("筛选中..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/backtest/filter",
                    json={"sector": sector, "min_score": min_score, "top_n": top_n},
                    timeout=120,
                )
                results = (
                    resp.json().get("results", []) if resp.status_code == 200 else []
                )
            except Exception as e:
                results = []
                st.error(f"请求失败: {e}")

        if results:
            df_show = pd.DataFrame(
                [
                    {
                        "代码": r["code"],
                        "名称": r["name"],
                        "评分": r["score"],
                        "PE": f"{r['pe']:.1f}" if r.get("pe") else "N/A",
                        "ROE": f"{r['roe']:.1f}%" if r.get("roe") else "N/A",
                        "毛利率": (
                            f"{r['gross_margin']:.1f}%"
                            if r.get("gross_margin")
                            else "N/A"
                        ),
                    }
                    for r in results
                ]
            )
            st.dataframe(
                df_show,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "评分": st.column_config.ProgressColumn(
                        "评分", min_value=0, max_value=100
                    )
                },
            )
            cols = st.columns(min(len(results), 5))
            for i, (col, r) in enumerate(zip(cols, results)):
                if col.button(f"{r['name']}\n{r['code']}", key=f"pick_{i}"):
                    st.session_state.selected_code = r["code"]
                    st.rerun()
        else:
            st.warning("没有股票通过筛选")

# ══════════════════════════════════════════════
# 模式4: 今日买点
# ══════════════════════════════════════════════
elif mode == "🎯 今日买点":
    st.markdown('<div class="section-title">今日买点扫描</div>', unsafe_allow_html=True)
    st.caption("扫描股票池中满足KDJ超卖条件的股票，并用4个Agent验证")

    col1, col2 = st.columns(2)
    with col1:
        base_start = st.text_input(
            "数据起始日期",
            value="20230101",
            help="首次扫描会从此日期拉取全量数据并缓存，之后每次只增量更新",
        )
    with col2:
        top_n = st.slider("最多显示", 5, 20, 10)

    st.info("💡 首次扫描较慢（需拉取历史数据），之后每次只更新最新数据，速度大幅提升")

    scan_btn = st.button(
        "🎯 开始扫描今日买点", type="primary", use_container_width=True
    )

    if scan_btn:
        with st.spinner("扫描中，首次约需5分钟，之后约30秒..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/scan/today",
                    json={"base_start": base_start, "top_n": top_n},
                    timeout=600,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    recs = data.get("recommendations", [])

                    st.success(
                        f"✅ 扫描完成 | 候选股{data['total_candidates']}只 | 推荐{data['count']}只"
                    )

                    if recs:
                        st.markdown("### 今日推荐买入")
                        for r in recs:
                            icon = "🟢" if r["confidence"] == "高" else "🟡"
                            with st.expander(
                                f"{icon} {r['name']}({r['code']}) — {r['decision']} | 置信度:{r['confidence']} | J={r['j']}"
                            ):
                                st.markdown(f"**当前价**: ¥{r['close']}")
                                st.markdown(r["report"])
                    else:
                        st.warning("今日无满足条件的买入机会，继续观望")
            except Exception as e:
                st.error(f"扫描失败: {e}")
