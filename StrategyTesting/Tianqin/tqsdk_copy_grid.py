#!/usr/bin/env python
#  -*- coding: utf-8 -*-
__author__ = 'TqSdk Strategy'

from tqsdk import TqApi, TqAuth, TqSim, TargetPosTask, TqBacktest, BacktestFinished
from datetime import date
import pandas as pd
import numpy as np

# ================= 配置参数 =================
# 【注意】请填入你的天勤账户和密码
TQ_USER = "cadofa"
TQ_PASS = "cadofa6688"

SYMBOL = "SHFE.rb2601"          # 标的
START_DT = date(2025, 8, 1)     # 回测开始时间
END_DT = date(2025, 11, 29)     # 回测结束时间
ATR_WINDOW = 13                 # ATR周期
VOL = 1                         # 下单手数

def get_atr(df, n):
    """计算ATR指标"""
    df = df.copy()
    df['h-l'] = df['high'] - df['low']
    df['h-yc'] = abs(df['high'] - df['close'].shift(1))
    df['l-yc'] = abs(df['low'] - df['close'].shift(1))
    
    df['tr'] = df[['h-l', 'h-yc', 'l-yc']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=n).mean()
    return df

def get_cog(df):
    """计算K线重心"""
    df['cog'] = (3 * df['close'] + 2 * df['open'] + df['high'] + df['low']) / 7
    return df

def log_separator():
    """打印分隔符"""
    print("\n" + "=" * 60 + "\n")

def run_backtest():
    try:
        api = TqApi(
            account=TqSim(init_balance=20000),
            backtest=TqBacktest(start_dt=START_DT, end_dt=END_DT),
            auth=TqAuth(TQ_USER, TQ_PASS),
            web_gui=True
        )
    except Exception as e:
        print(f"初始化失败: {e}")
        return

    print(f"开始回测: {SYMBOL}")
    print(f"回测区间: {START_DT} -> {END_DT}")
    print("正在预加载历史数据以确保首日即可交易...")

    # 预加载数据
    klines = api.get_kline_serial(SYMBOL, 24 * 60 * 60, data_length=100)
    
    target_pos = TargetPosTask(api, SYMBOL)
    quote = api.get_quote(SYMBOL)
    account = api.get_account()
    position = api.get_position(SYMBOL)

    # 策略状态变量
    stop_loss_price = 0.0
    take_profit_price = 0.0
    entry_price = 0.0           # 记录开仓价格(成本价)
    has_stopped_out_today = False 
    is_breakeven_set = False    # 标记是否已触发保本

    try:
        while True:
            api.wait_update()

            # -----------------------------------------------------------------
            # 1. 每日开盘信号逻辑 (COG反转策略)
            # -----------------------------------------------------------------
            if api.is_changing(klines.iloc[-1], "datetime"):
                current_k_time = klines.iloc[-1].datetime
                current_k_str = pd.to_datetime(current_k_time, unit='ns')
                
                # 重置日内风控标志
                has_stopped_out_today = False
                is_breakeven_set = False
                
                df = klines.copy()
                df = get_atr(df, ATR_WINDOW)
                df = get_cog(df)

                if np.isnan(df['atr'].iloc[-2]):
                    continue

                cog_yesterday = df['cog'].iloc[-2]
                cog_before = df['cog'].iloc[-3]
                atr_val = df['atr'].iloc[-2]
                current_open = df['open'].iloc[-1]

                # 更新入场价
                entry_price = current_open

                # 交易逻辑：COG下降做空，COG上升做多
                if cog_yesterday < cog_before:
                    target_pos.set_target_volume(-VOL)
                    # 【优化1】初始止损扩大到 1.5 ATR
                    stop_loss_price = current_open + 1.5 * atr_val
                    take_profit_price = current_open - 3.0 * atr_val # 配合宽止损，适当放大止盈
                    
                    log_separator()
                    print(f"【交易信号】时间: {current_k_str}")
                    print(f"  动作: 开空/持有空单 (SHORT)")
                    print(f"  价格: {current_open}")
                    print(f"  止损: {stop_loss_price:.1f} (1.5 ATR)")
                    print(f"  止盈: {take_profit_price:.1f}")
                    
                else:
                    target_pos.set_target_volume(VOL)
                    # 【优化1】初始止损扩大到 1.5 ATR
                    stop_loss_price = current_open - 1.5 * atr_val
                    take_profit_price = current_open + 3.0 * atr_val
                    
                    log_separator()
                    print(f"【交易信号】时间: {current_k_str}")
                    print(f"  动作: 开多/持有多单 (LONG)")
                    print(f"  价格: {current_open}")
                    print(f"  止损: {stop_loss_price:.1f} (1.5 ATR)")
                    print(f"  止盈: {take_profit_price:.1f}")

            # -----------------------------------------------------------------
            # 2. 盘中实时风控
            # -----------------------------------------------------------------
            if position.pos != 0 and not has_stopped_out_today:
                current_price = quote.last_price
                current_vol = position.pos 

                if current_price and current_price > 0:
                    
                    # === 多单风控 ===
                    if current_vol > 0:
                        # 1. 硬止损 / 保本止损触发
                        if current_price <= stop_loss_price:
                            target_pos.set_target_volume(0)
                            has_stopped_out_today = True
                            
                            log_separator()
                            print(f"【平仓信号】触发多单止损/保本")
                            print(f"  成交价格: {current_price}")
                            print(f"  设定止损: {stop_loss_price:.1f}")
                            print(f"  账户权益: {account.balance:.2f}")
                            
                        # 2. 硬止盈
                        elif current_price >= take_profit_price:
                            target_pos.set_target_volume(0)
                            has_stopped_out_today = True
                            
                            log_separator()
                            print(f"【平仓信号】触发多单止盈")
                            print(f"  成交价格: {current_price}")
                            print(f"  账户权益: {account.balance:.2f}")
                        
                        # 【优化2】保本策略：浮盈 > 0.5 ATR，止损上移至成本价
                        elif not is_breakeven_set and (current_price - entry_price) > (0.5 * atr_val):
                            stop_loss_price = entry_price + 1 # 加1跳防止手续费亏损
                            is_breakeven_set = True
                            # 仅供调试，不想刷屏可注释
                            # print(f"  >>> [动态风控] 多单浮盈达标，止损上移至保本位: {stop_loss_price}")

                    # === 空单风控 ===
                    elif current_vol < 0:
                        # 1. 硬止损 / 保本止损触发
                        if current_price >= stop_loss_price:
                            target_pos.set_target_volume(0)
                            has_stopped_out_today = True
                            
                            log_separator()
                            print(f"【平仓信号】触发空单止损/保本")
                            print(f"  成交价格: {current_price}")
                            print(f"  设定止损: {stop_loss_price:.1f}")
                            print(f"  账户权益: {account.balance:.2f}")
                            
                        # 2. 硬止盈
                        elif current_price <= take_profit_price:
                            target_pos.set_target_volume(0)
                            has_stopped_out_today = True
                            
                            log_separator()
                            print(f"【平仓信号】触发空单止盈")
                            print(f"  成交价格: {current_price}")
                            print(f"  账户权益: {account.balance:.2f}")
                        
                        # 【优化2】保本策略：浮盈 > 0.5 ATR，止损下移至成本价
                        elif not is_breakeven_set and (entry_price - current_price) > (0.5 * atr_val):
                            stop_loss_price = entry_price - 1 # 减1跳防止手续费亏损
                            is_breakeven_set = True
                            # print(f"  >>> [动态风控] 空单浮盈达标，止损下移至保本位: {stop_loss_price}")

    except Exception as e:
        print(f"\n程序运行结束: {e}")
    finally:
        if 'strategy' in locals():
            strategy.on_stop()

if __name__ == "__main__":
    run_backtest()