from datetime import date
from tqsdk import TqApi, TqAuth, TqSim, TqBacktest
from tqsdk.ta import MA
import time, math

# 创建API连接
api =  TqApi(account=TqSim(init_balance=100000),
             backtest=TqBacktest(start_dt=date(2025, 1, 18), end_dt=date(2025, 11, 24)),
             web_gui=True, 
             auth=TqAuth("cadofa", "cadofa6688"),
             debug=False)

#symbol = "DCE.m2601"  
#symbol = "CZCE.FG601"
#symbol = "CZCE.SA601"
symbol = "CZCE.MA601"

# 获取行情数据
quote = api.get_quote(symbol)
klines = api.get_kline_serial(symbol, 60, data_length=100)
long_position_list = []
short_position_list = []
copy_bottom_step = [5,6,8,10,13,15,18,21,34,55,89,55,34,21,18,15,13,10]
touch_top_step = 6
copy_top_step = [5,6,8,10,13,15,18,21,34,55,89,55,34,21,18,15,13,10]
touch_bottom_step = 6

def get_ma3(symbol, Tapi):
    """
    获取最近3天的3日移动平均线值
    
    参数:
    symbol: 品种代码，默认为CFFEX.IF1903
    auth: 认证信息，格式为(账号, 密码)
    
    返回:
    包含最近3天3日移动平均线值的列表，从早到晚排列
    如果数据不足或计算失败返回None
    """
    k3dlines = Tapi.get_kline_serial(symbol, 24 * 60 * 60, data_length=8)
        
    # 计算N日移动平均线
    ma = MA(k3dlines, 3)
        
    # 获取MA值列表
    ma_list = list(ma["ma"])
        
    # 返回最近3天的MA值
    return ma_list[-3:]


def print_latest_price():
    latest_price = quote.last_price
    print(f"最新价格: {latest_price}", end=" | ")
    print(f"MA60: {ma_60:.2f}")
    print(f"******"*18)
    print()

def open_long_position():
    order = api.insert_order(symbol=symbol, direction="BUY", offset="OPEN", volume=1)
    print("多单开仓OPEN订单已提交")

    # 等待订单成交
    while order.status == "ALIVE":
        api.wait_update()
        #print(f"订单状态: {order.status}")

    # 检查最终状态
    if order.status == "FINISHED" and (not math.isnan(order.trade_price)):
        print("✅ 多单建仓OPEN成功!")
        if not math.isnan(order.trade_price):
            long_position_list.append(order.trade_price)
        position = api.get_position(symbol)
        print(f"持仓: 多单{position.pos_long}手, 持仓列表{long_position_list}")
    else:
        print(f"❌ 订单异常: {order.status}")
    print_latest_price()

def close_long():
    order = api.insert_order(symbol=symbol, direction="SELL", offset="CLOSE", volume=1)
    print("多单平仓CLOSE订单已提交")
    
    # 等待订单成交
    while order.status == "ALIVE":
        api.wait_update()
    
    if order.status == "FINISHED" and (not math.isnan(order.trade_price)):
        print("✅ 多单平仓CLOSE成功")
        long_position_list.remove(long_position_list[-1])
        position = api.get_position(symbol)
        print(f"持仓: 多单{position.pos_long}手, 持仓列表{long_position_list}")
    else:
        print(f"平仓失败，订单状态: {order.status}")
    print_latest_price()

def open_short_position():
    order = api.insert_order(symbol=symbol, direction="SELL", offset="OPEN", volume=1)
    print("空单开仓OPEN订单已提交")

    # 等待订单成交
    while order.status == "ALIVE":
        api.wait_update()
        #print(f"订单状态: {order.status}")

    # 检查最终状态
    if order.status == "FINISHED" and (not math.isnan(order.trade_price)):
        print("✅ 空单建仓OPEN成功!")    
        short_position_list.append(order.trade_price)
        position = api.get_position(symbol)
        print(f"持仓: 空单{position.pos_short}手, 持仓列表{short_position_list}")
    else:
        print(f"❌ 订单异常: {order.status}")
    print_latest_price()

def close_short():
    order = api.insert_order(symbol=symbol, direction="BUY", offset="CLOSE", volume=1)
    print("空单平仓CLOSE订单已提交")
    
    # 等待订单成交
    while order.status == "ALIVE":
        api.wait_update()
    
    if order.status == "FINISHED" and (not math.isnan(order.trade_price)):
        print("✅ 空单平仓CLOSE成功")
        short_position_list.remove(short_position_list[-1])
        position = api.get_position(symbol)
        print(f"持仓: 空单{position.pos_short}手, 持仓列表{short_position_list}")
    else:
        print(f"平仓失败，订单状态: {order.status}")
    print_latest_price()

try:
    while True:
        api.wait_update()  # 等待数据更新

        ma3_list = get_ma3(symbol, api)

        # 获取最新价格
        if quote.datetime != 0:
            latest_price = quote.last_price
            #print(f"最新价格: {latest_price}", end=" | ")
        
        # 计算60周期均线
        if len(klines) >= 60:
            ma_60 = klines.close.iloc[-60:].mean()
            #print(f"MA60: {ma_60:.2f}")
        else:
            print(f"K线数量: {len(klines)}/60，均线计算中...")
        
        position = api.get_position(symbol)
        #多单建仓
        if (quote.last_price > ma_60) and (ma3_list[-1] > ma3_list[-2]):
            if not long_position_list:
                open_long_position()

            if long_position_list:
                last_index = long_position_list.index(long_position_list[-1])
                if (long_position_list[-1] - quote.last_price) >= copy_bottom_step[last_index]:
                    open_long_position()
        #多单平仓 
        if long_position_list:
            dynamic_step = len(long_position_list) * touch_top_step
            if (quote.last_price - long_position_list[-1]) >= dynamic_step:
                close_long()

        #空单建仓
        if (quote.last_price < ma_60) and (ma3_list[-1] < ma3_list[-2]):
            if not short_position_list:
                open_short_position()

            if short_position_list:
                last_index = short_position_list.index(short_position_list[-1])
                if (quote.last_price - short_position_list[-1]) >= copy_top_step[last_index]:
                    open_short_position()
        #空单平仓
        if short_position_list:
            dynamic_step = dynamic_step = len(short_position_list) * touch_bottom_step
            if (short_position_list[-1] - quote.last_price) >= dynamic_step:
                close_short()
            
        #time.sleep(1)
except KeyboardInterrupt:
    print("\n程序结束")

finally:
    api.close()