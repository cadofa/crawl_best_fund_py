# encoding: UTF-8

import numpy as np
from typing import Dict, List

from ctaTemplate import CtaTemplate
from vtObject import KLineData, TickData

class TrendFollow_MA(CtaTemplate):
    def __init__(self):
        super().__init__()
        self.vtSymbol = "MA2409"
        self.exchange = "CZCE"
        self.position_list = {}
        self.stop_loss_value = 2
        self.stop_profit_value = 8


    def buy_open_position(self, price):
        self.orderID = self.buy(
            price=price,
            volume=1,
            symbol=self.vtSymbol,
            exchange=self.exchange,
        )

    def sell_close_position(self, price):
        self.auto_close_position(
            price=price,
            volume=1,
            symbol=self.vtSymbol,
            exchange=self.exchange,
            order_direction="sell"
        )

    def sell_open_position(self, price):
        self.orderID = self.short(
            price=price,
            volume=1,
            symbol=self.vtSymbol,
            exchange=self.exchange,
        )

    def buy_close_position(self, price):
        self.auto_close_position(
            price=price,
            volume=1,
            symbol=self.vtSymbol,
            exchange=self.exchange,
            order_direction="buy"
        )

    def onTick(self, tick: TickData) -> None:
        """收到行情 tick 推送"""
        super().onTick(tick)

        if not self.position_list:
            self.output("初始化建仓")
            self.position_list.update({"B": tick.lastPrice + 1})
            self.buy_open_position(tick.lastPrice + 1)
            self.position_list.update({"S": tick.lastPrice - 1})
            self.sell_open_position(tick.lastPrice - 1)

        #止盈
        if self.position_list:
            for k, v in list(self.position_list.items()):
                if k == "B" and (tick.lastPrice - v) >= self.stop_profit_value:
                    self.position_list.pop("B")
                    self.output("止盈多单")
                    self.sell_close_position(tick.lastPrice - 1)
                if k == "S" and (v - tick.lastPrice) >= self.stop_profit_value:
                    self.position_list.pop("S")
                    self.output("止盈空单")
                    self.buy_close_position(tick.lastPrice + 1)

        if len(self.position_list) == 1:
            for k, v in list(self.position_list.items()):
                if k == "B" and (v - tick.lastPrice) <= self.stop_loss_value:
                    self.position_list.pop("B")
                    self.output("止损多单")
                    self.sell_close_position(tick.lastPrice - 1)
                if k == "S" and (tick.lastPrice - v) <= self.stop_loss_value:
                    self.position_list.pop("S")
                    self.output("止损空单")
                    self.buy_close_position(tick.lastPrice + 1)
    

    def onTrade(self, trade, log=True):
        """成交回调"""
        if trade.offset == "开仓":
            if trade.direction == "多":
                self.position_list["B"] = trade.price
            if trade.direction == "空":
                self.position_list["S"] = trade.price
            self.output("当前操作", trade.direction, trade.offset, trade.price)
            self.output("开仓/持仓详情", self.position_list)

        if trade.offset == "平仓":
            self.output("当前操作", trade.direction, trade.offset, trade.price)
            self.output("平仓/持仓详情", self.position_list)

        super().onTrade(trade, log)
        self.output("--------" * 8)

    def onStart(self):
        self.output("onStart")
        super().onStart()

    def onStop(self):
        self.output("onStop")
        super().onStop()
