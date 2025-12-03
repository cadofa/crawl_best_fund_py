# encoding: UTF-8

import os
import json
import time
from datetime import date
import pandas as pd

from tqsdk import TqApi, TqAuth, TqSim, TqBacktest

class GrabBottomTouchTop_TqSdk:
    def __init__(self, api, symbol):
        self.api = api
        self.symbol = symbol
        
        # 均线参数: 1分钟K线，60周期 (提前定义，供K线数据获取使用)
        self.ma_length = 60

        # --- [修改处开始] ---
        # 1. 先获取 Quote 对象以读取合约的最小跳价 (price_tick)
        self.quote = self.api.get_quote(self.symbol)
        
        # 获取该合约的一跳是多少钱 (例如: 螺纹钢是1, 焦炭是0.5, 玻璃是1, 纯碱是1等)
        # 注意：TqSdk会在初始化时自动同步合约信息，此处可直接读取
        tick = self.quote.price_tick
        
        # 2. 策略参数适配
        # 原参数定义的数值为"跳数"，乘以 tick 得到实际的价格价差
        self.touch_top_step = 6 * tick
        
        raw_bottom_steps = [5,6,8,10,13,15,18,21,34,55,89,55,34,21,18,15,13,10]
        self.copy_bottom_step = [x * tick for x in raw_bottom_steps]
        
        self.min_long_position = 1
        # --- [修改处结束] ---
        
        # 策略状态
        self.position_list = [] 
        self.operation_stack = []
        self.current_order = None 
        
        # 数据对象 (Quote已在上面获取，这里获取K线和持仓)
        self.klines = self.api.get_kline_serial(self.symbol, duration_seconds=60, data_length=self.ma_length+20)
        self.position = self.api.get_position(self.symbol)
        
        # --- [修改核心] 文件路径与合约绑定 ---
        # 将合约中的特殊字符替换为下划线，例如 "KQ.m@CZCE.FG" -> "KQ_m_CZCE_FG"
        safe_symbol = self.symbol.replace('.', '_').replace('@', '_')
        
        # 文件名包含合约代码，实现不同合约数据隔离
        self.base_name = f"Tq_GrabBottom_{safe_symbol}"
        self.pos_file = f"{self.base_name}_position.json"
        self.stack_file = f"{self.base_name}_stack.json"
        
        self.output(f"策略数据文件已绑定: {self.pos_file}")
        self.output(f"合约最小跳价: {tick}, 网格步长(实际价格): {self.copy_bottom_step}")

        # 初始化加载
        self.on_start()

    def output(self, msg, data=None):
        """通用日志输出"""
        t = self.quote.datetime if self.quote.datetime else ""
        content = f"{msg} {data if data is not None else ''}"
        print(f"[{t}] {content}")

    def log_market_info(self, ma_price):
        """打印当前市场状态"""
        print(f">>> 市场状态 | 最新价: {self.quote.last_price} | MA60: {ma_price:.2f}")

    def log_separator(self):
        """打印分割线"""
        print("\n" + "-" * 80 + "\n")

    # --- 数据持久化 ---
    def load_list(self, file_path):
        if not os.path.exists(file_path):
            self.output(f"未找到历史文件 {file_path}，将作为新策略启动")
            return []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"读取失败 {file_path}：{str(e)}")
            return []

    def save_list(self, data, file_path):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"保存失败 {file_path}：{str(e)}")

    def on_start(self):
        """策略启动，加载状态"""
        self.position_list = self.load_list(self.pos_file)
        if self.position_list:
            self.position_list.sort(reverse=True) # 仅做排序，不做数值修改
        self.operation_stack = self.load_list(self.stack_file)

    def on_stop(self):
        """策略停止"""
        self.save_list(self.position_list, self.pos_file)
        self.save_list(self.operation_stack[-8:], self.stack_file)

    # --- 辅助功能 ---
    def get_ma(self):
        """计算1分钟60周期均线"""
        if self.klines is None or len(self.klines) < self.ma_length:
            return None
        return self.klines.close.iloc[-self.ma_length:].mean()

    def insert_order(self, direction, price, reason=""):
        """下单封装"""
        ma = self.get_ma()
        self.output(f"【发出指令】 {direction} 目标价: {price}")
        self.output(f"   └─ 理由: {reason}")
        self.log_market_info(ma if ma else 0)
        
        if direction == "BUY":
            order = self.api.insert_order(symbol=self.symbol, direction="BUY", offset="OPEN", volume=1, limit_price=price)
        else:
            order = self.api.insert_order(symbol=self.symbol, direction="SELL", offset="CLOSE", volume=1, limit_price=price)
        
        self.current_order = order

    # --- 核心逻辑 ---
    def run(self):
        self.output("策略启动")
        self.log_separator()
        
        while True:
            self.api.wait_update()
            
            last_price = self.quote.last_price
            ma_price = self.get_ma()
            
            # 使用 self.quote.price_tick 获取当前合约的最小跳价
            tick = self.quote.price_tick

            if ma_price is None or pd.isna(ma_price) or pd.isna(last_price):
                continue

            # ------------------------------------------------------------------
            # 1. 处理订单状态
            # ------------------------------------------------------------------
            if self.current_order:
                if self.current_order.is_error:
                    self.output("订单错单", self.current_order.last_msg)
                    self.current_order = None 
                    continue

                if self.current_order.status == "FINISHED":
                    trade_price = self.current_order.trade_price
                    direction = self.current_order.direction
                    
                    self.output(f"【成交确认】 {direction} @ {trade_price}")
                    self.log_market_info(ma_price)

                    if direction == "BUY":
                        if self.position_list:
                             self.position_list[-1] = trade_price
                             self.position_list.sort(reverse=True) 
                        
                        if self.operation_stack:
                            self.operation_stack.pop()
                            self.operation_stack.append((trade_price, "B"))
                        
                        self.output("多单持仓详情", self.position_list)
                        self.output("最后操作栈", self.operation_stack[-1] if self.operation_stack else [])

                    elif direction == "SELL":
                        if self.position_list:
                            self.position_list.pop()
                            self.position_list.sort(reverse=True)

                        if self.operation_stack:
                            self.operation_stack.pop()
                            self.operation_stack.append((trade_price, "S"))

                        self.output("多单持仓详情", self.position_list)
                        self.output("最后操作栈", self.operation_stack[-1] if self.operation_stack else [])
                    
                    self.current_order = None
                    self.save_list(self.position_list, self.pos_file)
                    self.log_separator()

                continue 

            # ------------------------------------------------------------------
            # 2. 状态同步
            # ------------------------------------------------------------------
            real_pos = self.position.pos_long
            list_changed = False 

            # A. 实际持仓变少 -> 平仓修正
            # 如果实际持仓小于当前文件记录的持仓，说明有外部平仓操作，
            # 则依次修改self.position_list列表（将列表尾部多余的持仓去除）
            while len(self.position_list) > real_pos:
                self.position_list.pop()
                self.output("检测到外部平仓，移除尾部持仓")
                list_changed = True
            
            # B. 实际持仓变多 -> 开仓补录
            # 如果实际持仓大于当前文件记录的尺寸，说明有外部开仓操作，
            # 则依次在self.position尾部添加持仓(持仓价格为直接添加当前最新价)
            while len(self.position_list) < real_pos:
                self.position_list.append(last_price)
                self.output(f"检测到外部开仓，补录价格: {last_price}")
                list_changed = True
            
            if list_changed:
                self.position_list.sort(reverse=True)
                self.output("同步后的持仓", self.position_list)

            # ------------------------------------------------------------------
            # 3. 策略信号逻辑
            # ------------------------------------------------------------------
            
            if last_price > ma_price:
                
                # A. 绝对初始建仓 (列表为空)
                if not self.position_list:
                    if self.current_order is None:
                        # [修正] 价格 + 1个tick
                        target_price = last_price + tick
                        self.position_list.append(target_price)
                        self.position_list.sort(reverse=True)
                        self.operation_stack.append((target_price, "B"))
                        
                        reason_msg = "初始建仓 (持仓列表为空)"
                        self.insert_order("BUY", target_price, reason_msg)
                        continue

                # B. 网格加仓 (只要列表不为空，必须检查步长)
                else:
                    idx = len(self.position_list) - 1
                    step_idx = idx if idx < len(self.copy_bottom_step) else -1
                    step = self.copy_bottom_step[step_idx]

                    bottom_price = self.position_list[-1]
                    if (bottom_price - last_price) >= step:
                        if self.current_order is None:
                            # [修正] 价格 + 1个tick
                            target_price = last_price + tick
                            
                            self.position_list.append(target_price)
                            self.position_list.sort(reverse=True)
                            self.operation_stack.append((target_price, "B"))
                            
                            reason_msg = f"网格加仓 (最低持仓{bottom_price} - 当前价{last_price} >= 步长{step})"
                            self.insert_order("BUY", target_price, reason_msg)
                            continue

            # C. 触顶平仓 (止盈)
            if self.position_list:
                # 1. 原策略：动态百分比止盈
                dynamic_step = last_price * 0.01 
                min_pos_price = self.position_list[-1]

                if (last_price - min_pos_price) >= dynamic_step:
                    if self.current_order is None:
                        # [修正] 价格 - 1个tick
                        target_price = last_price - tick
                        self.operation_stack.append((target_price, "S"))
                        
                        reason_msg = f"触顶止盈1 (当前价{last_price} - 最低持仓{min_pos_price} >= 止盈步长{dynamic_step:.2f})"
                        self.insert_order("SELL", target_price, reason_msg)
                        continue
                
                # 2. 新增策略：根据持仓数量 * touch_top_step 进行止盈
                step_threshold = len(self.position_list) * self.touch_top_step
                
                if (last_price - min_pos_price) >= step_threshold:
                    if self.current_order is None:
                        # [修正] 价格 - 1个tick
                        target_price = last_price - tick
                        self.operation_stack.append((target_price, "S"))
                        
                        reason_msg = f"触顶止盈2 (当前价{last_price} - 最低持仓{min_pos_price} >= 阶梯阈值{step_threshold:.2f} [持仓数{len(self.position_list)}])"
                        self.insert_order("SELL", target_price, reason_msg)
                        continue

if __name__ == "__main__":
    # 示例：现在切换合约会自动生成不同的文件
    SYMBOL = "CZCE.TA601"
    
    try:
        api = TqApi(
            account=TqSim(init_balance=100000),
            backtest=TqBacktest(start_dt=date(2025, 8, 1), end_dt=date(2025, 12, 2)),
            web_gui=True,
            auth=TqAuth("cadofa", "cadofa6688"),
            debug=False
        )
        
        strategy = GrabBottomTouchTop_TqSdk(api, SYMBOL)
        strategy.run()

    except Exception as e:
        print(f"\n程序运行结束: {e}")
    finally:
        if 'strategy' in locals():
            strategy.on_stop()