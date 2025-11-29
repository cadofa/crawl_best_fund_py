# encoding: UTF-8

import os
import json
import math
import pandas as pd
import numpy as np
from datetime import date
from tqsdk import TqApi, TqAuth, TqSim, TqBacktest
from tqsdk.ta import MA, ATR

# ==============================================================================
# 1. 斐波那契趋势分析器 (Fibonacci Trend Analyzer)
#    (逻辑保持不变)
# ==============================================================================
class FibonacciTrendAnalyzer:
    def __init__(self, api, symbol):
        self.api = api
        self.symbol = symbol
        self.quote = api.get_quote(symbol)
        
        # 订阅 1小时 K线
        self.klines_1h = api.get_kline_serial(symbol, duration_seconds=3600, data_length=300)
        
        # 斐波那契周期
        self.periods = [233, 144, 89, 55, 34, 21]
        
        # 权重分配
        self.weights = {
            233: 30,
            144: 20,
            89:  15,
            55:  15,
            34:  10,
            21:  10
        }
        
        # 判定阈值
        self.threshold = 15

    def get_trend(self):
        # 数据预热检查
        if self.klines_1h is None or len(self.klines_1h) < 235:
            return 0
        
        current_price = self.quote.last_price
        if pd.isna(current_price): return 0

        total_score = 0
        
        for p in self.periods:
            ma_val = MA(self.klines_1h, p).ma.iloc[-1]
            weight = self.weights[p]
            
            if pd.isna(ma_val): continue
            
            if current_price > ma_val:
                total_score += weight
            else:
                total_score -= weight
        
        if total_score > self.threshold:
            return 1
        elif total_score < -self.threshold:
            return -1
        else:
            return 0

# ==============================================================================
# 2. 基础策略类 (保持不变)
# ==============================================================================
class BaseGridStrategy:
    def __init__(self, api, symbol, direction):
        self.api = api
        self.symbol = symbol
        self.direction = direction # "LONG" or "SHORT"
        self.quote = api.get_quote(symbol)
        self.position = api.get_position(symbol)
        
        # 使用1小时线计算ATR
        self.klines_atr = api.get_kline_serial(symbol, 3600, data_length=50)
        
        self.pos_list = []      # 开仓价格列表
        self.avg_cost = 0.0     # 持仓均价
        
        # 文件名防止冲突
        safe_sym = symbol.replace('.', '_')
        self.file_path = f"Fibo_{direction}_{safe_sym}.json"
        self._load()

    def get_atr(self):
        atr = ATR(self.klines_atr, 20).atr.iloc[-1]
        return 30.0 if (pd.isna(atr) or atr == 0) else atr

    def update_cost(self):
        if not self.pos_list: self.avg_cost = 0.0
        else: self.avg_cost = sum(self.pos_list) / len(self.pos_list)

    def _load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r") as f:
                    self.pos_list = json.load(f)
                    self.update_cost()
            except: pass

    def _save(self):
        with open(self.file_path, "w") as f:
            json.dump(self.pos_list, f)

    def close_all(self, force=False):
        """平仓逻辑"""
        vol = self.position.pos_long if self.direction == "LONG" else self.position.pos_short
        if vol > 0:
            msg = "!!! 趋势反转强平" if force else ">>> 均价止盈"
            print(f"[{self.direction}] {msg} | 手数: {vol}")
            
            dir_order = "SELL" if self.direction == "LONG" else "BUY"
            price = self.quote.bid_price1 if self.direction == "LONG" else self.quote.ask_price1
            # 使用 CLOSE 平仓，实盘中 TqSdk 会自动处理平今平昨
            self.api.insert_order(self.symbol, dir_order, "CLOSE", vol, price)
            
        self.pos_list = []
        self.avg_cost = 0.0
        self._save()

# ==============================================================================
# 3. 斐波那契做多网格 (Long Strategy)
#    [修改]: 限制最大真实持仓 4 手
# ==============================================================================
class StrategyFiboLong(BaseGridStrategy):
    def __init__(self, api, symbol):
        super().__init__(api, symbol, "LONG")
        
    def on_tick(self):
        price = self.quote.last_price
        if pd.isna(price): return
        
        atr = self.get_atr()
        grid_step = 0.6 * atr 
        
        # --- 建仓/加仓 ---
        do_buy = False
        
        # 获取真实多头持仓量
        real_pos_long = self.position.pos_long

        if not self.pos_list:
            do_buy = True
        else:
            # 回调加仓
            if price < (self.pos_list[-1] - grid_step):
                # [修改点1] 使用真实持仓判断是否允许补仓
                if real_pos_long < 4: 
                    print(f"[Long] 回调补仓, 跌幅 {grid_step:.1f}")
                    do_buy = True
        
        if do_buy:
            # [修改点2] 硬性检查：如果当前真实持仓已经达到或超过4手，禁止开仓
            if self.position.pos_long >= 4:
                # print(f"[Long] 真实持仓已达 {self.position.pos_long} 手，停止开仓")
                return

            self.api.insert_order(self.symbol, "BUY", "OPEN", 1, self.quote.ask_price1)
            self.pos_list.append(price)
            self.update_cost()
            self._save()
            return

        # --- 均价止盈 ---
        if self.pos_list and self.avg_cost > 0:
            target = self.avg_cost + 1.0 * atr
            if price > target:
                print(f"[Long] 触发止盈, 现价{price} > 均价{self.avg_cost:.1f}")
                self.close_all(force=False)

# ==============================================================================
# 4. 斐波那契做空网格 (Short Strategy)
#    [修改]: 限制最大真实持仓 4 手
# ==============================================================================
class StrategyFiboShort(BaseGridStrategy):
    def __init__(self, api, symbol):
        super().__init__(api, symbol, "SHORT")
        
    def on_tick(self):
        price = self.quote.last_price
        if pd.isna(price): return
        
        atr = self.get_atr()
        grid_step = 0.6 * atr
        
        # --- 建仓/加仓 ---
        do_sell = False
        
        # 获取真实空头持仓量
        real_pos_short = self.position.pos_short

        if not self.pos_list:
            do_sell = True
        else:
            # 反弹加仓
            if price > (self.pos_list[-1] + grid_step):
                # [修改点1] 使用真实持仓判断是否允许补仓
                if real_pos_short < 4:
                    print(f"[Short] 反弹补仓, 涨幅 {grid_step:.1f}")
                    do_sell = True
        
        if do_sell:
            # [修改点2] 硬性检查：如果当前真实持仓已经达到或超过4手，禁止开仓
            if self.position.pos_short >= 4:
                # print(f"[Short] 真实持仓已达 {self.position.pos_short} 手，停止开仓")
                return

            self.api.insert_order(self.symbol, "SELL", "OPEN", 1, self.quote.bid_price1)
            self.pos_list.append(price)
            self.update_cost()
            self._save()
            return

        # --- 均价止盈 ---
        if self.pos_list and self.avg_cost > 0:
            target = self.avg_cost - 1.0 * atr
            if price < target:
                print(f"[Short] 触发止盈, 现价{price} < 均价{self.avg_cost:.1f}")
                self.close_all(force=False)

# ==============================================================================
# 5. 主程序入口
# ==============================================================================
if __name__ == "__main__":
    SYMBOL = "SHFE.rb2601"
    
    # 模拟回测设置
    api = TqApi(
        account=TqSim(init_balance=20000),
        # 建议测试具有明显趋势+震荡的完整周期
        backtest=TqBacktest(start_dt=date(2025, 8, 15), end_dt=date(2025, 11, 29)),
        web_gui=True,
        auth=TqAuth("cadofa", "cadofa6688"), # 请替换为你的账号
        debug=False
    )
    
    print(f">>> 策略启动: 斐波那契均线(1H)趋势网格 | 合约: {SYMBOL}")
    print(">>> 均线组: [233, 144, 89, 55, 34, 21]")
    print(">>> 限制: 单边最大真实持仓 4 手")
    
    # 初始化模块
    analyzer = FibonacciTrendAnalyzer(api, SYMBOL)
    stg_long = StrategyFiboLong(api, SYMBOL)
    stg_short = StrategyFiboShort(api, SYMBOL)
    
    current_trend = 0 # 0:震荡, 1:多, -1:空
    
    try:
        while api.wait_update():
            # 1. 计算斐波那契趋势得分
            new_trend = analyzer.get_trend()
            
            # 2. 状态切换逻辑
            if new_trend != 0 and new_trend != current_trend:
                print(f"\n======== [趋势切换] {current_trend} -> {new_trend} ========")
                
                if new_trend == 1:
                    print(">>> 判定: 多头排列 (MA21>...>MA233)")
                    # 强平空单，转为做多
                    stg_short.close_all(force=True)
                
                elif new_trend == -1:
                    print(">>> 判定: 空头排列 (MA21<...<MA233)")
                    # 强平多单，转为做空
                    stg_long.close_all(force=True)
                    
                current_trend = new_trend
            
            # 3. 策略执行
            if current_trend == 1:
                stg_long.on_tick()
            elif current_trend == -1:
                stg_short.on_tick()
            else:
                pass

    except KeyboardInterrupt:
        print("停止策略")
    finally:
        api.close()