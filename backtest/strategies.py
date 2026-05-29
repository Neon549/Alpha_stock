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
            if self.kdj_cross[0] > 0 and self.macd_hist[0] > 0 and self.macd_hist[-1] <= 0:
                self.order = self.buy()
        else:
            if self.kdj_cross[0] < 0 or (self.macd_hist[0] < 0 and self.macd_hist[-1] >= 0):
                self.order = self.sell()


class RSIStrategy(bt.Strategy):
    params = dict(
        rsi_period=14,
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
    "rsi":      RSIStrategy,
    "boll":     BOLLStrategy,
}