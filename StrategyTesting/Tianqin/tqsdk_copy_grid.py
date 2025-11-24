from datetime import date
from tqsdk import TqApi, TqAuth, TqSim, TqBacktest
from tqsdk.ta import MA
import math

class GridStrategy:
    def __init__(self, symbol, api, config):
        self.symbol = symbol
        self.api = api
        self.config = config
        
        # 初始化数据序列
        self.quote = api.get_quote(symbol)
        self.klines_1min = api.get_kline_serial(symbol, 60, data_length=100)
        self.klines_1day = api.get_kline_serial(symbol, 24 * 60 * 60, data_length=8)
        
        #以此获取账户资金情况
        self.account = api.get_account()

        # 持仓价格列表
        self.long_pos_prices = []
        self.short_pos_prices = []
        
        # 累计平仓盈亏 (Realized PnL)
        self._long_accum_pnl = 0.0
        self._short_accum_pnl = 0.0

    # ---------------- [盈亏计算函数] ----------------

    def get_long_float_pnl(self):
        """多单实时持仓盈亏 (浮动盈亏)"""
        if not self.long_pos_prices:
            return 0.0
        
        current_price = self.quote.last_price
        multiplier = self.quote.volume_multiple
        
        if math.isnan(current_price) or math.isnan(multiplier):
            return 0.0
            
        pnl = 0.0
        for entry_price in self.long_pos_prices:
            pnl += (current_price - entry_price) * multiplier
        return pnl

    def get_short_float_pnl(self):
        """空单实时持仓盈亏 (浮动盈亏)"""
        if not self.short_pos_prices:
            return 0.0
            
        current_price = self.quote.last_price
        multiplier = self.quote.volume_multiple
        
        if math.isnan(current_price) or math.isnan(multiplier):
            return 0.0
            
        pnl = 0.0
        for entry_price in self.short_pos_prices:
            pnl += (entry_price - current_price) * multiplier
        return pnl

    def get_long_accum_pnl(self):
        """多单累计平仓盈亏"""
        return self._long_accum_pnl

    def get_short_accum_pnl(self):
        """空单累计平仓盈亏"""
        return self._short_accum_pnl

    # ---------------- [新增：风控检查逻辑] ----------------
    
    def _is_risk_triggered(self, direction):
        """
        检查指定方向是否触发最大亏损风控
        Return: True (触发风控，禁止开仓), False (未触发，允许开仓)
        """
        # 获取账户动态权益 (balance = 静态权益 + 浮动盈亏)
        equity = self.account.balance
        if equity <= 0:
            return True # 资金不足或异常，禁止开仓

        threshold = self.config.get('max_loss_ratio', 0.05) # 默认5%

        if direction == "BUY":
            # 多单总盈亏 = 多单浮动 + 多单累计
            total_pnl = self.get_long_float_pnl() + self.get_long_accum_pnl()
            
            # 如果是亏损状态，且亏损金额占比超过阈值
            if total_pnl < 0 and (abs(total_pnl) / equity) >= threshold:
                return True
                
        elif direction == "SELL":
            # 空单总盈亏 = 空单浮动 + 空单累计
            total_pnl = self.get_short_float_pnl() + self.get_short_accum_pnl()
            
            if total_pnl < 0 and (abs(total_pnl) / equity) >= threshold:
                return True

        return False

    # ---------------- [原有逻辑] ----------------

    def _get_ma3_trend(self):
        """计算日线MA3趋势"""
        ma_data = MA(self.klines_1day, 3)
        ma_list = list(ma_data["ma"])
        if len(ma_list) < 3:
            return 0, 0
        return ma_list[-1], ma_list[-2]

    def _get_ma60(self):
        """计算1分钟线MA60"""
        if len(self.klines_1min) < 60:
            return None
        return self.klines_1min.close.iloc[-60:].mean()

    def _print_status(self, ma60):
        """打印当前行情及盈亏状态"""
        price = self.quote.last_price
        ma60_str = f"{ma60:.2f}" if ma60 else "计算中"
        
        l_float = self.get_long_float_pnl()
        s_float = self.get_short_float_pnl()
        l_accum = self.get_long_accum_pnl()
        s_accum = self.get_short_accum_pnl()
        
        # 计算总盈亏和风险状态用于显示
        equity = self.account.balance
        l_total = l_float + l_accum
        s_total = s_float + s_accum
        
        # 简单的风险提示字符串
        l_risk_str = "[多单暂停]" if self._is_risk_triggered("BUY") else ""
        s_risk_str = "[空单暂停]" if self._is_risk_triggered("SELL") else ""

        print(f"最新价: {price} | MA60: {ma60_str} | 权益: {equity:.2f}")
        print(f"多单: 浮盈{l_float:>8.2f} + 累计{l_accum:>8.2f} = 总{l_total:>8.2f} {l_risk_str}")
        print(f"空单: 浮盈{s_float:>8.2f} + 累计{s_accum:>8.2f} = 总{s_total:>8.2f} {s_risk_str}")
        print(f"******" * 18)
        print()

    def _execute_order(self, direction, offset, pos_list):
        """交易执行函数"""
        if offset == "OPEN":
            order_dir = direction
            action_name = "多单" if direction == "BUY" else "空单"
        else:
            order_dir = "SELL" if direction == "BUY" else "BUY"
            action_name = "多单" if direction == "BUY" else "空单"

        act_type = "建仓OPEN" if offset == "OPEN" else "平仓CLOSE"
        print(f"✅ {action_name}{act_type}订单已提交...")

        order = self.api.insert_order(symbol=self.symbol, direction=order_dir, offset=offset, volume=1)

        while order.status == "ALIVE":
            self.api.wait_update()

        if order.status == "FINISHED" and not math.isnan(order.trade_price):
            print(f"✅ {action_name}{act_type}成功! 价格: {order.trade_price}")
            
            multiplier = self.quote.volume_multiple if not math.isnan(self.quote.volume_multiple) else 1.0
            
            if offset == "OPEN":
                pos_list.append(order.trade_price)
            else:
                if pos_list:
                    entry_price = pos_list[-1]
                    exit_price = order.trade_price
                    
                    if direction == "BUY": 
                        trade_pnl = (exit_price - entry_price) * multiplier
                        self._long_accum_pnl += trade_pnl
                        print(f"   -> 多单本次平仓盈亏: {trade_pnl:.2f}")
                    else: 
                        trade_pnl = (entry_price - exit_price) * multiplier
                        self._short_accum_pnl += trade_pnl
                        print(f"   -> 空单本次平仓盈亏: {trade_pnl:.2f}")
                    
                    pos_list.pop()

            pos_info = self.api.get_position(self.symbol)
            pos_vol = pos_info.pos_long if direction == "BUY" else pos_info.pos_short
            print(f"持仓: {action_name}{pos_vol}手, 列表: {pos_list}")
            
            self._print_status(self._get_ma60())
            return True
        else:
            print(f"❌ 订单异常: {order.status}")
            return False

    def run(self):
        try:
            while True:
                self.api.wait_update()

                current_price = self.quote.last_price
                ma60 = self._get_ma60()
                ma3_curr, ma3_prev = self._get_ma3_trend()

                if ma60 is None or self.quote.datetime == 0:
                    if len(self.klines_1min) % 10 == 0: 
                        print(f"K线预加载: {len(self.klines_1min)}/60...")
                    continue

                # --- 实时检查风控状态 ---
                is_long_banned = self._is_risk_triggered("BUY")
                is_short_banned = self._is_risk_triggered("SELL")

                # ================= 2. 多单逻辑 =================
                # 条件：价格在MA60之上 且 日线MA3上涨 且 未触发多单风控
                if current_price > ma60 and ma3_curr > ma3_prev and not is_long_banned:
                    if not self.long_pos_prices:
                        self._execute_order("BUY", "OPEN", self.long_pos_prices)
                    elif self.long_pos_prices:
                        last_price = self.long_pos_prices[-1]
                        idx = len(self.long_pos_prices) - 1
                        step_cfg = self.config['copy_bottom']
                        step = step_cfg[idx] if idx < len(step_cfg) else step_cfg[-1]
                        
                        if (last_price - current_price) >= step:
                            self._execute_order("BUY", "OPEN", self.long_pos_prices)
                
                # 多单止盈/平仓 (不受开仓风控影响)
                if self.long_pos_prices:
                    last_price = self.long_pos_prices[-1]
                    dynamic_step = len(self.long_pos_prices) * self.config['touch_top']
                    if (current_price - last_price) >= dynamic_step:
                        self._execute_order("BUY", "CLOSE", self.long_pos_prices)

                # ================= 3. 空单逻辑 =================
                # 条件：价格在MA60之下 且 日线MA3下跌 且 未触发空单风控
                if current_price < ma60 and ma3_curr < ma3_prev and not is_short_banned:
                    if not self.short_pos_prices:
                        self._execute_order("SELL", "OPEN", self.short_pos_prices)
                    elif self.short_pos_prices:
                        last_price = self.short_pos_prices[-1]
                        idx = len(self.short_pos_prices) - 1
                        step_cfg = self.config['copy_top']
                        step = step_cfg[idx] if idx < len(step_cfg) else step_cfg[-1]
                        
                        if (current_price - last_price) >= step:
                            self._execute_order("SELL", "OPEN", self.short_pos_prices)

                # 空单止盈/平仓 (不受开仓风控影响)
                if self.short_pos_prices:
                    last_price = self.short_pos_prices[-1]
                    dynamic_step = len(self.short_pos_prices) * self.config['touch_bottom']
                    if (last_price - current_price) >= dynamic_step:
                        self._execute_order("SELL", "CLOSE", self.short_pos_prices)

        except KeyboardInterrupt:
            print("\n程序结束")
        finally:
            print("\n=== 最终统计 ===")
            print(f"多单最终累计盈亏: {self.get_long_accum_pnl():.2f}")
            print(f"空单最终累计盈亏: {self.get_short_accum_pnl():.2f}")
            self.api.close()

if __name__ == "__main__":
    # 策略参数配置
    STRATEGY_CONFIG = {
        "copy_bottom": [5, 6, 8, 10, 13, 15, 18, 21, 34, 55, 89, 55, 34, 21, 18, 15, 13, 10],
        "copy_top": [5, 6, 8, 10, 13, 15, 18, 21, 34, 55, 89, 55, 34, 21, 18, 15, 13, 10],
        "touch_top": 6,
        "touch_bottom": 6,
        "max_loss_ratio": 0.005
    }
    
    #SYMBOL = "CZCE.MA601"
    #SYMBOL = "DCE.m2601"  
    #SYMBOL = "CZCE.FG601"
    SYMBOL = "CZCE.SA601"

    # 创建API实例
    api = TqApi(
        account=TqSim(init_balance=100000),
        backtest=TqBacktest(start_dt=date(2025, 8, 18), end_dt=date(2025, 11, 24)),
        web_gui=True,
        auth=TqAuth("cadofa", "cadofa6688"),
        debug=False
    )

    # 运行策略
    strategy = GridStrategy(SYMBOL, api, STRATEGY_CONFIG)
    strategy.run()