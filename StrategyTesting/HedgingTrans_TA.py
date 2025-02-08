# encoding: UTF-8

from typing import Dict, List

from ctaTemplate import CtaTemplate
from vtObject import KLineData, TickData

class HedgingTrans_TA(CtaTemplate):
    def __init__(self):
        super().__init__()
        self.vtSymbol = "TA505"
        self.exchange = "CZCE"
        self.B_net_pos_threshold = 6
        self.B_S_close_threshold = 3
        self.tran_auth = True
        self.one_hop = 2

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

        B_pos_num = self.get_position(self.vtSymbol).long.position
        S_pos_num = self.get_position(self.vtSymbol).short.position

        # 多单持仓量小于阈值，建仓多单
        if (self.get_position(self.vtSymbol).long.position 
            - self.get_position(self.vtSymbol).short.position) < self.B_net_pos_threshold:
            if self.tran_auth:
                self.tran_auth = False
                self.buy_open_position(tick.lastPrice + self.one_hop)
                self.output("对冲策略多单持仓量小于规定阈值，建仓多单")


        # 多空持仓量大于平仓阈值，双向平仓
        if (self.get_position(self.vtSymbol).long.position > self.B_S_close_threshold and 
            self.get_position(self.vtSymbol).short.position > self.B_S_close_threshold) :
                if self.tran_auth:
                    self.tran_auth = False
                    self.sell_close_position(tick.lastPrice - self.one_hop)
                    self.buy_close_position(tick.lastPrice + self.one_hop)
                    self.output("对冲策略多空持仓超过阈值，双向同时平仓")

    def onTrade(self, trade, log=True):
        """成交回调"""
        if trade.direction == "多" and trade.offset == "开仓":
            self.output("对冲买入开仓", trade.price)
            self.tran_auth = True

        if trade.direction == "空" and trade.offset == "平仓":
            self.output("对冲卖出平仓", trade.price)
            self.tran_auth = True
            
        if trade.direction == "空" and trade.offset == "开仓":
            self.output("对冲卖出开仓", trade.price)
            self.tran_auth = True

        if trade.direction == "多" and trade.offset == "平仓":
            self.output("对冲买入平仓", trade.price)
            self.tran_auth = True

        super().onTrade(trade, log)
        self.output("--------" * 8)


    def onStart(self):
        self.output("onStart")
        super().onStart()

    def onStop(self):
        self.output("onStop")
        super().onStop()
