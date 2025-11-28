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
        
        self.account = api.get_account()

        # 持仓价格列表
        self.long_pos_prices = []
        self.short_pos_prices = []

        # --- 记录上次平仓价格，用于连续止盈逻辑 ---
        self.last_long_exit_price = None
        self.last_short_exit_price = None
        
        # 风控状态管理变量
        self.banned_direction = None   # 当前被暂停的方向: "BUY", "SELL" 或 None
        self.prev_long_risky = False   # 上一帧多单是否超阈值
        self.prev_short_risky = False  # 上一帧空单是否超阈值

    # ---------------- [盈亏计算函数] ----------------
    def get_long_float_pnl(self):
        """计算多单浮动盈亏"""
        if not self.long_pos_prices: return 0.0
        current_price = self.quote.last_price
        multiplier = self.quote.volume_multiple
        if math.isnan(current_price) or math.isnan(multiplier): return 0.0
        pnl = 0.0
        for entry_price in self.long_pos_prices:
            pnl += (current_price - entry_price) * multiplier
        return pnl

    def get_short_float_pnl(self):
        """计算空单浮动盈亏"""
        if not self.short_pos_prices: return 0.0
        current_price = self.quote.last_price
        multiplier = self.quote.volume_multiple
        if math.isnan(current_price) or math.isnan(multiplier): return 0.0
        pnl = 0.0
        for entry_price in self.short_pos_prices:
            pnl += (entry_price - current_price) * multiplier
        return pnl

    # ---------------- [风控核心逻辑] ----------------
    
    def _check_raw_threshold(self, direction):
        """纯粹计算是否超过风控阈值，不涉及暂停逻辑"""
        equity = self.account.balance
        if equity <= 0: return True
        threshold = self.config.get('max_loss_ratio', 0.05)

        if direction == "BUY":
            float_pnl = self.get_long_float_pnl()
            if float_pnl < 0 and (abs(float_pnl) / equity) >= threshold:
                return True
        elif direction == "SELL":
            float_pnl = self.get_short_float_pnl()
            if float_pnl < 0 and (abs(float_pnl) / equity) >= threshold:
                return True
        return False

    def _update_risk_state(self):
        """更新风控状态机"""
        curr_long_risky = self._check_raw_threshold("BUY")
        curr_short_risky = self._check_raw_threshold("SELL")

        new_long_trigger = curr_long_risky and not self.prev_long_risky
        new_short_trigger = curr_short_risky and not self.prev_short_risky

        if new_long_trigger:
            self.banned_direction = "BUY"
        elif new_short_trigger:
            self.banned_direction = "SELL"
        else:
            if self.banned_direction == "BUY":
                if not curr_long_risky:
                    if curr_short_risky:
                        self.banned_direction = "SELL"
                    else:
                        self.banned_direction = None
            elif self.banned_direction == "SELL":
                if not curr_short_risky:
                    if curr_long_risky:
                        self.banned_direction = "BUY"
                    else:
                        self.banned_direction = None

        self.prev_long_risky = curr_long_risky
        self.prev_short_risky = curr_short_risky

    def _is_risk_triggered(self, direction):
        return self.banned_direction == direction

    # ---------------- [辅助函数] ----------------
    def _get_ma3_trend(self):
        """返回 (当前MA3, 上一次MA3)"""
        ma_data = MA(self.klines_1day, 3)
        ma_list = list(ma_data["ma"])
        if len(ma_list) < 3: return 0, 0
        return ma_list[-1], ma_list[-2]

    def _get_ma60(self):
        """获取当前1分钟K线的MA60值"""
        if len(self.klines_1min) < 60: return None
        return self.klines_1min.close.iloc[-60:].mean()

    def _print_status(self, ma60):
        price = self.quote.last_price
        ma60_str = f"{ma60:.2f}" if ma60 else "计算中"
        
        l_float = self.get_long_float_pnl()
        s_float = self.get_short_float_pnl()
        
        equity = self.account.balance
        
        l_risk_str = "[⛔暂停开仓]" if self.banned_direction == "BUY" else ""
        s_risk_str = "[⛔暂停开仓]" if self.banned_direction == "SELL" else ""
        
        if self._check_raw_threshold("BUY") and self.banned_direction != "BUY":
            l_risk_str = "[⚠️超阈值但放开]"
        if self._check_raw_threshold("SELL") and self.banned_direction != "SELL":
            s_risk_str = "[⚠️超阈值但放开]"

        print(f"最新价: {price} | MA60: {ma60_str} | 权益(含浮盈): {equity:.2f}")
        print(f"多单: {len(self.long_pos_prices)}手 | 浮动盈亏: {l_float:>8.2f} {l_risk_str} | {self.long_pos_prices}")
        print(f"空单: {len(self.short_pos_prices)}手 | 浮动盈亏: {s_float:>8.2f} {s_risk_str} | {self.short_pos_prices}")
        print(f"******" * 18)
        print()

    # ---------------- [交易执行逻辑] ----------------

    def _execute_order(self, direction, offset, pos_list):
        if offset == "OPEN":
            order_dir = direction
            action_name = "多单" if direction == "BUY" else "空单"
        else:
            order_dir = "SELL" if direction == "BUY" else "BUY"
            action_name = "多单" if direction == "BUY" else "空单"

        final_offset = offset
        if offset != "OPEN":
            exchange = self.symbol.split('.')[0]
            if exchange in ["SHFE", "INE"]:
                pos = self.api.get_position(self.symbol)
                if order_dir == "SELL":
                    if pos.pos_long_his > 0:
                        final_offset = "CLOSE"
                        print("   [提示] 上期所优先平昨仓")
                    else:
                        final_offset = "CLOSETODAY"
                        print("   [提示] 上期所平今仓")
                else: 
                    if pos.pos_short_his > 0:
                        final_offset = "CLOSE"
                        print("   [提示] 上期所优先平昨仓")
                    else:
                        final_offset = "CLOSETODAY"
                        print("   [提示] 上期所平今仓")

        act_type = "建仓OPEN" if offset == "OPEN" else f"平仓{final_offset}"
        
        if order_dir == "BUY":
            limit_price = self.quote.ask_price1
            price_desc = "卖一价"
        else:
            limit_price = self.quote.bid_price1
            price_desc = "买一价"

        if math.isnan(limit_price):
            limit_price = self.quote.last_price
            price_desc = "最新价(兜底)"

        if math.isnan(limit_price):
            print("❌ 无法获取有效价格，取消下单")
            return False

        print(f"✅ {action_name}{act_type}订单提交 | {price_desc}: {limit_price}")

        order = self.api.insert_order(
            symbol=self.symbol, 
            direction=order_dir, 
            offset=final_offset,
            volume=1, 
            limit_price=limit_price
        )

        while order.status == "ALIVE":
            self.api.wait_update()

        if order.status == "FINISHED" and not math.isnan(order.trade_price):
            print(f"✅ {action_name}{act_type}成功! 成交均价: {order.trade_price}")
            
            if offset != "OPEN":
                if direction == "BUY":
                    self.last_long_exit_price = order.trade_price
                elif direction == "SELL":
                    self.last_short_exit_price = order.trade_price

            if offset == "OPEN":
                pos_list.append(order.trade_price)
            else:
                if pos_list:
                    pos_list.pop()
                    print(f"   -> {action_name}平仓完成，释放保证金")

            pos_info = self.api.get_position(self.symbol)
            pos_vol = pos_info.pos_long if direction == "BUY" else pos_info.pos_short
            
            print(f"当前持仓量: {action_name}{pos_vol}手 | 持仓列表: {pos_list}")
            
            self._print_status(self._get_ma60())
            return True
        else:
            print(f"❌ 订单失败: {order.status} | {order.last_msg}")
            return False

    def run(self):
        try:
            while True:
                self.api.wait_update()
                
                # --- 1. 更新风控状态机 ---
                self._update_risk_state()

                current_price = self.quote.last_price
                price_tick = self.quote.price_tick

                # 获取当前MA60 (均值)
                ma60 = self._get_ma60()
                # 获取MA3趋势
                ma3_curr, ma3_prev = self._get_ma3_trend()

                if ma60 is None or self.quote.datetime == 0:
                    if len(self.klines_1min) % 10 == 0: 
                        print(f"K线预加载: {len(self.klines_1min)}/60...")
                    continue
                
                if math.isnan(current_price) or math.isnan(price_tick): 
                    continue

                # --- 计算 MA60 的前一周期值，用于判断趋势 ---
                ma60_prev = None
                if len(self.klines_1min) >= 61:
                    # 获取倒数第61根到倒数第2根的均值 (即上一分钟的MA60)
                    ma60_prev = self.klines_1min.close.iloc[-61:-1].mean()

                # --- 2. 获取当前是否暂停 ---
                is_long_banned = self._is_risk_triggered("BUY")
                is_short_banned = self._is_risk_triggered("SELL")
                
                # 在每一轮循环开始时获取持仓数量
                long_count = len(self.long_pos_prices)
                short_count = len(self.short_pos_prices)

                # ================= [新增] 特殊开仓逻辑 =================
                
                # 特殊逻辑 1: 双均线向上 + 价格之上 + 多单 < 空单 -> 补多单 (不受约束)
                if ma60_prev is not None:
                    ma60_is_up = ma60 > ma60_prev
                    ma3_is_up = ma3_curr > ma3_prev
                    
                    if ma3_is_up and ma60_is_up and current_price > ma3_curr and current_price > ma60:
                        if long_count < short_count:
                            print(f"⚡ [特殊策略触发] 趋势向上且多单({long_count})<空单({short_count}) -> 强制开多")
                            self._execute_order("BUY", "OPEN", self.long_pos_prices)
                            # 执行后更新计数，防止同一帧重复逻辑
                            long_count += 1 

                # 特殊逻辑 2: 双均线向下 + 价格之下 + 空单 < 多单 -> 补空单 (不受约束)
                if ma60_prev is not None:
                    ma60_is_down = ma60 < ma60_prev
                    ma3_is_down = ma3_curr < ma3_prev

                    if ma3_is_down and ma60_is_down and current_price < ma3_curr and current_price < ma60:
                        if short_count < long_count:
                            print(f"⚡ [特殊策略触发] 趋势向下且空单({short_count})<多单({long_count}) -> 强制开空")
                            self._execute_order("SELL", "OPEN", self.short_pos_prices)
                            # 执行后更新计数
                            short_count += 1  # <--- 已补上

                # ================= 3. 原有多单逻辑 (标准网格) =================
                if current_price > ma60 and ma3_curr > ma3_prev and not is_long_banned:
                    if not self.long_pos_prices:
                        self._execute_order("BUY", "OPEN", self.long_pos_prices)
                    elif self.long_pos_prices:
                        last_price = self.long_pos_prices[-1]
                        idx = len(self.long_pos_prices) - 1
                        step_cfg = self.config['copy_bottom']
                        step_ticks = step_cfg[idx] if idx < len(step_cfg) else step_cfg[-1]
                        step = step_ticks * price_tick
                        
                        if (last_price - current_price) >= step:
                            self._execute_order("BUY", "OPEN", self.long_pos_prices)
                
                # 多单止盈
                if self.long_pos_prices:
                    last_price = self.long_pos_prices[-1]
                    dynamic_step = current_price * 0.01
                    if (current_price - last_price) >= dynamic_step:
                        self._execute_order("BUY", "CLOSE", self.long_pos_prices)

                # 多单连续止盈
                if self.long_pos_prices and self.last_long_exit_price is not None:
                    dynamic_step = current_price * 0.01
                    if (current_price - self.last_long_exit_price) >= dynamic_step:
                         print(f"🚀 [多单追踪] 价格继续上涨，触发连续平仓")
                         self._execute_order("BUY", "CLOSE", self.long_pos_prices)

                # ================= 4. 原有空单逻辑 (标准网格) =================
                if current_price < ma60 and ma3_curr < ma3_prev and not is_short_banned:
                    if not self.short_pos_prices:
                        self._execute_order("SELL", "OPEN", self.short_pos_prices)
                    elif self.short_pos_prices:
                        last_price = self.short_pos_prices[-1]
                        idx = len(self.short_pos_prices) - 1
                        step_cfg = self.config['copy_top']
                        step_ticks = step_cfg[idx] if idx < len(step_cfg) else step_cfg[-1]
                        step = step_ticks * price_tick
                        
                        if (current_price - last_price) >= step:
                            self._execute_order("SELL", "OPEN", self.short_pos_prices)

                # 空单止盈
                if self.short_pos_prices:
                    last_price = self.short_pos_prices[-1]
                    dynamic_step = current_price * 0.01
                    if (last_price - current_price) >= dynamic_step:
                        self._execute_order("SELL", "CLOSE", self.short_pos_prices)

                # 空单连续止盈
                if self.short_pos_prices and self.last_short_exit_price is not None:
                    dynamic_step = current_price * 0.01
                    if (self.last_short_exit_price - current_price) >= dynamic_step:
                         print(f"🚀 [空单追踪] 价格继续下跌，触发连续平仓")
                         self._execute_order("SELL", "CLOSE", self.short_pos_prices)

        except KeyboardInterrupt:
            print("\n程序结束")
        finally:
            print("\n=== 最终统计 ===")
            print(f"账户最终权益: {self.account.balance:.2f}")
            self.api.close()

if __name__ == "__main__":
    # 策略参数配置
    STRATEGY_CONFIG = {
        "copy_bottom": [5, 6, 8, 10, 13, 15, 18, 21, 34, 55, 89, 55, 34, 21, 18, 15, 13, 10],
        "copy_top": [5, 6, 8, 10, 13, 15, 18, 21, 34, 55, 89, 55, 34, 21, 18, 15, 13, 10],
        "touch_top": 6,
        "touch_bottom": 6,
        "max_loss_ratio": 0.01
    }
    
    #SYMBOL = "SHFE.rb2601"
    #SYMBOL = "DCE.m2601"
    #SYMBOL = "DCE.v2601"  
    #SYMBOL = "CZCE.FG601"
    #SYMBOL = "CZCE.SA601"
    #SYMBOL = "CZCE.RM601"
    SYMBOL = "CZCE.TA601"
    #SYMBOL = "CZCE.SR601"
    #SYMBOL = "CZCE.SM601"
    #SYMBOL = "CZCE.MA601"

    # 创建API实例
    api = TqApi(
        account=TqSim(init_balance=100000),
        backtest=TqBacktest(start_dt=date(2025, 5, 18), end_dt=date(2025, 11, 29)),
        web_gui=True,
        auth=TqAuth("cadofa", "cadofa6688"),
        debug=False
    )
    # 运行策略
    strategy = GridStrategy(SYMBOL, api, STRATEGY_CONFIG)
    strategy.run()