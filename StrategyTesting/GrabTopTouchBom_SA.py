# encoding: UTF-8

import os
import json
import time
import threading
from typing import Dict, List
from collections import deque

from ctaTemplate import CtaTemplate
from vtObject import KLineData, TickData

class GrabTopTouchBom_SA(CtaTemplate):
    def __init__(self):
        super().__init__()
        self.vtSymbol = "SA601"
        self.exchange = "CZCE"
        self.touch_bom_step = 6
        self.copy_top_step = [5,6,8,10,13,15,18,21,34,55,89,55,34,21,18,15,13,10]
        self.position_list = []
        self.operation_stack = []
        self.tran_auth = True
        self.min_short_position = 1

        #计算均线的周期，例如60就是60周期均线  
        self.QUEUE_LENGTH = 60
        #QUEUE_INTERVAL数字为分钟，1代码采集间隔为1分钟
        self.QUEUE_INTERVAL = 1
        self.QUEUE = deque(maxlen=self.QUEUE_LENGTH)
        self.last_added_time = None

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

    def check_postition_list(self, tick):
        self.position_num = self.get_position(self.vtSymbol).short.position

        if self.tran_auth:
            if self.position_num <= self.min_short_position:
                self.position_list = []

            if len(self.position_list) > self.position_num:
                self.position_list.pop()
                self.output("pop 空单持仓详情", self.position_list)

            if len(self.position_list) < self.position_num:
                self.position_list.append(tick.lastPrice)
                self.output("append 空单持仓详情", self.position_list)

    def tick_averager(self, tick):
        self.current_time = time.time()
        if self.last_added_time is None or (self.current_time - self.last_added_time >= self.QUEUE_INTERVAL * 60):
            self.QUEUE.append(tick.lastPrice)
            self.last_added_time = self.current_time
            #self.output("self.QUEUE", self.QUEUE)
            #self.output("self.tick_averager", sum(self.QUEUE) / len(self.QUEUE))
        return sum(self.QUEUE) / len(self.QUEUE)

    def onTick(self, tick: TickData) -> None:
        """收到行情 tick 推送"""
        super().onTick(tick)
        self.check_postition_list(tick)

        #确认当前空头趋势
        if tick.lastPrice < self.tick_averager(tick):
            # 空单持仓量为0，开始建仓空单
            if self.get_position(self.vtSymbol).short.position <= self.min_short_position:
                if self.tran_auth:
                    self.tran_auth = False
                    self.position_list.append(tick.lastPrice - 1)
                    self.operation_stack.append((tick.lastPrice - 1, "S"))
                    self.sell_open_position(tick.lastPrice - 1)
                    self.output("self.tick_averager", sum(self.QUEUE) / len(self.QUEUE))
                    self.output("空单持仓量为0，开始建仓空单")

            # 初始化建仓
            if not self.position_list:
                if self.tran_auth:
                    self.tran_auth = False
                    self.position_list.append(tick.lastPrice - 1)
                    self.operation_stack.append((tick.lastPrice - 1, "S"))
                    self.sell_open_position(tick.lastPrice - 1)
                    self.output("self.tick_averager", sum(self.QUEUE) / len(self.QUEUE))
                    self.output("程序启动建仓空单")

            if self.position_list:
                last_index = self.position_list.index(self.position_list[-1])
                # 根据卖出步长逐步卖出建仓
                if (tick.lastPrice - self.position_list[-1]) >= self.copy_top_step[last_index]:
                    if self.tran_auth:
                        self.tran_auth = False
                        self.position_list.append(tick.lastPrice - 1)
                        self.operation_stack.append((tick.lastPrice - 1, "S"))
                        self.sell_open_position(tick.lastPrice - 1)
                        self.output("self.tick_averager", sum(self.QUEUE) / len(self.QUEUE))
                        self.output("当前点位比最后持仓点位高出指定间隔步长继续卖出开仓")

        # 如果比上一次卖出低动态步长，买入平仓
        if self.position_list:
            self.dynamic_step = len(self.position_list) * self.touch_bom_step
            if (self.position_list[-1] - tick.lastPrice) >= self.dynamic_step and self.position_list:
                if self.tran_auth:
                    self.tran_auth = False
                    self.operation_stack.append((tick.lastPrice + 1, "B"))
                    self.buy_close_position(tick.lastPrice + 1)
                    self.output("当前动态步长", self.dynamic_step)
                    self.output("当前价格比上一次卖出低摸底步长，买入平仓")

        # 如果上一次是买入，当前价格比上一次买入价格低出步长，继续买入平仓
        if self.position_list and self.operation_stack:
            if (self.operation_stack[-1][1] == "B" and
                    self.operation_stack[-1][0] - tick.lastPrice >= self.touch_bom_step and self.position_list):
                if self.tran_auth:
                    self.tran_auth = False
                    self.operation_stack.append((tick.lastPrice + 1, "B"))
                    self.buy_close_position(tick.lastPrice + 1)
                    self.output("上一次是买入，当前价格比上一次买入价格低出摸底步长，继续买入平仓")

    def onTrade(self, trade, log=True):
        """成交回调"""
        if trade.direction == "空":
            self.position_list[-1] = trade.price
            self.operation_stack.remove(self.operation_stack[-1])
            self.operation_stack.append((trade.price, "S"))
            self.output("卖出开仓", trade.price)
            self.output("空单持仓详情", self.position_list)
            self.output("最后操作", self.operation_stack[-1])
            self.tran_auth = True

        if trade.direction == "多":
            self.position_list.remove(self.position_list[-1])
            self.operation_stack.remove(self.operation_stack[-1])
            self.operation_stack.append((trade.price, "B"))
            self.output("买入平仓", trade.price)
            self.output("空单持仓详情", self.position_list)
            self.output("最后操作", self.operation_stack[-1])
            self.tran_auth = True

        super().onTrade(trade, log)
        self.save_list(self.position_list, self.__class__.__name__ + "_position.json")
        self.save_list(self.operation_stack[-8:], self.__class__.__name__ + "_oper_stack.json")
        self.save_list(list(self.QUEUE), self.__class__.__name__ + "_tick_averager.json")
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
        self.QUEUE = deque(self.load_list(self.__class__.__name__ + "_tick_averager.json"), maxlen=self.QUEUE_LENGTH)
        super().onStart()

    def onStop(self):
        self.output("onStop 保存持仓列表，操作列表")
        self.save_list(self.position_list, self.__class__.__name__ + "_position.json")
        self.save_list(self.operation_stack[-8:], self.__class__.__name__ + "_oper_stack.json")
        self.save_list(list(self.QUEUE), self.__class__.__name__ + "_tick_averager.json")
        super().onStop()
