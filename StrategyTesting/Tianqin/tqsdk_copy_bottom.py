# encoding: UTF-8

import os
import json
import time
from datetime import datetime
from datetime import date
from tqsdk import TqApi, TqAuth, TqSim, TqBacktest
from tqsdk.ta import MA
import math

class TrendStepGridStrategy:
    """
    趋势步长网格策略 (TrendStepGridStrategy)
    """
    
    def __init__(self, api):
        self.api = api
        # 交易合约
        self.symbol = "SHFE.rb2601" 
        
        # 摸顶(止盈)基础步长
        self.touch_top_step = 6
        
        # 抄底(加仓)步长列表: 随着持仓增加，加仓间距拉大
        self.copy_bottom_step = [5, 6, 8, 10, 13, 15, 18, 21, 34, 55, 89, 55, 34, 21, 18, 15, 13, 10]
        
        self.position_list = []   # 持仓价格列表
        self.operation_stack = [] # 操作记录栈
        self.pending_order = None # 挂单锁
        
        # 均线周期
        self.QUEUE_LENGTH = 60
        
        # TqSdk 数据对象
        self.quote = self.api.get_quote(self.symbol)
        self.position = self.api.get_position(self.symbol)
        self.klines = self.api.get_kline_serial(self.symbol, duration_seconds=60, data_length=100)

        # 自动根据类名生成状态文件名
        self.files = {
            "pos": f"{self.__class__.__name__}_position.json",
            "oper": f"{self.__class__.__name__}_oper_stack.json"
        }

    def output(self, msg, data=None):
        """标准输出日志"""
        t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{t}] {msg} {data if data is not None else ''}")

    def load_data(self):
        """加载本地状态"""
        self.position_list = self._load_json(self.files["pos"])
        self.operation_stack = self._load_json(self.files["oper"])
        self.output(f"策略恢复 - 持仓层数: {len(self.position_list)}")
        if self.position_list:
            self.output(f"当前持仓列表详情: {self.position_list}")
            print("-" * 80)

    def save_data(self):
        """保存本地状态"""
        self._save_json(self.position_list, self.files["pos"])
        self._save_json(self.operation_stack[-8:], self.files["oper"])
    
    def _load_json(self, file_path):
        if not os.path.exists(file_path): return []
        try:
            with open(file_path, "r", encoding="utf-8") as f: return json.load(f)
        except: return []

    def _save_json(self, data, file_path):
        try:
            with open(file_path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False)
        except: pass

    def get_ma_price(self):
        """计算均线价格"""
        if len(self.klines) < self.QUEUE_LENGTH: return self.quote.last_price
        # 计算MA
        ma_val = MA(self.klines, self.QUEUE_LENGTH).ma.iloc[-1]
        # 处理可能的 NaN 情况 (K线不足时)
        if math.isnan(ma_val):
            return self.quote.last_price
        return ma_val

    def check_position_list_sync(self):
        """持仓同步校验"""
        if self.pending_order is not None: return
        real_pos = self.position.pos_long
        
        if real_pos == 0 and self.position_list:
             self.position_list = []
             self.operation_stack = []
             self.output("警告：账户无持仓，重置策略记录")

        if len(self.position_list) > real_pos:
            self.position_list.pop()
            self.output(f"同步修正 - Pop后持仓列表: {self.position_list}")

    def on_trade_handler(self, order):
        """成交回报处理"""
        price = order.trade_price if order.trade_price else self.quote.last_price
        
        # 获取成交时的行情数据
        current_tick = self.quote.last_price
        current_ma = self.get_ma_price()

        if order.direction == "BUY" and order.offset == "OPEN":
            if self.position_list:
                self.position_list[-1] = price
            else:
                self.position_list.append(price)
            
            if self.operation_stack and self.operation_stack[-1][1] == "B":
                 self.operation_stack.pop() 
            self.operation_stack.append((price, "B"))
            
            self.output(f"【买入成交】价格: {price}, 当前持仓: {len(self.position_list)}手")

        elif order.direction == "SELL" and order.offset == "CLOSE":
            if self.position_list: self.position_list.pop()
            if self.operation_stack and self.operation_stack[-1][1] == "S":
                self.operation_stack.pop()
            self.operation_stack.append((price, "S"))
            
            self.output(f"【卖出成交】价格: {price}, 剩余持仓: {len(self.position_list)}手")

        # --- 新增：输出成交时的价格和均线 ---
        self.output(f"【行情快照】 当前Tick价: {current_tick}, MA60均线价: {current_ma:.2f}")

        self.save_data()
        self.output(f"当前持仓列表详情: {self.position_list}")
        print("\n" + "-" * 80 + "\n")

    def execute_order(self, direction, offset, price):
        """下单执行"""
        self.output(f"正在下单: {direction} {offset} 目标价:{price}")
        order = self.api.insert_order(
            symbol=self.symbol, direction=direction, offset=offset, volume=1, limit_price=price
        )
        self.pending_order = order

    def run(self):
        self.load_data()
        self.output(f"策略 {self.__class__.__name__} 启动，监控中...")

        try:
            while self.api.wait_update():
                # --- 1. 订单状态维护 ---
                if self.pending_order:
                    if self.pending_order.status == "FINISHED":
                        self.on_trade_handler(self.pending_order)
                        self.pending_order = None
                    elif self.pending_order.status == "ALIVE":
                        continue 
                    else:
                        self.output(f"订单异常: {self.pending_order.status}")
                        self.pending_order = None 
                
                if self.pending_order: continue

                # --- 2. 数据更新 ---
                self.check_position_list_sync()
                tick_price = self.quote.last_price
                ma_price = self.get_ma_price()
                
                # --- 3. 核心策略逻辑 ---

                # [买入逻辑] 只有在价格高于均线时才考虑买入
                if tick_price > ma_price:
                    
                    # 场景A: 空仓启动
                    if not self.position_list:
                        target_price = tick_price + 1
                        self.position_list.append(target_price) # 占位
                        self.operation_stack.append((target_price, "B"))
                        self.execute_order("BUY", "OPEN", target_price)
                        self.output(f"触发首单建仓 (Tick:{tick_price} > MA:{ma_price:.2f})")
                        continue

                    # 场景B: 下跌补仓
                    if self.position_list:
                        layer_index = len(self.position_list) - 1
                        if layer_index >= len(self.copy_bottom_step):
                            step_val = self.copy_bottom_step[-1]
                        else:
                            step_val = self.copy_bottom_step[layer_index]
                        
                        price_diff = self.position_list[-1] - tick_price
                        
                        if price_diff >= step_val:
                            target_price = tick_price + 1
                            self.position_list.append(target_price)
                            self.operation_stack.append((target_price, "B"))
                            self.execute_order("BUY", "OPEN", target_price)
                            self.output(f"触发补仓: 步长满足 (Diff:{price_diff} >= Step:{step_val})")
                            continue

                # [卖出逻辑] 
                if self.position_list:
                    # 场景C: 动态止盈
                    dynamic_step = len(self.position_list) * self.touch_top_step
                    
                    if (tick_price - self.position_list[-1]) >= dynamic_step:
                        target_price = tick_price - 1
                        self.operation_stack.append((target_price, "S"))
                        self.execute_order("SELL", "CLOSE", target_price)
                        self.output(f"触发止盈: 盈利空间满足 (Diff:{tick_price - self.position_list[-1]} >= DynStep:{dynamic_step})")
                        continue
                
                # 场景D: 追踪卖出
                if self.position_list and self.operation_stack:
                    last_op_price, last_op_dir = self.operation_stack[-1]
                    if last_op_dir == "S" and (tick_price - last_op_price >= self.touch_top_step):
                        target_price = tick_price - 1
                        self.operation_stack.append((target_price, "S"))
                        self.execute_order("SELL", "CLOSE", target_price)
                        self.output(f"触发追踪卖出 (Price:{tick_price} > LastSell:{last_op_price} + {self.touch_top_step})")
                        continue

        except KeyboardInterrupt:
            self.output("手动停止策略")
        finally:
            self.save_data()
            self.output("数据已保存，程序退出")

if __name__ == "__main__":
    api = TqApi(
        account=TqSim(init_balance=100000),
        backtest=TqBacktest(start_dt=date(2025, 8, 18), end_dt=date(2025, 11, 26)),
        web_gui=True,
        auth=TqAuth("cadofa", "cadofa6688"),
        debug=False
    )
    
    strategy = TrendStepGridStrategy(api)
    strategy.run()
    
    api.close()