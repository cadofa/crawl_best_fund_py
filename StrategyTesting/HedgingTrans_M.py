# encoding: UTF-8

from typing import Dict, List

from ctaTemplate import CtaTemplate
from vtObject import KLineData, TickData

class HedgingTrans_M(CtaTemplate):
    def __init__(self):
        super().__init__()
        self.vtSymbol = "m2505"
        self.exchange = "DCE"
        self.touch_step = 6
        self.copy_step = [5,6,8,10,13,15,18,21,34,55,34,21,18,15,13,10]
        self.B_long_pos_list = []
        self.B_long_op_stack = []
        self.S_short_pos_list = []
        self.S_short_op_stack = []
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

        # 初始化建仓
        # if not self.B_long_pos_list and not self.B_long_op_stack:
        if not self.B_long_pos_list and (B_pos_num < S_pos_num):
            if self.tran_auth:
                self.tran_auth = False
                self.B_long_pos_list.append(tick.lastPrice + 1)
                self.B_long_op_stack.append((tick.lastPrice + 1, "B"))
                self.buy_open_position(tick.lastPrice + 1)
                self.output("对冲策略中多单数量 %d, 空单数量 %d, 多单建仓" % (B_pos_num, S_pos_num))

        # 有过操作，没有持仓
        if self.B_long_op_stack and not self.B_long_pos_list and (B_pos_num < S_pos_num):
            # 如果上一次是卖出，当前价格比上一次卖出价格低出步长，继续买
            if (self.B_long_op_stack[-1][1] == "S" and
                    self.B_long_op_stack[-1][0] - tick.lastPrice >= self.touch_step):
                if self.tran_auth:
                    self.tran_auth = False
                    self.B_long_pos_list.append(tick.lastPrice + 1)
                    self.B_long_op_stack.append((tick.lastPrice + 1, "B"))
                    self.buy_open_position(tick.lastPrice + 1)
                    self.output("对冲策略中多单数量 %d, 空单数量 %d, 多单建仓" % (B_pos_num, S_pos_num))
                    self.output("对冲策略中上一次操作是卖出，当前价格比上一次卖出价格低出摸顶步长，继续买")

        if self.B_long_pos_list and (B_pos_num < S_pos_num):
            last_index = self.B_long_pos_list.index(self.B_long_pos_list[-1])
            # 根据买入步长逐步买进
            if (self.B_long_pos_list[-1] - tick.lastPrice) >= self.copy_step[last_index]:
                if self.tran_auth:
                    self.tran_auth = False
                    self.B_long_pos_list.append(tick.lastPrice + 1)
                    self.B_long_op_stack.append((tick.lastPrice + 1, "B"))
                    self.buy_open_position(tick.lastPrice + 1)
                    self.output("对冲策略中多单数量 %d, 空单数量 %d, 多单建仓" % (B_pos_num, S_pos_num))
                    self.output("对冲策略中最后持仓点位比当前点位高出指定间隔步长继续买入开仓")

        # 如果比上一次买入高指定步长，卖出
        if self.B_long_pos_list:
            if (tick.lastPrice - self.B_long_pos_list[-1]) >= self.touch_step and self.B_long_pos_list:
                if self.tran_auth:
                    self.tran_auth = False
                    self.B_long_op_stack.append((tick.lastPrice - 1, "S"))
                    self.sell_close_position(tick.lastPrice - 1)
                    self.output("对冲策略中当前价格比上一次买入高摸顶步长，卖出平仓")
        
        # 如果上一次是卖出，当前价格比上一次卖出价格高出步长，继续卖
        if self.B_long_pos_list:
            if (self.B_long_op_stack[-1][1] == "S" and
                    tick.lastPrice - self.B_long_op_stack[-1][0] >= self.touch_step and self.B_long_pos_list):
                if self.tran_auth:
                    self.tran_auth = False
                    self.B_long_op_stack.append((tick.lastPrice - 1, "S"))
                    self.sell_close_position(tick.lastPrice - 1)
                    self.output("对冲策略中上一次是卖出，当前价格比上一次卖出价格高出摸顶步长，继续卖出平仓")

        # 初始化建仓
        # if not self.S_short_pos_list and not self.S_short_op_stack:
        if not self.S_short_pos_list and (S_pos_num < B_pos_num):
            if self.tran_auth:
                self.tran_auth = False
                self.S_short_pos_list.append(tick.lastPrice - 1)
                self.S_short_op_stack.append((tick.lastPrice - 1, "S"))
                self.sell_open_position(tick.lastPrice - 1)
                self.output("对冲策略中多单数量 %d, 空单数量 %d, 空单建仓" % (B_pos_num, S_pos_num))

        # 有过操作，没有持仓
        if self.S_short_op_stack and not self.S_short_pos_list and (S_pos_num < B_pos_num):
            # 如果上一次是买入，当前价格比上一次买入价格高出步长，继续卖
            if (self.S_short_op_stack[-1][1] == "B" and
                    tick.lastPrice - self.S_short_op_stack[-1][0] >= self.touch_step):
                if self.tran_auth:
                    self.tran_auth = False
                    self.S_short_pos_list.append(tick.lastPrice - 1)
                    self.S_short_op_stack.append((tick.lastPrice - 1, "S"))
                    self.sell_open_position(tick.lastPrice - 1)
                    self.output("对冲策略中多单数量 %d, 空单数量 %d, 空单建仓" % (B_pos_num, S_pos_num))
                    self.output("对冲策略中上一次操作是买入平仓，当前价格比上一次买入价格高出摸底步长，继续卖出开仓")

        if self.S_short_pos_list and (S_pos_num < B_pos_num):
            last_index = self.S_short_pos_list.index(self.S_short_pos_list[-1])
            # 根据卖出步长逐步卖出
            if (tick.lastPrice - self.S_short_pos_list[-1]) >= self.copy_step[last_index]:
                if self.tran_auth:
                    self.tran_auth = False
                    self.S_short_pos_list.append(tick.lastPrice - 1)
                    self.S_short_op_stack.append((tick.lastPrice - 1, "S"))
                    self.sell_open_position(tick.lastPrice - 1)
                    self.output("对冲策略中多单数量 %d, 空单数量 %d, 空单建仓" % (B_pos_num, S_pos_num))
                    self.output("对冲策略中当前点位比最后持仓点位高出指定间隔步长继续卖出开仓")

        # 如果比上一次卖出低指定步长，买入平仓
        if self.S_short_pos_list:
            if (self.S_short_pos_list[-1] - tick.lastPrice) >= self.touch_step and self.S_short_pos_list:
                if self.tran_auth:
                    self.tran_auth = False
                    self.S_short_op_stack.append((tick.lastPrice + 1, "B"))
                    self.buy_close_position(tick.lastPrice + 1)
                    self.output("对冲策略中当前价格比上一次卖出低摸底步长，买入平仓")

        # 如果上一次是买入，当前价格比上一次买入价格低出步长，继续买入平仓
        if self.S_short_pos_list:
            if (self.S_short_op_stack[-1][1] == "B" and
                    self.S_short_op_stack[-1][0] - tick.lastPrice >= self.touch_step and self.S_short_pos_list):
                if self.tran_auth:
                    self.tran_auth = False
                    self.S_short_op_stack.append((tick.lastPrice + 1, "B"))
                    self.buy_close_position(tick.lastPrice + 1)
                    self.output("对冲策略中上一次是买入，当前价格比上一次买入价格低出摸底步长，继续买入平仓")

    def onTrade(self, trade, log=True):
        """成交回调"""
        if trade.direction == "多" and trade.offset == "开仓":
            self.B_long_pos_list[-1] = trade.price
            self.B_long_op_stack.remove(self.B_long_op_stack[-1])
            self.B_long_op_stack.append((trade.price, "B"))
            self.output("对冲买入开仓", trade.price)
            self.output("对冲持仓详情", self.B_long_pos_list)
            self.output("对冲最后操作", self.B_long_op_stack[-1])
            self.tran_auth = True

        if trade.direction == "空" and trade.offset == "平仓":
            self.B_long_pos_list.remove(self.B_long_pos_list[-1])
            self.B_long_op_stack.remove(self.B_long_op_stack[-1])
            self.B_long_op_stack.append((trade.price, "S"))
            self.output("对冲卖出平仓", trade.price)
            self.output("对冲持仓详情", self.B_long_pos_list)
            self.output("对冲最后操作", self.B_long_op_stack[-1])
            self.tran_auth = True
            
        if trade.direction == "空" and trade.offset == "开仓":
            self.S_short_pos_list[-1] = trade.price
            self.S_short_op_stack.remove(self.S_short_op_stack[-1])
            self.S_short_op_stack.append((trade.price, "S"))
            self.output("对冲卖出开仓", trade.price)
            self.output("对冲空单持仓详情", self.S_short_pos_list)
            self.output("对冲最后操作", self.S_short_op_stack[-1])
            self.tran_auth = True

        if trade.direction == "多" and trade.offset == "平仓":
            self.S_short_pos_list.remove(self.S_short_pos_list[-1])
            self.S_short_op_stack.remove(self.S_short_op_stack[-1])
            self.S_short_op_stack.append((trade.price, "B"))
            self.output("对冲买入平仓", trade.price)
            self.output("对冲空单持仓详情", self.S_short_pos_list)
            self.output("对冲最后操作", self.S_short_op_stack[-1])
            self.tran_auth = True

        super().onTrade(trade, log)
        self.output("--------" * 8)


    def onStart(self):
        self.output("onStart")
        super().onStart()

    def onStop(self):
        self.output("onStop")
        super().onStop()
