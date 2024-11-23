# encoding: UTF-8

from typing import Dict, List

from ctaTemplate import CtaTemplate
from vtObject import KLineData, TickData

class GrabBomTouchTop_M(CtaTemplate):
    def __init__(self):
        super().__init__()
        self.vtSymbol = "m2505"
        self.exchange = "DCE"
        self.touch_top_step = 6
        self.copy_bottom_step = [5,6,8,10,13,15,18,21,34,55,34,21,18,15,13,10]
        self.position_list = []
        self.operation_stack = []
        self.tran_auth = True


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

    def onTick(self, tick: TickData) -> None:
        """收到行情 tick 推送"""
        super().onTick(tick)

        #多单持仓量为0，开始建仓多单
        if self.get_position(self.vtSymbol).long.position == 0:
            if self.tran_auth:
                self.tran_auth = False
                self.position_list.append(tick.lastPrice + 1)
                self.operation_stack.append((tick.lastPrice + 1, "B"))
                self.buy_open_position(tick.lastPrice + 1)
                self.output("多单持仓量为0，开始建仓多单")

        # 初始化建仓
        # if not self.position_list and not self.operation_stack:
        if not self.position_list:
            if self.tran_auth:
                self.tran_auth = False
                self.position_list.append(tick.lastPrice + 1)
                self.operation_stack.append((tick.lastPrice + 1, "B"))
                self.buy_open_position(tick.lastPrice + 1)
                self.output("程序启动建仓")

        # 有过操作，没有持仓
        if self.operation_stack and not self.position_list:
            # 如果上一次是卖出，当前价格比上一次卖出价格低出步长，继续买
            if (self.operation_stack[-1][1] == "S" and
                    self.operation_stack[-1][0] - tick.lastPrice >= self.touch_top_step):
                if self.tran_auth:
                    self.tran_auth = False
                    self.position_list.append(tick.lastPrice + 1)
                    self.operation_stack.append((tick.lastPrice + 1, "B"))
                    self.buy_open_position(tick.lastPrice + 1)
                    self.output("上一次操作是卖出，当前价格比上一次卖出价格低出摸顶步长，继续买")

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
            if (tick.lastPrice - self.position_list[-1]) >= self.touch_top_step and self.position_list:
                if self.tran_auth:
                    self.tran_auth = False
                    self.operation_stack.append((tick.lastPrice - 1, "S"))
                    self.sell_close_position(tick.lastPrice - 1)
                    self.output("当前价格比上一次买入高摸顶步长，卖出平仓")
        
        # 如果上一次是卖出，当前价格比上一次卖出价格高出步长，继续卖
        if self.position_list:
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
        self.output("--------" * 8)


    def onStart(self):
        self.output("onStart")
        super().onStart()

    def onStop(self):
        self.output("onStop")
        super().onStop()
