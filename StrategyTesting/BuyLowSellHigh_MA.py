# encoding: UTF-8

import numpy as np
from typing import Dict, List

from ctaTemplate import CtaTemplate
from vtObject import KLineData, TickData

class BuyLowSellHigh_MA(CtaTemplate):
    def __init__(self):
        super().__init__()
        self.vtSymbol = "MA405"
        self.exchange = "CZCE"
        self.tick_data_list = []
        self.tick_mean = 0
        self.mean_deviation = 0
        #高卖间隔
        self.high_sell_devs = [3,5,8,13,21,34,55,89]
        #低买间隔
        self.low_buy_devs = [-3,-5,-8,-13,-21,-34,-55,-89]
        self.buy_position_list = {}
        self.sell_position_list = {}


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
        self.tick_data_list.append(tick.lastPrice)
        self.tick_mean = np.mean(self.tick_data_list)
        self.mean_deviation = int((tick.lastPrice - self.tick_mean)/self.tick_mean*1000)
        #开仓多单
        if self.mean_deviation in self.low_buy_devs:
            if self.mean_deviation not in self.buy_position_list.keys():
                self.buy_position_list.update({self.mean_deviation: tick.lastPrice + 1})
                self.buy_open_position(tick.lastPrice + 1)
        #开仓空单
        if self.mean_deviation in self.high_sell_devs:
            if self.mean_deviation not in self.sell_position_list.keys():
                self.sell_position_list.update({self.mean_deviation: tick.lastPrice - 1})

        if self.mean_deviation == 0:
            if self.buy_position_list:
                #平仓多单
                for k,v in self.buy_position_list.items():
                    self.sell_close_position(tick.lastPrice - 1)    
                self.buy_position_list.clear()

            if self.sell_position_list:
                #平仓空单
                for k,v in self.sell_position_list.items():
                    self.buy_close_position(tick.lastPrice + 1)
                self.sell_position_list.clear()
        

    def onTrade(self, trade, log=True):
        """成交回调"""
        super().onTrade(trade, log)

    def onStart(self):
        self.output("onStart")
        super().onStart()

    def onStop(self):
        self.output("onStop")
        super().onStop()
