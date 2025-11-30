from tqsdk import TqApi, TqAuth, TargetPosTask, TqSim, TqBacktest
from tqsdk.ta import ATR
from datetime import date
import pandas as pd
import numpy as np

# ================= 配置区域 =================
SYMBOL = "SHFE.rb2601"   # 合约代码
# 斐波那契周期权重配置
WEIGHTS = {
    3: 0.10,
    5: 0.15,
    8: 0.15,
    13: 0.15,
    21: 0.20,
    34: 0.25
}

# 阈值配置
OPEN_THRESHOLD = 0.6 
VOL = 1               
ATR_MULTIPLIER = 1.0  

# ================= 核心工具函数 =================

def to_scalar(val):
    """
    通用辅助函数：将 Series/Numpy/List 类型的单值强制转换为 python float
    """
    try:
        # 如果是 Pandas Series，取第一个值
        if isinstance(val, pd.Series):
            if val.empty: return 0.0
            val = val.iloc[0]
        
        # 如果是 Numpy 类型，取 item
        if hasattr(val, "item"):
            val = val.item()
            
        return float(val)
    except:
        return 0.0

def resample_klines(df_daily, days):
    """
    将日线数据重采样为 N日线数据
    修复点：使用 to_scalar 确保提取的是纯数字
    """
    if len(df_daily) < days:
        return None
    
    # 取最近N天的数据
    recent_df = df_daily.iloc[-days:]
    
    if recent_df.empty:
        return None

    # 合成逻辑
    try:
        n_day_bar = {
            'open': to_scalar(recent_df.iloc[0]['open']),
            'high': to_scalar(recent_df['high'].max()),
            'low': to_scalar(recent_df['low'].min()),
            'close': to_scalar(recent_df.iloc[-1]['close']),
            'days': days
        }
        return n_day_bar
    except Exception as e:
        print(f"数据合成出错: {e}")
        return None

def calculate_price_action_score(bar_data):
    """
    基于量化价格行为(Price Action)的评分模型
    """
    if bar_data is None:
        return 0
    
    o, h, l, c = bar_data['open'], bar_data['high'], bar_data['low'], bar_data['close']
    
    total_range = h - l
    
    if total_range <= 0:
        return 0
    
    # --- 1. 实体动能 ---
    body_score = (c - o) / total_range
    
    # --- 2. 影线博弈 ---
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    wick_score = (lower_shadow - upper_shadow) / total_range
    
    # --- 3. 收盘位置 ---
    position_ratio = (c - l) / total_range
    position_score = (position_ratio - 0.5) * 2
    
    # --- 4. 综合加权 ---
    final_score = (0.5 * body_score) + (0.3 * position_score) + (0.2 * wick_score)
    
    return max(min(final_score, 1.0), -1.0)

def analyze_morphology(bar_data):
    return calculate_price_action_score(bar_data)

def get_current_atr(klines, period=14):
    """
    获取最新ATR
    修复点：严格处理 Series 类型歧义
    """
    atr_serial = ATR(klines, period)
    if len(atr_serial) == 0:
        return 0.0
    
    # 获取最后一个值
    val = atr_serial.iloc[-1]
    
    # 转换为标量
    scalar_val = to_scalar(val)
    
    # 检查 NaN
    if np.isnan(scalar_val):
        return 0.0
        
    return scalar_val

# ================= 主程序逻辑 =================

try:
    # 初始化API
    api = TqApi(
        account=TqSim(init_balance=20000),
        backtest=TqBacktest(start_dt=date(2025, 8, 15), end_dt=date(2025, 11, 29)),
        web_gui=True,
        auth=TqAuth("cadofa", "cadofa6688"), # 请替换为真实的 TQ_USER, TQ_PASS
        debug=False
    )
    print(f"策略已启动，监控合约: {SYMBOL}")
    print("正在预加载数据...")

    # 获取日线数据
    klines = api.get_kline_serial(SYMBOL, 24 * 60 * 60, data_length=200)
    quote = api.get_quote(SYMBOL)
    target_pos = TargetPosTask(api, SYMBOL)

    # 交易状态变量
    position_state = 0  
    extreme_price = 0.0 
    entry_atr = 0.0     

    while True:
        api.wait_update()

        # -----------------------------------------------------
        # 1. 信号判定逻辑
        # -----------------------------------------------------
        if api.is_changing(klines.iloc[-1], "datetime"):
            # 确保 datetime 存在再打印
            dt_val = klines.iloc[-1]['datetime']
            if np.isnan(dt_val):
                continue
            
            print(f"\n====== 新日线生成: {pd.to_datetime(dt_val, unit='ns').date()} ======")
            
            # 直接引用 DataFrame
            df = klines 
            
            total_weighted_score = 0
            
            print("周期分析详情:")
            for days, weight in WEIGHTS.items():
                # 1. 动态合成N日K线
                n_bar = resample_klines(df, days)
                
                # 2. 调用核心算法评分
                score = analyze_morphology(n_bar)
                
                # 3. 加权累加
                weighted_val = score * weight
                total_weighted_score += weighted_val
                
                sentiment = "看涨" if score > 0.1 else ("看跌" if score < -0.1 else "震荡")
                print(f"  [{days:02d}日线] 形态分: {score:+.2f} | 权重贡献: {weighted_val:+.2f} ({sentiment})")
            
            print(f"  >>> 综合预测总分: {total_weighted_score:+.2f} (阈值: +/-{OPEN_THRESHOLD})")
            
            current_atr = get_current_atr(klines)
            # 如果回测初期 ATR 为 0 或 NaN，给个默认保护值（例如当前价格的1%）
            if current_atr <= 0: 
                current_atr = to_scalar(quote.last_price) * 0.01 
            
            # --- 开仓/反手逻辑 ---
            if total_weighted_score > OPEN_THRESHOLD:
                if position_state != 1:
                    print(f"  [交易指令] 强力看涨信号 -> 开多单 (目标ATR: {current_atr:.1f})")
                    target_pos.set_target_volume(VOL)
                    position_state = 1
                    extreme_price = to_scalar(quote.last_price)
                    entry_atr = current_atr
                else:
                    print("  [持仓] 多单持有中，趋势延续")

            elif total_weighted_score < -OPEN_THRESHOLD:
                if position_state != -1:
                    print(f"  [交易指令] 强力看跌信号 -> 开空单 (目标ATR: {current_atr:.1f})")
                    target_pos.set_target_volume(-VOL)
                    position_state = -1
                    extreme_price = to_scalar(quote.last_price)
                    entry_atr = current_atr
                else:
                    print("  [持仓] 空单持有中，趋势延续")
            
            else:
                print("  [信号] 震荡区间，无新开仓信号")

        # -----------------------------------------------------
        # 2. 盘中风控
        # -----------------------------------------------------
        if position_state != 0:
            last_price = to_scalar(quote.last_price)
            
            # 如果价格无效（如NaN），跳过本次风控
            if np.isnan(last_price) or last_price == 0:
                continue
                
            stop_gap = ATR_MULTIPLIER * entry_atr
            
            if position_state == 1: # 多单
                if last_price > extreme_price:
                    extreme_price = last_price
                
                stop_price = extreme_price - stop_gap
                
                if last_price <= stop_price:
                    print(f"[风控触发] 多单平仓 | 现价:{last_price} <= 止损线:{stop_price:.1f} (最高:{extreme_price})")
                    target_pos.set_target_volume(0)
                    position_state = 0
            
            elif position_state == -1: # 空单
                if last_price < extreme_price:
                    extreme_price = last_price
                
                stop_price = extreme_price + stop_gap
                
                if last_price >= stop_price:
                    print(f"[风控触发] 空单平仓 | 现价:{last_price} >= 止损线:{stop_price:.1f} (最低:{extreme_price})")
                    target_pos.set_target_volume(0)
                    position_state = 0

except Exception as e:
    import traceback
    print("策略异常退出:")
    traceback.print_exc()
finally:
    api.close()