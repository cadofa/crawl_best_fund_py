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
# 1. 斐波那契趋势分析器 (保持不变)
# ==============================================================================
class FibonacciTrendAnalyzer:
    def __init__(self, api, symbol):
        self.api = api
        self.symbol = symbol
        self.quote = api.get_quote(symbol)
        
        self.klines_1h = api.get_kline_serial(symbol, duration_seconds=3600, data_length=300)
        self.periods = [233, 144, 89, 55, 34, 21]
        self.weights = {233: 30, 144: 20, 89: 15, 55: 15, 34: 10, 21: 10}
        self.threshold = 15

    def get_trend(self):
        if self.klines_1h is None or len(self.klines_1h) < 235:
            return 0
        current_price = self.quote.last_price
        if pd.isna(current_price): return 0

        total_score = 0
        for p in self.periods:
            ma_val = MA(self.klines_1h, p).ma.iloc[-1]
            if pd.isna(ma_val): continue
            if current_price > ma_val: total_score += self.weights[p]
            else: total_score -= self.weights[p]
        
        if total_score > self.threshold: return 1
        elif total_score < -self.threshold: return -1
        else: return 0

# ==============================================================================
# 2. 基础策略类 (增加移动止盈保护逻辑)
# ==============================================================================
class BaseGridStrategy:
    def __init__(self, api, symbol, direction):
        self.api = api
        self.symbol = symbol
        self.direction = direction 
        self.quote = api.get_quote(symbol)
        self.position = api.get_position(symbol)
        self.account = api.get_account()
        
        self.klines_atr = api.get_kline_serial(symbol, 3600, data_length=50)
        
        self.pos_list = []      
        self.avg_cost = 0.0     
        
        # [优化] 增加最高/最低价记录，用于移动止盈
        self.highest_price = 0.0 # 多单持仓期间最高价
        self.lowest_price = 0.0  # 空单持仓期间最低价
        
        safe_sym = symbol.replace('.', '_')
        self.file_path = f"Fibo_{direction}_{safe_sym}.json"
        self._load()

    def get_atr(self):
        atr = ATR(self.klines_atr, 20).atr.iloc[-1]
        return 30.0 if (pd.isna(atr) or atr == 0) else atr

    def update_cost(self):
        if not self.pos_list: 
            self.avg_cost = 0.0
            self.highest_price = 0.0
            self.lowest_price = float('inf')
        else: 
            self.avg_cost = sum(self.pos_list) / len(self.pos_list)
            # 开仓/加仓时重置极值，避免旧数据干扰
            if self.direction == "LONG":
                self.highest_price = self.quote.last_price
            else:
                self.lowest_price = self.quote.last_price

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

    # --- 风控检查 ---
    def check_risk(self, price):
        balance = self.account.balance
        current_margin = self.account.margin
        if balance <= 0: return False

        one_lot_margin = self.quote.margin
        if math.isnan(one_lot_margin) or one_lot_margin == 0:
            volume_multiple = self.quote.volume_multiple
            if math.isnan(volume_multiple) or volume_multiple == 0: volume_multiple = 10 
            one_lot_margin = price * volume_multiple * 0.13

        risk_ratio = (current_margin + one_lot_margin) / balance
        if risk_ratio > 0.35:
            if len(self.pos_list) > 0:
                print(f"[{self.direction}] 风控拦截! 预计风险: {risk_ratio*100:.2f}%")
            return False
        return True

    # --- [核心优化] 移动止盈与硬止损检查 ---
    def check_trailing_and_stop(self, price):
        if not self.pos_list or self.avg_cost == 0: return False
        
        atr = self.get_atr()
        
        # 1. 硬止损 (防止亏损无限扩大)
        # [优化] 保持 2.5 ATR 不变，这是最后的防线
        HARD_STOP = 2.5 * atr
        
        # 2. 移动止盈参数
        # 当盈利超过 ACTIVATION_LEVEL (1.0 ATR) 时，启动保护
        # 如果回撤超过 CALLBACK (0.4 ATR)，则止盈
        ACTIVATION_LEVEL = 1.0 * atr 
        CALLBACK = 0.4 * atr

        if self.direction == "LONG":
            # 更新最高价
            self.highest_price = max(self.highest_price, price)
            
            # A. 硬止损
            if price < (self.avg_cost - HARD_STOP):
                print(f"[Long] 🛑 硬止损触发: 现价{price} < 均价{self.avg_cost:.1f}-2.5ATR")
                self.close_all(force=True)
                return True
                
            # B. 移动止盈
            profit = self.highest_price - self.avg_cost
            if profit > ACTIVATION_LEVEL:
                # 如果从最高点回撤超过回调阈值
                if price < (self.highest_price - CALLBACK):
                    print(f"[Long] 🛡️ 移动止盈: 最高{self.highest_price} 回撤 > {CALLBACK:.1f}")
                    self.close_all(force=False)
                    return True

        else: # SHORT
            # 更新最低价
            self.lowest_price = min(self.lowest_price, price)
            
            # A. 硬止损
            if price > (self.avg_cost + HARD_STOP):
                print(f"[Short] 🛑 硬止损触发: 现价{price} > 均价{self.avg_cost:.1f}+2.5ATR")
                self.close_all(force=True)
                return True
            
            # B. 移动止盈
            profit = self.avg_cost - self.lowest_price
            if profit > ACTIVATION_LEVEL:
                if price > (self.lowest_price + CALLBACK):
                    print(f"[Short] 🛡️ 移动止盈: 最低{self.lowest_price} 反弹 > {CALLBACK:.1f}")
                    self.close_all(force=False)
                    return True
                    
        return False

    def close_all(self, force=False):
        """平仓逻辑 (SHFE修复版)"""
        vol = self.position.pos_long if self.direction == "LONG" else self.position.pos_short
        if vol > 0:
            msg = "趋势反转/止损" if force else "止盈出场"
            print(f"[{self.direction}] {msg} | 手数: {vol} | 均价: {self.avg_cost:.1f}")
            
            dir_order = "SELL" if self.direction == "LONG" else "BUY"
            price = self.quote.bid_price1 if self.direction == "LONG" else self.quote.ask_price1
            
            exchange = self.symbol.split('.')[0]
            if exchange in ["SHFE", "INE"]:
                if self.direction == "LONG":
                    his_vol = self.position.pos_long_his
                else:
                    his_vol = self.position.pos_short_his
                
                close_his = min(vol, his_vol)
                close_today = vol - close_his
                if close_his > 0:
                    self.api.insert_order(self.symbol, dir_order, "CLOSE", close_his, price)
                if close_today > 0:
                    self.api.insert_order(self.symbol, dir_order, "CLOSETODAY", close_today, price)
            else:
                self.api.insert_order(self.symbol, dir_order, "CLOSE", vol, price)
            
        self.pos_list = []
        self.avg_cost = 0.0
        self.highest_price = 0.0
        self.lowest_price = float('inf')
        self._save()

# ==============================================================================
# 3. 斐波那契做多网格 (Long Strategy)
# ==============================================================================
class StrategyFiboLong(BaseGridStrategy):
    def __init__(self, api, symbol):
        super().__init__(api, symbol, "LONG")
        
    def on_tick(self):
        price = self.quote.last_price
        if pd.isna(price): return
        
        # 1. 优先检查止损/移动止盈
        if self.check_trailing_and_stop(price):
            return
        
        atr = self.get_atr()
        
        # [优化] 扩大网格间距，减少在震荡中频繁加仓
        # 从 0.6 ATR 增加到 1.2 ATR
        grid_step = 1.2 * atr 
        
        # --- 建仓/加仓 ---
        do_buy = False
        real_pos_long = self.position.pos_long

        if not self.pos_list:
            if real_pos_long == 0: do_buy = True
            else:
                self.pos_list.append(price)
                self.update_cost()
        else:
            if price < (self.pos_list[-1] - grid_step):
                # 限制最大持仓4手
                if real_pos_long < 4: 
                    do_buy = True
        
        if do_buy:
            if self.position.pos_long >= 4: return
            if self.check_risk(price):
                self.api.insert_order(self.symbol, "BUY", "OPEN", 1, self.quote.ask_price1)
                self.pos_list.append(price)
                self.update_cost()
                self._save()
                print(f"[Long] 开仓/补仓 | 价格:{price} | 间距:{grid_step:.1f}")
            return

        # --- 基础均价止盈 ---
        # [优化] 提高基础止盈目标，改善盈亏比
        # 目标：均价 + 1.6 ATR (原 1.0)
        if self.pos_list and self.avg_cost > 0:
            target = self.avg_cost + 1.6 * atr
            if price > target:
                print(f"[Long] 🎯 目标止盈, 现价{price} > 目标{target:.1f}")
                self.close_all(force=False)

# ==============================================================================
# 4. 斐波那契做空网格 (Short Strategy)
# ==============================================================================
class StrategyFiboShort(BaseGridStrategy):
    def __init__(self, api, symbol):
        super().__init__(api, symbol, "SHORT")
        
    def on_tick(self):
        price = self.quote.last_price
        if pd.isna(price): return
        
        # 1. 优先检查止损/移动止盈
        if self.check_trailing_and_stop(price):
            return
        
        atr = self.get_atr()
        # [优化] 扩大网格间距
        grid_step = 1.2 * atr
        
        # --- 建仓/加仓 ---
        do_sell = False
        real_pos_short = self.position.pos_short

        if not self.pos_list:
            if real_pos_short == 0: do_sell = True
            else:
                self.pos_list.append(price)
                self.update_cost()
        else:
            if price > (self.pos_list[-1] + grid_step):
                if real_pos_short < 4:
                    do_sell = True
        
        if do_sell:
            if self.position.pos_short >= 4: return
            if self.check_risk(price):
                self.api.insert_order(self.symbol, "SELL", "OPEN", 1, self.quote.bid_price1)
                self.pos_list.append(price)
                self.update_cost()
                self._save()
                print(f"[Short] 开仓/补仓 | 价格:{price} | 间距:{grid_step:.1f}")
            return

        # --- 基础均价止盈 ---
        # [优化] 提高基础止盈目标
        if self.pos_list and self.avg_cost > 0:
            target = self.avg_cost - 1.6 * atr
            if price < target:
                print(f"[Short] 🎯 目标止盈, 现价{price} < 目标{target:.1f}")
                self.close_all(force=False)

# ==============================================================================
# 5. 主程序入口
# ==============================================================================
if __name__ == "__main__":
    SYMBOL = "SHFE.rb2601"
    
    api = TqApi(
        account=TqSim(init_balance=50000),
        backtest=TqBacktest(start_dt=date(2025, 8, 15), end_dt=date(2025, 11, 29)),
        web_gui=True,
        auth=TqAuth("cadofa", "cadofa6688"), 
        debug=False
    )
    
    print(f">>> 策略启动: 斐波那契网格 Pro | 合约: {SYMBOL}")
    print(">>> 优化: 间距1.2ATR | 止盈1.6ATR | 增加移动止盈保护 | 限仓4手")
    
    analyzer = FibonacciTrendAnalyzer(api, SYMBOL)
    stg_long = StrategyFiboLong(api, SYMBOL)
    stg_short = StrategyFiboShort(api, SYMBOL)
    
    current_trend = 0 
    
    try:
        while api.wait_update():
            new_trend = analyzer.get_trend()
            
            if new_trend != 0 and new_trend != current_trend:
                print(f"\n======== [趋势切换] {current_trend} -> {new_trend} ========")
                
                if new_trend == 1:
                    print(">>> 判定: 多头排列")
                    stg_short.close_all(force=True)
                
                elif new_trend == -1:
                    print(">>> 判定: 空头排列")
                    stg_long.close_all(force=True)
                    
                current_trend = new_trend
            
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