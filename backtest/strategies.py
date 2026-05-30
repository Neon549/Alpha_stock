#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@author: yulin
@created: 2026/5/29 21:12
@updated: 2026/5/29 21:12
@version: 1.0
@description:
"""

import backtrader as bt
import backtrader.indicators as btind


class KDJOversoldStrategy(bt.Strategy):
    """
    KDJ超卖买入 + 死叉卖出策略

    买入: K<20 且 D<20 且 J<10 (三线同处超卖区)
    卖出: KDJ死叉 (K下穿D) 或 止损-8%
    仓位: 95%满仓
    """

    params = dict(
        kdj_period=9,
        kdj_signal=3,
        k_threshold=25,
        d_threshold=30,
        j_threshold=15,
        stop_loss=0.08,
        printlog=True,
    )

    def __init__(self):
        self.stoch = btind.Stochastic(
            self.data,
            period=self.p.kdj_period,
            period_dfast=self.p.kdj_signal,
            period_dslow=self.p.kdj_signal,
        )
        self.k_line = self.stoch.percK
        self.d_line = self.stoch.percD
        self.j_line = self.k_line * 3 - self.d_line * 2
        self.kdj_cross = btind.CrossOver(self.k_line, self.d_line)

        # 新增MA60
        self.ma60 = btind.SMA(self.data.close, period=60)

        self.order = None
        self.buy_price = None

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"[{dt}] [KDJ超卖] {txt}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_price = order.executed.price
                self.log(f"买入成交 | ¥{order.executed.price:.2f}")
            else:
                gain = (order.executed.price - self.buy_price) / self.buy_price * 100
                self.log(f"卖出成交 | ¥{order.executed.price:.2f} | 盈亏:{gain:+.1f}%")
                self.buy_price = None
        self.order = None

    def next(self):
        if self.order:
            return

        if not self.position:
            k_oversold = self.k_line[0] < self.p.k_threshold
            d_oversold = self.d_line[0] < self.p.d_threshold
            j_oversold = self.j_line[0] < self.p.j_threshold
            above_ma60 = self.data.close[0] > self.ma60[0]
            ma60_rising = self.ma60[0] > self.ma60[-10]

            if k_oversold and d_oversold and j_oversold and above_ma60 and ma60_rising:
                self.log(
                    f"买入信号 | K={self.k_line[0]:.1f} "
                    f"D={self.d_line[0]:.1f} J={self.j_line[0]:.1f}"
                )
                self.order = self.buy()
        else:
            current_price = self.data.close[0]

            # 死叉卖出
            death_cross = self.kdj_cross[0] < 0

            # 止损
            stop_loss = (
                self.buy_price is not None
                and (current_price - self.buy_price) / self.buy_price
                <= -self.p.stop_loss
            )

            if death_cross:
                self.log(f"死叉卖出 | K={self.k_line[0]:.1f} D={self.d_line[0]:.1f}")
                self.order = self.sell()
            elif stop_loss:
                loss = (current_price - self.buy_price) / self.buy_price * 100
                self.log(f"止损卖出 | 跌幅={loss:.1f}%")
                self.order = self.sell()


class JExtremeStrategy(bt.Strategy):
    """
    J线极值策略（用户自定义策略）

    买入条件（同时满足）:
      1. J线 < 10（极度超卖）
      2. K线 < 20
      3. D线 < 40
      4. 当前K线为阳线（close > open）
      5. 成交量放大（> 前日1.2倍）
      6. KDJ金叉（K上穿D）

    卖出条件（满足任一）:
      1. J线 > 85
      2. 持仓涨幅 > 15%
      3. 持仓跌幅 > 8%（止损）
    """

    params = dict(
        kdj_period=9,
        kdj_signal=3,
        j_buy_threshold=15,  # J线买入阈值
        k_buy_threshold=25,  # K线买入阈值
        d_buy_threshold=30,  # D线买入阈值
        j_sell_threshold=85,  # J线卖出阈值
        profit_target=0.15,  # 止盈比例 15%
        stop_loss=0.06,  # 止损比例 6%
        volume_ratio=1.05,  # 放量倍数
        printlog=True,
    )

    def __init__(self):
        # KDJ
        self.stoch = btind.Stochastic(
            self.data,
            period=self.p.kdj_period,
            period_dfast=self.p.kdj_signal,
            period_dslow=self.p.kdj_signal,
        )
        self.k_line = self.stoch.percK
        self.d_line = self.stoch.percD
        # J线 = 3K - 2D
        self.j_line = self.k_line * 3 - self.d_line * 2

        # KDJ金叉
        self.kdj_cross = btind.CrossOver(self.k_line, self.d_line)

        self.order = None
        self.buy_price = None  # 记录买入价格，用于止盈止损计算
        self.ma60 = btind.SMA(self.data.close, period=60)

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"[{dt}] [J极值策略] {txt}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_price = order.executed.price
                self.log(f"买入成交 | ¥{order.executed.price:.2f}")
            else:
                gain = (order.executed.price - self.buy_price) / self.buy_price * 100
                self.log(f"卖出成交 | ¥{order.executed.price:.2f} | 盈亏:{gain:+.1f}%")
                self.buy_price = None
        self.order = None

    def next(self):
        if self.order:
            return

        if not self.position:
            j_ok = self.j_line[0] < self.p.j_buy_threshold
            k_ok = self.k_line[0] < self.p.k_buy_threshold
            d_ok = self.d_line[0] < self.p.d_buy_threshold
            yang = self.data.close[0] > self.data.open[0]
            volume_surge = (
                self.data.volume[0] > self.data.volume[-1] * self.p.volume_ratio
            )

            # 新增：强势股过滤
            above_ma60 = self.data.close[0] > self.ma60[0]
            ma60_rising = self.ma60[0] > self.ma60[-10]

            if (
                j_ok
                and k_ok
                and d_ok
                and yang
                and volume_surge
                and above_ma60
                and ma60_rising
            ):
                self.log(
                    f"买入信号 | J={self.j_line[0]:.1f} K={self.k_line[0]:.1f} "
                    f"D={self.d_line[0]:.1f} | MA60={self.ma60[0]:.2f}"
                )
                self.order = self.buy()

        else:
            # ── 卖出条件 ──────────────────────────
            current_price = self.data.close[0]

            j_overbought = self.j_line[0] > self.p.j_sell_threshold  # J > 85
            take_profit = (
                current_price - self.buy_price
            ) / self.buy_price >= self.p.profit_target  # 涨15%
            stop_loss = (
                current_price - self.buy_price
            ) / self.buy_price <= -self.p.stop_loss  # 跌8%

            if j_overbought:
                self.log(f"J线卖出 | J={self.j_line[0]:.1f}")
                self.order = self.sell()
            elif take_profit:
                gain = (current_price - self.buy_price) / self.buy_price * 100
                self.log(f"止盈卖出 | 涨幅={gain:.1f}%")
                self.order = self.sell()
            elif stop_loss:
                loss = (current_price - self.buy_price) / self.buy_price * 100
                self.log(f"止损卖出 | 跌幅={loss:.1f}%")
                self.order = self.sell()


class KDJMACDStrategy(bt.Strategy):
    params = dict(
        kdj_period=9,
        kdj_signal=3,
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        printlog=False,
    )

    def __init__(self):
        self.stoch = btind.Stochastic(
            self.data,
            period=self.p.kdj_period,
            period_dfast=self.p.kdj_signal,
            period_dslow=self.p.kdj_signal,
        )
        self.k_line = self.stoch.percK
        self.d_line = self.stoch.percD
        self.kdj_cross = btind.CrossOver(self.k_line, self.d_line)

        self.macd = btind.MACD(
            self.data.close,
            period_me1=self.p.macd_fast,
            period_me2=self.p.macd_slow,
            period_signal=self.p.macd_signal,
        )
        self.macd_hist = self.macd.macd - self.macd.signal
        self.order = None

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"[{dt}] {txt}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            action = "买入" if order.isbuy() else "卖出"
            self.log(f"{action}成交 | ¥{order.executed.price:.2f}")
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if (
                self.kdj_cross[0] > 0
                and self.macd_hist[0] > 0
                and self.macd_hist[-1] <= 0
            ):
                self.order = self.buy()
        else:
            if self.kdj_cross[0] < 0 or (
                self.macd_hist[0] < 0 and self.macd_hist[-1] >= 0
            ):
                self.order = self.sell()


class RSIStrategy(bt.Strategy):
    params = dict(
        rsi_period=21,
        rsi_low=30,
        rsi_high=70,
        printlog=False,
    )

    def __init__(self):
        self.rsi = btind.RSI(self.data.close, period=self.p.rsi_period)
        self.order = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            action = "买入" if order.isbuy() else "卖出"
            print(f"[RSI] {action}成交 | ¥{order.executed.price:.2f}")
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.rsi[0] < self.p.rsi_low:
                self.order = self.buy()
        else:
            if self.rsi[0] > self.p.rsi_high:
                self.order = self.sell()


class BOLLStrategy(bt.Strategy):
    params = dict(
        boll_period=20,
        boll_dev=2.0,
        printlog=False,
    )

    def __init__(self):
        self.boll = btind.BollingerBands(
            self.data.close,
            period=self.p.boll_period,
            devfactor=self.p.boll_dev,
        )
        self.cross_lower = btind.CrossOver(self.data.close, self.boll.bot)
        self.cross_upper = btind.CrossOver(self.data.close, self.boll.top)
        self.order = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            action = "买入" if order.isbuy() else "卖出"
            print(f"[BOLL] {action}成交 | ¥{order.executed.price:.2f}")
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.cross_lower[0] > 0:
                self.order = self.buy()
        else:
            if self.cross_upper[0] < 0:
                self.order = self.sell()


STRATEGY_MAP = {
    "kdj_macd": KDJMACDStrategy,
    "rsi": RSIStrategy,
    "boll": BOLLStrategy,
    "j_extreme": JExtremeStrategy,  # 新增
    "kdj_oversold": KDJOversoldStrategy,
}
