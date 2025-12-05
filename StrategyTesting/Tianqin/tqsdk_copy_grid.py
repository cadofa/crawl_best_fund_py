# encoding: UTF-8

import os
import json
import time
from datetime import date
import pandas as pd

from tqsdk import TqApi, TqAuth, TqSim, TqBacktest, BacktestFinished

class GrabBottomTop_Dual_TqSdk:
    def __init__(self, api, symbol):
        self.api = api
        self.symbol = symbol
        
        # 均线参数: 1分钟K线，60周期
        self.ma_length = 60

        # --- [基础数据获取] ---
        # 1. 先获取 Quote 对象以读取合约的最小跳价 (price_tick)
        self.quote = self.api.get_quote(self.symbol)
        tick = self.quote.price_tick
        
        # --- [策略参数适配：多单 (Bottom)] ---
        # 原参数定义的数值为"跳数"，乘以 tick 得到实际的价格价差
        self.touch_top_step = 6 * tick
        raw_bottom_steps = [5,6,8,10,13,15,18,21,34,55,89,55,34,21,18,15,13,10]
        self.copy_bottom_step = [x * tick for x in raw_bottom_steps]
        self.min_long_position = 1
        
        # --- [策略参数适配：空单 (Top)] ---
        self.touch_bom_step = 6 * tick
        raw_top_steps = [5,6,8,10,13,15,18,21,34,55,89,55,34,21,18,15,13,10]
        self.copy_top_step = [x * tick for x in raw_top_steps]
        self.min_short_position = 1

        # --- [状态管理] ---
        # 多单状态
        self.long_pos_list = [] 
        self.long_stack = []
        self.long_order = None 

        # 空单状态
        self.short_pos_list = []
        self.short_stack = []
        self.short_order = None

        # --- [数据对象] ---
        self.klines = self.api.get_kline_serial(self.symbol, duration_seconds=60, data_length=self.ma_length+20)
        self.position = self.api.get_position(self.symbol)
        
        # --- [文件路径与合约绑定] ---
        # 将合约中的特殊字符替换为下划线
        safe_symbol = self.symbol.replace('.', '_').replace('@', '_')
        self.base_name = f"Tq_Dual_{safe_symbol}"
        
        # 多单文件
        self.file_long_pos = f"{self.base_name}_Long_position.json"
        self.file_long_stack = f"{self.base_name}_Long_stack.json"
        
        # 空单文件
        self.file_short_pos = f"{self.base_name}_Short_position.json"
        self.file_short_stack = f"{self.base_name}_Short_stack.json"
        
        self.output(f"策略已启动，合约: {self.symbol}, Tick: {tick}")
        self.output(f"多单文件: {self.file_long_pos}")
        self.output(f"空单文件: {self.file_short_pos}")

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
            self.output(f"未找到历史文件 {file_path}，初始化为空列表")
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
        # 加载多单
        self.long_pos_list = self.load_list(self.file_long_pos)
        if self.long_pos_list:
            self.long_pos_list.sort(reverse=True) # 多单降序
        self.long_stack = self.load_list(self.file_long_stack)
        
        # 加载空单
        self.short_pos_list = self.load_list(self.file_short_pos)
        if self.short_pos_list:
            self.short_pos_list.sort() # 空单升序
        self.short_stack = self.load_list(self.file_short_stack)

    def on_stop(self):
        """策略停止"""
        self.save_list(self.long_pos_list, self.file_long_pos)
        self.save_list(self.long_stack[-8:], self.file_long_stack)
        
        self.save_list(self.short_pos_list, self.file_short_pos)
        self.save_list(self.short_stack[-8:], self.file_short_stack)

    # --- 辅助功能 ---
    def get_ma(self):
        """计算1分钟60周期均线"""
        if self.klines is None or len(self.klines) < self.ma_length:
            return None
        return self.klines.close.iloc[-self.ma_length:].mean()

    def insert_order(self, direction, price, reason="", strategy_type="LONG"):
        """
        下单封装
        strategy_type: "LONG" (多单策略) 或 "SHORT" (空单策略)
        """
        ma = self.get_ma()
        self.output(f"【发出指令 ({strategy_type})】 {direction} 目标价: {price}")
        self.output(f"   └─ 理由: {reason}")
        self.log_market_info(ma if ma else 0)
        
        offset_flag = "OPEN" # 默认开仓
        final_direction = direction

        # 逻辑分支：根据策略类型和买卖方向确定 offset
        exchange_id = self.symbol.split('.')[0]
        is_shfe_ine = exchange_id in ["SHFE", "INE"]

        # --- 多单策略逻辑 (Bottom) ---
        if strategy_type == "LONG":
            if direction == "BUY":
                offset_flag = "OPEN"
            else: # SELL (平多)
                offset_flag = "CLOSE"
                if is_shfe_ine:
                    # 检查持仓对象的昨多仓数量
                    if self.position.pos_long_his > 0:
                        offset_flag = "CLOSE"
                    else:
                        offset_flag = "CLOSETODAY"

        # --- 空单策略逻辑 (Top) ---
        elif strategy_type == "SHORT":
            if direction == "SELL":
                offset_flag = "OPEN"
            else: # BUY (平空)
                offset_flag = "CLOSE"
                if is_shfe_ine:
                    # 检查持仓对象的昨空仓数量
                    if self.position.pos_short_his > 0:
                        offset_flag = "CLOSE"
                    else:
                        offset_flag = "CLOSETODAY"

        order = self.api.insert_order(
            symbol=self.symbol, 
            direction=final_direction, 
            offset=offset_flag, 
            volume=1, 
            limit_price=price
        )
        
        # 将订单对象返回给调用者，以便分别赋值给 long_order 或 short_order
        return order

    # --- 核心逻辑 ---
    def run(self):
        self.output("双向网格策略启动")
        self.log_separator()
        
        while True:
            self.api.wait_update()
            
            last_price = self.quote.last_price
            ma_price = self.get_ma()
            tick = self.quote.price_tick

            if ma_price is None or pd.isna(ma_price) or pd.isna(last_price):
                continue

            # ==================================================================
            # 模块一：多单策略逻辑 (GrabBottom)
            # ==================================================================
            
            # 1.1 处理多单订单状态
            if self.long_order:
                if self.long_order.is_error:
                    self.output("[多单] 订单错单", self.long_order.last_msg)
                    self.long_order = None 
                
                elif self.long_order.status == "FINISHED":
                    trade_price = self.long_order.trade_price
                    direction = self.long_order.direction
                    
                    self.output(f"【多单成交】 {direction} @ {trade_price}")
                    
                    if direction == "BUY": # 开多成功
                        if self.long_pos_list:
                             self.long_pos_list[-1] = trade_price
                             self.long_pos_list.sort(reverse=True) 
                        if self.long_stack:
                            self.long_stack.pop()
                            self.long_stack.append((trade_price, "B"))
                    
                    elif direction == "SELL": # 平多成功
                        if self.long_pos_list:
                            self.long_pos_list.pop()
                            self.long_pos_list.sort(reverse=True)
                        if self.long_stack:
                            self.long_stack.pop()
                            self.long_stack.append((trade_price, "S"))
                    
                    self.output("多单持仓详情", self.long_pos_list)
                    self.long_order = None
                    self.save_list(self.long_pos_list, self.file_long_pos)
                    self.log_separator()
            
            # 1.2 多单状态同步 (仅在无活跃订单时)
            if self.long_order is None:
                real_pos_long = self.position.pos_long
                long_changed = False
                
                # A. 实际多单变少 -> 平仓修正
                while len(self.long_pos_list) > real_pos_long:
                    self.long_pos_list.pop()
                    self.output("[多单] 检测到外部平仓，移除尾部持仓")
                    long_changed = True
                
                # B. 实际多单变多 -> 开仓补录
                while len(self.long_pos_list) < real_pos_long:
                    self.long_pos_list.append(last_price)
                    self.output(f"[多单] 检测到外部开仓，补录价格: {last_price}")
                    long_changed = True
                
                if long_changed:
                    self.long_pos_list.sort(reverse=True)
                    self.output("同步后的多单持仓", self.long_pos_list)

                # 1.3 多单策略信号逻辑
                if last_price > ma_price:
                    # A. 绝对初始建仓
                    if (not self.long_pos_list) or (real_pos_long < self.min_long_position):
                        target_price = last_price + tick
                        self.long_pos_list.append(target_price)
                        self.long_pos_list.sort(reverse=True)
                        self.long_stack.append((target_price, "B"))
                        
                        self.long_order = self.insert_order("BUY", target_price, "初始建仓 (多)", "LONG")

                    # B. 网格加仓 (Price drop)
                    else:
                        idx = len(self.long_pos_list) - 1
                        step_idx = idx if idx < len(self.copy_bottom_step) else -1
                        step = self.copy_bottom_step[step_idx]

                        bottom_price = self.long_pos_list[-1]
                        if (bottom_price - last_price) >= step:
                            target_price = last_price + tick
                            self.long_pos_list.append(target_price)
                            self.long_pos_list.sort(reverse=True)
                            self.long_stack.append((target_price, "B"))
                            
                            reason = f"网格加仓 (最低{bottom_price} - 现价{last_price} >= 步长{step})"
                            self.long_order = self.insert_order("BUY", target_price, reason, "LONG")

                # C. 触顶平仓 (止盈)
                if self.long_pos_list and self.long_order is None:
                    dynamic_step = last_price * 0.01 
                    min_pos_price = self.long_pos_list[-1]
                    step_threshold = len(self.long_pos_list) * self.touch_top_step
                    
                    # 止盈条件 1 或 2
                    is_profit_1 = (last_price - min_pos_price) >= dynamic_step
                    is_profit_2 = (last_price - min_pos_price) >= step_threshold
                    
                    if is_profit_1 or is_profit_2:
                        target_price = last_price - tick
                        self.long_stack.append((target_price, "S"))
                        
                        trigger = "动态百分比" if is_profit_1 else f"阶梯阈值({step_threshold})"
                        reason = f"触顶止盈 [{trigger}] (现价{last_price} - 最低{min_pos_price})"
                        self.long_order = self.insert_order("SELL", target_price, reason, "LONG")


            # ==================================================================
            # 模块二：空单策略逻辑 (GrabTop)
            # ==================================================================

            # 2.1 处理空单订单状态
            if self.short_order:
                if self.short_order.is_error:
                    self.output("[空单] 订单错单", self.short_order.last_msg)
                    self.short_order = None 

                elif self.short_order.status == "FINISHED":
                    trade_price = self.short_order.trade_price
                    direction = self.short_order.direction
                    
                    self.output(f"【空单成交】 {direction} @ {trade_price}")

                    if direction == "SELL": # 开空成功
                        if self.short_pos_list:
                             self.short_pos_list[-1] = trade_price
                             self.short_pos_list.sort() 
                        if self.short_stack:
                            self.short_stack.pop()
                            self.short_stack.append((trade_price, "S"))

                    elif direction == "BUY": # 平空成功
                        if self.short_pos_list:
                            self.short_pos_list.pop()
                            self.short_pos_list.sort()
                        if self.short_stack:
                            self.short_stack.pop()
                            self.short_stack.append((trade_price, "B"))

                    self.output("空单持仓详情", self.short_pos_list)
                    self.short_order = None
                    self.save_list(self.short_pos_list, self.file_short_pos)
                    self.log_separator()

            # 2.2 空单状态同步 (仅在无活跃订单时)
            if self.short_order is None:
                real_pos_short = self.position.pos_short
                short_changed = False 

                # A. 实际空单变少 -> 平仓修正
                while len(self.short_pos_list) > real_pos_short:
                    self.short_pos_list.pop()
                    self.output("[空单] 检测到外部平仓，移除尾部持仓")
                    short_changed = True
                
                # B. 实际空单变多 -> 开仓补录
                while len(self.short_pos_list) < real_pos_short:
                    self.short_pos_list.append(last_price)
                    self.output(f"[空单] 检测到外部开仓，补录价格: {last_price}")
                    short_changed = True
                
                if short_changed:
                    self.short_pos_list.sort()
                    self.output("同步后的空单持仓", self.short_pos_list)

                # 2.3 空单策略信号逻辑
                if last_price < ma_price:
                    # A. 绝对初始建仓
                    if (not self.short_pos_list) or (real_pos_short < self.min_short_position):
                        target_price = last_price - tick
                        self.short_pos_list.append(target_price)
                        self.short_pos_list.sort()
                        self.short_stack.append((target_price, "S"))
                        
                        self.short_order = self.insert_order("SELL", target_price, "初始建仓 (空)", "SHORT")

                    # B. 网格加仓 (Price rise)
                    else:
                        idx = len(self.short_pos_list) - 1
                        step_idx = idx if idx < len(self.copy_top_step) else -1
                        step = self.copy_top_step[step_idx]

                        top_price = self.short_pos_list[-1]
                        if (last_price - top_price) >= step:
                            target_price = last_price - tick
                            self.short_pos_list.append(target_price)
                            self.short_pos_list.sort()
                            self.short_stack.append((target_price, "S"))
                            
                            reason = f"网格加仓 (现价{last_price} - 最高{top_price} >= 步长{step})"
                            self.short_order = self.insert_order("SELL", target_price, reason, "SHORT")

                # C. 摸底平仓 (止盈)
                if self.short_pos_list and self.short_order is None:
                    dynamic_step = last_price * 0.01 
                    max_pos_price = self.short_pos_list[-1]
                    step_threshold = len(self.short_pos_list) * self.touch_bom_step
                    
                    is_profit_1 = (max_pos_price - last_price) >= dynamic_step
                    is_profit_2 = (max_pos_price - last_price) >= step_threshold
                    
                    if is_profit_1 or is_profit_2:
                        target_price = last_price + tick
                        self.short_stack.append((target_price, "B"))
                        
                        trigger = "动态百分比" if is_profit_1 else f"阶梯阈值({step_threshold})"
                        reason = f"摸底止盈 [{trigger}] (最高{max_pos_price} - 现价{last_price})"
                        self.short_order = self.insert_order("BUY", target_price, reason, "SHORT")

if __name__ == "__main__":
    # 示例：现在切换合约会自动生成区分多空的文件
    SYMBOL = "SHFE.rb2605"
    
    try:
        api = TqApi(
            account=TqSim(init_balance=100000),
            backtest=TqBacktest(start_dt=date(2025, 8, 1), end_dt=date(2025, 12, 5)),
            web_gui=True,
            auth=TqAuth("cadofa", "cadofa6688"),
            debug=False
        )
        
        strategy = GrabBottomTop_Dual_TqSdk(api, SYMBOL)
        strategy.run()

    except BacktestFinished:   
        # 死循环保持进程活跃，使 Web GUI 继续提供服务
        while True:
            api.wait_update()
    except KeyboardInterrupt:
        print("\n用户手动停止")
    except Exception as e:
        print(f"\n程序运行报错: {e}")
    finally:
        # 兜底保存，防止非回测结束的异常退出导致数据丢失
        if 'strategy' in locals():
            strategy.on_stop()