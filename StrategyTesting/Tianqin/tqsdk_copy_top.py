# encoding: UTF-8

import os
import json
import time
from datetime import date
import pandas as pd

from tqsdk import TqApi, TqAuth, TqSim, TqBacktest

class GrabTopTouchBom_TqSdk:
    def __init__(self, api, symbol):
        self.api = api
        self.symbol = symbol
        
        # 策略参数
        self.touch_bom_step = 6
        self.copy_top_step = [5,6,8,10,13,15,18,21,34,55,89,55,34,21,18,15,13,10]
        self.min_short_position = 1
        
        # 均线参数: 1分钟K线，60周期
        self.ma_length = 60
        
        # 策略状态
        self.position_list = [] 
        self.operation_stack = []
        self.current_order = None 
        
        # 数据对象
        self.quote = self.api.get_quote(self.symbol)
        self.klines = self.api.get_kline_serial(self.symbol, duration_seconds=60, data_length=self.ma_length+20)
        self.position = self.api.get_position(self.symbol)
        
        # --- [修改核心] 文件路径与合约绑定 ---
        # 将合约中的特殊字符替换为下划线，例如 "KQ.m@CZCE.FG" -> "KQ_m_CZCE_FG"
        safe_symbol = self.symbol.replace('.', '_').replace('@', '_')
        
        # 文件名包含合约代码，实现不同合约数据隔离
        self.base_name = f"Tq_GrabTop_{safe_symbol}"
        self.pos_file = f"{self.base_name}_position.json"
        self.stack_file = f"{self.base_name}_stack.json"
        
        self.output(f"策略数据文件已绑定: {self.pos_file}")

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
            self.position_list.sort() # 仅做排序，不做数值修改
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
        
        if direction == "SELL":
            order = self.api.insert_order(symbol=self.symbol, direction="SELL", offset="OPEN", volume=1, limit_price=price)
        else:
            order = self.api.insert_order(symbol=self.symbol, direction="BUY", offset="CLOSE", volume=1, limit_price=price)
        
        self.current_order = order

    # --- 核心逻辑 ---
    def run(self):
        self.output("策略启动")
        self.log_separator()
        
        while True:
            self.api.wait_update()
            
            last_price = self.quote.last_price
            ma_price = self.get_ma()

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

                    if direction == "SELL":
                        if self.position_list:
                             self.position_list[-1] = trade_price
                             self.position_list.sort() 
                        
                        if self.operation_stack:
                            self.operation_stack.pop()
                            self.operation_stack.append((trade_price, "S"))
                        
                        self.output("空单持仓详情", self.position_list)
                        self.output("最后操作栈", self.operation_stack[-1] if self.operation_stack else [])

                    elif direction == "BUY":
                        if self.position_list:
                            self.position_list.pop()
                            self.position_list.sort()

                        if self.operation_stack:
                            self.operation_stack.pop()
                            self.operation_stack.append((trade_price, "B"))

                        self.output("空单持仓详情", self.position_list)
                        self.output("最后操作栈", self.operation_stack[-1] if self.operation_stack else [])
                    
                    self.current_order = None
                    self.save_list(self.position_list, self.pos_file)
                    self.log_separator()

                continue 

            # ------------------------------------------------------------------
            # 2. 状态同步
            # ------------------------------------------------------------------
            real_pos = self.position.pos_short
            list_changed = False 

            # A. 实际持仓变少 -> 平仓修正
            if real_pos <= self.min_short_position:
                 if len(self.position_list) > real_pos:
                     self.position_list = []
                     list_changed = True
            
            if len(self.position_list) > real_pos:
                self.position_list = self.position_list[:real_pos]
                self.output("检测到平仓，修正 list", self.position_list)
                list_changed = True
            
            # B. 实际持仓变多 -> 开仓补录
            while len(self.position_list) < real_pos:
                self.position_list.append(last_price)
                self.output(f"检测到外部开仓，补录价格: {last_price}")
                list_changed = True
            
            if list_changed:
                self.position_list.sort()
                self.output("同步后的持仓", self.position_list)

            # ------------------------------------------------------------------
            # 3. 策略信号逻辑
            # ------------------------------------------------------------------
            
            if last_price < ma_price:
                
                # A. 绝对初始建仓 (列表为空)
                if not self.position_list:
                    if self.current_order is None:
                        target_price = last_price - 1
                        self.position_list.append(target_price)
                        self.position_list.sort()
                        self.operation_stack.append((target_price, "S"))
                        
                        reason_msg = "初始建仓 (持仓列表为空)"
                        self.insert_order("SELL", target_price, reason_msg)
                        continue

                # B. 网格加仓 (只要列表不为空，必须检查步长)
                else:
                    idx = len(self.position_list) - 1
                    step_idx = idx if idx < len(self.copy_top_step) else -1
                    step = self.copy_top_step[step_idx]

                    top_price = self.position_list[-1]
                    if (last_price - top_price) >= step:
                        if self.current_order is None:
                            target_price = last_price - 1
                            
                            self.position_list.append(target_price)
                            self.position_list.sort()
                            self.operation_stack.append((target_price, "S"))
                            
                            reason_msg = f"网格加仓 (当前价{last_price} - 最高持仓{top_price} >= 步长{step})"
                            self.insert_order("SELL", target_price, reason_msg)
                            continue

            # C. 摸底平仓
            if self.position_list:
                dynamic_step = last_price * 0.01
                max_pos_price = self.position_list[-1]
                
                if (max_pos_price - last_price) >= dynamic_step:
                    if self.current_order is None:
                        target_price = last_price + 1
                        self.operation_stack.append((target_price, "B"))
                        
                        reason_msg = f"摸底止盈 (最高持仓{max_pos_price} - 当前价{last_price} >= 止盈步长{dynamic_step})"
                        self.insert_order("BUY", target_price, reason_msg)
                        continue

if __name__ == "__main__":
    # 示例：现在切换合约会自动生成不同的文件
    SYMBOL = "CZCE.MA601"
    #SYMBOL = "DCE.m2601"
    #SYMBOL = "SHFE.rb2601" 
    
    try:
        api = TqApi(
            account=TqSim(init_balance=20000),
            backtest=TqBacktest(start_dt=date(2025, 8, 1), end_dt=date(2025, 11, 29)),
            web_gui=True,
            auth=TqAuth("cadofa", "cadofa6688"),
            debug=False
        )
        
        strategy = GrabTopTouchBom_TqSdk(api, SYMBOL)
        strategy.run()

    except Exception as e:
        print(f"\n程序运行结束: {e}")
    finally:
        if 'strategy' in locals():
            strategy.on_stop()