# encoding: UTF-8

import os
import json
import time
import threading
from typing import Dict, List

from ctaTemplate import CtaTemplate
from vtObject import KLineData, TickData

class GrabBomTouchTop_SA(CtaTemplate):
    def __init__(self):
        super().__init__()
        self.vtSymbol = "SA509"
        self.exchange = "CZCE"
        self.touch_top_step = 6
        self.copy_bottom_step = [5,6,8,10,13,15,18,21,34,55,34,21,18,15,13,10]
        self.position_list = []
        self.operation_stack = []
        self.tran_auth = True
        self.min_long_position = 5
        self.dynamic_step = len(self.position_list) * self.touch_top_step

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

    def check_postition_list(self, tick):
        self.position_num = self.get_position(self.vtSymbol).long.position

        if self.tran_auth:  
            if self.position_num <= self.min_long_position:
                self.position_list = []

            if len(self.position_list) > self.position_num:
                self.position_list.pop()
                self.output("pop 持仓详情", self.position_list)

            if len(self.position_list) < self.position_num:
                self.position_list.append(tick.lastPrice)
                self.output("append 持仓详情", self.position_list)

    def onTick(self, tick: TickData) -> None:
        """收到行情 tick 推送"""
        super().onTick(tick)
        self.check_postition_list(tick)

        #多单持仓量为0，开始建仓多单
        if self.get_position(self.vtSymbol).long.position <= self.min_long_position:
            if self.tran_auth:
                self.tran_auth = False
                self.position_list.append(tick.lastPrice + 1)
                self.operation_stack.append((tick.lastPrice + 1, "B"))
                self.buy_open_position(tick.lastPrice + 1)
                self.output("多单持仓量为0，开始建仓多单")

        # 初始化建仓
        if not self.position_list:
            if self.tran_auth:
                self.tran_auth = False
                self.position_list.append(tick.lastPrice + 1)
                self.operation_stack.append((tick.lastPrice + 1, "B"))
                self.buy_open_position(tick.lastPrice + 1)
                self.output("程序启动建仓")

        if self.position_list:
            last_index = self.position_list.index(self.position_list[-1])
            # 根据买入步长逐步买进
            if (self.position_list[-1] - tick.lastPrice) >= self.copy_bottom_step[last_index]:
                if self.tran_auth:
                    self.tran_auth = False
                    self.position_list.append(tick.lastPrice + 1)
                    self.operation_stack.append((tick.lastPrice + 1, "B"))
                    self.buy_open_position(tick.lastPrice + 1)
                    self.output("最后持仓点位比当前点位高出指定间隔步长继续买入开仓")

        # 如果比上一次买入高指定步长，卖出
        if self.position_list:
            if (tick.lastPrice - self.position_list[-1]) >= self.dynamic_step and self.position_list:
                if self.tran_auth:
                    self.tran_auth = False
                    self.operation_stack.append((tick.lastPrice - 1, "S"))
                    self.sell_close_position(tick.lastPrice - 1)
                    self.output("当前价格比上一次买入高摸顶步长，卖出平仓")

        # 如果上一次是卖出，当前价格比上一次卖出价格高出步长，继续卖
        if self.position_list and self.operation_stack:
            if (self.operation_stack[-1][1] == "S" and
                    tick.lastPrice - self.operation_stack[-1][0] >= self.touch_top_step and self.position_list):
                if self.tran_auth:
                    self.tran_auth = False
                    self.operation_stack.append((tick.lastPrice - 1, "S"))
                    self.sell_close_position(tick.lastPrice - 1)
                    self.output("上一次是卖出，当前价格比上一次卖出价格高出摸顶步长，继续卖出平仓")

    def onTrade(self, trade, log=True):
        """成交回调"""
        if trade.direction == "多":
            self.position_list[-1] = trade.price
            self.operation_stack.remove(self.operation_stack[-1])
            self.operation_stack.append((trade.price, "B"))
            self.output("买入开仓", trade.price)
            self.output("持仓详情", self.position_list)
            self.output("最后操作", self.operation_stack[-1])
            self.tran_auth = True

        if trade.direction == "空":
            self.position_list.remove(self.position_list[-1])
            self.operation_stack.remove(self.operation_stack[-1])
            self.operation_stack.append((trade.price, "S"))
            self.output("卖出平仓", trade.price)
            self.output("持仓详情", self.position_list)
            self.output("最后操作", self.operation_stack[-1])
            self.tran_auth = True

        super().onTrade(trade, log)
        self.save_list(self.position_list, self.__class__.__name__ + "_position.json")
        self.save_list(self.operation_stack[-8:], self.__class__.__name__ + "_oper_stack.json")
        self.output("--------" * 8)

    def load_list(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("文件内容不是有效的列表")
            return data
        except FileNotFoundError as e:
            self.output(f"读取失败：{str(e)}")
            return []

    def save_list(self, data, file_path, ensure_ascii=False):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=ensure_ascii)
        except Exception as e:
            self.output(f"保存失败：{str(e)}")
            raise

    def onStart(self):
        self.output("onStart 读取持仓列表，操作列表")
        self.position_list = self.load_list(self.__class__.__name__ + "_position.json")
        self.output("启动持仓列表", self.position_list)
        self.operation_stack = self.load_list(self.__class__.__name__ + "_oper_stack.json")
        self.output("启动操作列表", self.operation_stack)
        super().onStart()

    def onStop(self):
        self.output("onStop 保存持仓列表，操作列表")
        self.save_list(self.position_list, self.__class__.__name__ + "_position.json")
        self.save_list(self.operation_stack[-8:], self.__class__.__name__ + "_oper_stack.json")
        super().onStop()