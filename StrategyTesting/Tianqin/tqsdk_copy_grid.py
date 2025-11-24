from datetime import date
from tqsdk import TqApi, TqAuth, TqSim, TqBacktest
from tqsdk.ta import MA
import math

class GridStrategy:
    def __init__(self, symbol, api, config):
        self.symbol = symbol
        self.api = api
        self.config = config
        
        # 初始化数据序列 (TqSDK会自动更新这些序列)
        self.quote = api.get_quote(symbol)
        self.klines_1min = api.get_kline_serial(symbol, 60, data_length=100)
        self.klines_1day = api.get_kline_serial(symbol, 24 * 60 * 60, data_length=8)
        
        # 持仓价格列表
        self.long_pos_prices = []
        self.short_pos_prices = []

    def _get_ma3_trend(self):
        """计算日线MA3趋势，返回(当前值, 上一值)"""
        ma_data = MA(self.klines_1day, 3)
        ma_list = list(ma_data["ma"])
        # 确保数据足够
        if len(ma_list) < 3:
            return 0, 0
        return ma_list[-1], ma_list[-2]

    def _get_ma60(self):
        """计算1分钟线MA60"""
        if len(self.klines_1min) < 60:
            return None
        return self.klines_1min.close.iloc[-60:].mean()

    def _print_status(self, ma60):
        """打印当前行情状态"""
        price = self.quote.last_price
        ma60_str = f"{ma60:.2f}" if ma60 else "计算中"
        print(f"最新价格: {price} | MA60: {ma60_str}")
        print(f"******" * 18)
        print()

    def _execute_order(self, direction, offset, pos_list):
        """
        统一交易执行函数
        direction: "BUY" or "SELL" (对于持仓方向)
        offset: "OPEN" or "CLOSE"
        pos_list: 对应的持仓价格列表
        """
        # 确定实际下单指令方向
        # 如果是开仓：多单买入，空单卖出
        # 如果是平仓：多单卖出，空单买入
        if offset == "OPEN":
            order_dir = direction
            action_name = "多单" if direction == "BUY" else "空单"
        else:
            order_dir = "SELL" if direction == "BUY" else "BUY"
            action_name = "多单" if direction == "BUY" else "空单"

        act_type = "建仓OPEN" if offset == "OPEN" else "平仓CLOSE"
        print(f"{action_name}{act_type}订单已提交")

        # 提交订单
        order = self.api.insert_order(symbol=self.symbol, direction=order_dir, offset=offset, volume=1)

        # 等待成交
        while order.status == "ALIVE":
            self.api.wait_update()

        # 检查结果
        if order.status == "FINISHED" and not math.isnan(order.trade_price):
            print(f"✅ {action_name}{act_type}成功!")
            
            # 更新内存中的持仓列表
            if offset == "OPEN":
                pos_list.append(order.trade_price)
            else:
                if pos_list:
                    # LIFO: 移除最后进场的
                    pos_list.pop()

            # 打印持仓信息
            pos_info = self.api.get_position(self.symbol)
            pos_vol = pos_info.pos_long if direction == "BUY" else pos_info.pos_short
            print(f"持仓: {action_name}{pos_vol}手, 持仓列表{pos_list}")
            
            # 交易完成后打印行情
            self._print_status(self._get_ma60())
            return True
        else:
            print(f"❌ 订单异常: {order.status}")
            self._print_status(self._get_ma60())
            return False

    def run(self):
        try:
            while True:
                self.api.wait_update()

                # 1. 数据准备
                current_price = self.quote.last_price
                ma60 = self._get_ma60()
                ma3_curr, ma3_prev = self._get_ma3_trend()

                if ma60 is None or self.quote.datetime == 0:
                    print(f"K线数量: {len(self.klines_1min)}/60，初始化中...")
                    continue

                # 2. 多单逻辑
                # 条件：价格在MA60之上 且 日线MA3上涨
                if current_price > ma60 and ma3_curr > ma3_prev:
                    # 首单开仓
                    if not self.long_pos_prices:
                        self._execute_order("BUY", "OPEN", self.long_pos_prices)
                    # 补仓 (Martingale)
                    elif self.long_pos_prices:
                        last_price = self.long_pos_prices[-1]
                        # 获取当前层级对应的步长
                        idx = len(self.long_pos_prices) - 1
                        # 防止索引越界，超过配置长度取最后一个
                        step_cfg = self.config['copy_bottom']
                        step = step_cfg[idx] if idx < len(step_cfg) else step_cfg[-1]
                        
                        if (last_price - current_price) >= step:
                            self._execute_order("BUY", "OPEN", self.long_pos_prices)
                
                # 多单止盈/平仓
                if self.long_pos_prices:
                    last_price = self.long_pos_prices[-1]
                    dynamic_step = len(self.long_pos_prices) * self.config['touch_top']
                    if (current_price - last_price) >= dynamic_step:
                        self._execute_order("BUY", "CLOSE", self.long_pos_prices)

                # 3. 空单逻辑
                # 条件：价格在MA60之下 且 日线MA3下跌
                if current_price < ma60 and ma3_curr < ma3_prev:
                    # 首单开仓
                    if not self.short_pos_prices:
                        self._execute_order("SELL", "OPEN", self.short_pos_prices)
                    # 补仓
                    elif self.short_pos_prices:
                        last_price = self.short_pos_prices[-1]
                        idx = len(self.short_pos_prices) - 1
                        step_cfg = self.config['copy_top']
                        step = step_cfg[idx] if idx < len(step_cfg) else step_cfg[-1]
                        
                        if (current_price - last_price) >= step:
                            self._execute_order("SELL", "OPEN", self.short_pos_prices)

                # 空单止盈/平仓
                if self.short_pos_prices:
                    last_price = self.short_pos_prices[-1]
                    dynamic_step = len(self.short_pos_prices) * self.config['touch_bottom']
                    if (last_price - current_price) >= dynamic_step:
                        self._execute_order("SELL", "CLOSE", self.short_pos_prices)

        except KeyboardInterrupt:
            print("\n程序结束")
        finally:
            self.api.close()

# --- 配置与入口 ---
if __name__ == "__main__":
    # 策略参数配置
    STRATEGY_CONFIG = {
        "copy_bottom": [5, 6, 8, 10, 13, 15, 18, 21, 34, 55, 89, 55, 34, 21, 18, 15, 13, 10],
        "copy_top": [5, 6, 8, 10, 13, 15, 18, 21, 34, 55, 89, 55, 34, 21, 18, 15, 13, 10],
        "touch_top": 6,
        "touch_bottom": 6
    }
    
    SYMBOL = "CZCE.MA601"

    # 创建API实例
    api = TqApi(
        account=TqSim(init_balance=100000),
        backtest=TqBacktest(start_dt=date(2025, 10, 18), end_dt=date(2025, 11, 24)),
        web_gui=True,
        auth=TqAuth("cadofa", "cadofa6688"),
        debug=False
    )

    # 运行策略
    strategy = GridStrategy(SYMBOL, api, STRATEGY_CONFIG)
    strategy.run()