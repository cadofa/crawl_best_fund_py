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
ATR_WINDOW = 20                 # ATR周期
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

    # 预加载数据，确保8月1日有足够的历史数据计算指标
    klines = api.get_kline_serial(SYMBOL, 24 * 60 * 60, data_length=100)
    
    target_pos = TargetPosTask(api, SYMBOL)
    quote = api.get_quote(SYMBOL)
    account = api.get_account()
    
    # 【修复点1】获取持仓对象引用
    position = api.get_position(SYMBOL)

    stop_loss_price = 0.0
    take_profit_price = 0.0
    has_stopped_out_today = False 

    try:
        while True:
            api.wait_update()

            # 1. 每日开盘信号逻辑
            if api.is_changing(klines.iloc[-1], "datetime"):
                current_k_time = klines.iloc[-1].datetime
                current_k_str = pd.to_datetime(current_k_time, unit='ns')
                
                # 重置日内风控标志
                has_stopped_out_today = False
                
                df = klines.copy()
                df = get_atr(df, ATR_WINDOW)
                df = get_cog(df)

                # 检查昨天的ATR是否计算完成
                if np.isnan(df['atr'].iloc[-2]):
                    print(f"[{current_k_str}] 历史数据不足，跳过...")
                    continue

                cog_yesterday = df['cog'].iloc[-2]
                cog_before = df['cog'].iloc[-3]
                atr_val = df['atr'].iloc[-2]
                current_open = df['open'].iloc[-1]

                print(f"[{current_k_str}] 开盘:{current_open} | ATR:{atr_val:.1f} | 昨COG:{cog_yesterday:.2f} vs 前COG:{cog_before:.2f}")

                # 交易逻辑
                if cog_yesterday < cog_before:
                    target_pos.set_target_volume(-VOL)
                    stop_loss_price = current_open + 1.0 * atr_val
                    take_profit_price = current_open - 2.0 * atr_val
                    print(f"  >>> 信号触发: 做空 (止损:{stop_loss_price:.1f}, 止盈:{take_profit_price:.1f})")
                else:
                    target_pos.set_target_volume(VOL)
                    stop_loss_price = current_open - 1.0 * atr_val
                    take_profit_price = current_open + 2.0 * atr_val
                    print(f"  >>> 信号触发: 做多 (止损:{stop_loss_price:.1f}, 止盈:{take_profit_price:.1f})")

            # 2. 盘中实时风控
            # 【修复点2】使用 position.pos 判断当前实际持仓
            # position.pos > 0 表示多单，< 0 表示空单，0 表示无持仓
            if position.pos != 0 and not has_stopped_out_today:
                current_price = quote.last_price
                current_vol = position.pos # 获取当前实际净持仓手数

                if current_price and current_price > 0:
                    # 多单风控
                    if current_vol > 0:
                        if current_price <= stop_loss_price:
                            print(f"  [多单止损] 价格 {current_price} 触及止损线 {stop_loss_price:.1f}")
                            target_pos.set_target_volume(0)
                            has_stopped_out_today = True
                        elif current_price >= take_profit_price:
                            print(f"  [多单止盈] 价格 {current_price} 触及止盈线 {take_profit_price:.1f}")
                            target_pos.set_target_volume(0)
                            has_stopped_out_today = True
                    # 空单风控
                    elif current_vol < 0:
                        if current_price >= stop_loss_price:
                            print(f"  [空单止损] 价格 {current_price} 触及止损线 {stop_loss_price:.1f}")
                            target_pos.set_target_volume(0)
                            has_stopped_out_today = True
                        elif current_price <= take_profit_price:
                            print(f"  [空单止盈] 价格 {current_price} 触及止盈线 {take_profit_price:.1f}")
                            target_pos.set_target_volume(0)
                            has_stopped_out_today = True

    except Exception as e:
        print(f"\n程序运行结束: {e}")
    finally:
        if 'strategy' in locals():
            strategy.on_stop()

if __name__ == "__main__":
    run_backtest()