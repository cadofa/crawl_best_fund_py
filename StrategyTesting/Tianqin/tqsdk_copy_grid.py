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

        # --- 虚拟持仓价格列表 (策略逻辑层) ---
        self.long_pos_prices = []
        self.short_pos_prices = []

        # --- 记录上次平仓价格，用于连续止盈逻辑 ---
        self.last_long_exit_price = None
        self.last_short_exit_price = None
        
        # 风控状态管理变量
        self.banned_direction = None
        self.prev_long_risky = False
        self.prev_short_risky = False

    # ---------------- [修改：调试信息打印辅助函数] ----------------
    def _print_snapshot(self, action_msg):
        """
        打印动作描述及当前账户权益简报 (修改后)
        :param action_msg: 当前发生的动作描述字符串
        """
        # 获取账户当前的实际持仓对象
        pos = self.api.get_position(self.symbol)
        
        print(f"   [调试] 成交动作: {action_msg}")
        # 打印实际持仓 (标注多空方向) 和 账户权益
        print(f"   [调试] 账户权益: {self.account.balance:.2f}")
        print(f"   [调试] 实际持仓列表: [多单] {pos.pos_long} 手")
        print(f"   [调试] 实际持仓列表: [空单] {pos.pos_short} 手")
        print("=" * 80 + "\n")

    # ---------------- [盈亏计算函数 (基于虚拟持仓)] ----------------
    def get_long_float_pnl(self):
        """计算多单浮动盈亏 - 风控层使用 LastPrice (盯市盈亏)，避免点差导致的误触风控"""
        if not self.long_pos_prices: return 0.0
        current_price = self.quote.last_price
        multiplier = self.quote.volume_multiple
        if math.isnan(current_price) or math.isnan(multiplier): return 0.0
        pnl = 0.0
        for entry_price in self.long_pos_prices:
            pnl += (current_price - entry_price) * multiplier
        return pnl

    def get_short_float_pnl(self):
        """计算空单浮动盈亏 - 风控层使用 LastPrice (盯市盈亏)"""
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
        ma_data = MA(self.klines_1day, 3)
        ma_list = list(ma_data["ma"])
        if len(ma_list) < 3: return 0, 0
        return ma_list[-1], ma_list[-2]

    def _get_ma60(self):
        if len(self.klines_1min) < 60: return None
        return self.klines_1min.close.iloc[-60:].mean()

    # ---------------- [实际下单执行器] ----------------
    def _place_order_now(self, direction, offset, volume):
        """发送实际订单的底层函数"""
        if volume <= 0: return

        # 针对上期所/能源中心的平今/平昨处理
        final_offset = offset
        if offset == "CLOSE":
            exchange = self.symbol.split('.')[0]
            if exchange in ["SHFE", "INE"]:
                pos = self.api.get_position(self.symbol)
                if direction == "BUY": # 买平（平空）
                    if pos.pos_short_his >= volume:
                        final_offset = "CLOSE"
                    else:
                        final_offset = "CLOSETODAY"
                else: # 卖平（平多）
                    if pos.pos_long_his >= volume:
                        final_offset = "CLOSE"
                    else:
                        final_offset = "CLOSETODAY"

        order_dir_cn = "买入" if direction == "BUY" else "卖出"
        offset_cn = "开仓" if final_offset == "OPEN" else "平仓"
        
        # 实际下单仍使用对手价以保证成交
        limit_price = self.quote.ask_price1 if direction == "BUY" else self.quote.bid_price1
        if math.isnan(limit_price): limit_price = self.quote.last_price

        print(f"⚡ [执行同步] {order_dir_cn}{offset_cn} {volume}手 | 价格: {limit_price}")
        
        order = self.api.insert_order(
            symbol=self.symbol,
            direction=direction,
            offset=final_offset,
            volume=volume,
            limit_price=limit_price
        )
        while order.status == "ALIVE":
            self.api.wait_update()

    def _sync_actual_position(self):
        """同步实际持仓到目标净持仓"""
        target_net = len(self.long_pos_prices) - len(self.short_pos_prices)
        pos = self.api.get_position(self.symbol)
        actual_net = pos.pos_long - pos.pos_short
        diff = target_net - actual_net
        
        if diff == 0: return

        if diff > 0: # 需增加净多头
            volume = abs(diff)
            # 优先平空
            if pos.pos_short > 0:
                cover = min(pos.pos_short, volume)
                self._place_order_now("BUY", "CLOSE", cover)
                volume -= cover
            # 剩余开多
            if volume > 0:
                self._place_order_now("BUY", "OPEN", volume)

        elif diff < 0: # 需增加净空头
            volume = abs(diff)
            # 优先平多
            if pos.pos_long > 0:
                close = min(pos.pos_long, volume)
                self._place_order_now("SELL", "CLOSE", close)
                volume -= close
            # 剩余开空
            if volume > 0:
                self._place_order_now("SELL", "OPEN", volume)

    # ---------------- [主循环] ----------------
    def run(self):
        print("策略启动，开始初始化数据...")
        try:
            while True:
                self.api.wait_update()
                
                # --- 1. 数据准备 ---
                current_price = self.quote.last_price
                
                # 获取真实对手价用于【记账】，但触发信号依然用 current_price
                ask_price = self.quote.ask_price1
                bid_price = self.quote.bid_price1
                
                # 数据保护
                if math.isnan(ask_price) or math.isnan(bid_price):
                    ask_price = current_price
                    bid_price = current_price

                price_tick = self.quote.price_tick
                if math.isnan(current_price) or math.isnan(price_tick): continue

                ma60 = self._get_ma60()
                if ma60 is None:
                    if len(self.klines_1min) % 10 == 0: 
                        print(f"K线预加载: {len(self.klines_1min)}/60...")
                    continue
                    
                ma3_curr, ma3_prev = self._get_ma3_trend()
                
                # --- 风控更新 ---
                self._update_risk_state()
                is_long_banned = self._is_risk_triggered("BUY")
                is_short_banned = self._is_risk_triggered("SELL")

                # MA60 前值
                ma60_prev = None
                if len(self.klines_1min) >= 61:
                    ma60_prev = self.klines_1min.close.iloc[-61:-1].mean()

                long_count = len(self.long_pos_prices)
                short_count = len(self.short_pos_prices)

                # ==========================================================
                # ============= 核心逻辑：信号触发与记账分离 =================
                # ==========================================================

                # --- 特殊逻辑 1: 趋势向上，强制补多单 ---
                if ma60_prev is not None:
                    ma60_is_up = ma60 > ma60_prev
                    ma3_is_up = ma3_curr > ma3_prev
                    
                    if ma3_is_up and ma60_is_up and current_price > ma3_curr and current_price > ma60:
                        if long_count <= short_count:
                            self.long_pos_prices.append(ask_price)
                            long_count += 1 
                            self._print_snapshot(f"⚡ [虚拟信号] 趋势向上补多单 (Trigger: {current_price}, Cost: {ask_price})")

                # --- 特殊逻辑 2: 趋势向下，强制补空单 ---
                if ma60_prev is not None:
                    ma60_is_down = ma60 < ma60_prev
                    ma3_is_down = ma3_curr < ma3_prev

                    if ma3_is_down and ma60_is_down and current_price < ma3_curr and current_price < ma60:
                        if short_count <= long_count:
                            self.short_pos_prices.append(bid_price)
                            short_count += 1
                            self._print_snapshot(f"⚡ [虚拟信号] 趋势向下补空单 (Trigger: {current_price}, Cost: {bid_price})")

                # --- 3. 标准网格多单逻辑 ---
                if current_price > ma60 and ma3_curr > ma3_prev and not is_long_banned:
                    if not self.long_pos_prices:
                        self.long_pos_prices.append(ask_price)
                        self._print_snapshot(f"➕ [虚拟信号] 首单开多 (Trigger: {current_price}, Cost: {ask_price})")
                    elif self.long_pos_prices:
                        last_entry = self.long_pos_prices[-1]
                        idx = len(self.long_pos_prices) - 1
                        step_cfg = self.config['copy_bottom']
                        step_ticks = step_cfg[idx] if idx < len(step_cfg) else step_cfg[-1]
                        step = step_ticks * price_tick
                        
                        if (last_entry - current_price) >= step:
                            self.long_pos_prices.append(ask_price)
                            self._print_snapshot(f"➕ [虚拟信号] 网格加多 (Trigger: {current_price}, Cost: {ask_price})")
                
                # --- 多单止盈逻辑 ---
                if self.long_pos_prices:
                    last_entry = self.long_pos_prices[-1]
                    dynamic_step = current_price * 0.01
                    
                    if (current_price - last_entry) >= dynamic_step:
                        self.last_long_exit_price = bid_price 
                        self.long_pos_prices.pop()
                        self._print_snapshot(f"➖ [虚拟信号] 多单止盈 (Trigger: {current_price}, Sell: {bid_price})")

                # 多单连续止盈
                if self.long_pos_prices and self.last_long_exit_price is not None:
                    dynamic_step = current_price * 0.01
                    if (current_price - self.last_long_exit_price) >= dynamic_step:
                        self.last_long_exit_price = bid_price
                        self.long_pos_prices.pop()
                        self._print_snapshot(f"🚀 [虚拟信号] 多单追踪止盈 (Trigger: {current_price}, Sell: {bid_price})")

                # --- 4. 标准网格空单逻辑 ---
                if current_price < ma60 and ma3_curr < ma3_prev and not is_short_banned:
                    if not self.short_pos_prices:
                        self.short_pos_prices.append(bid_price)
                        self._print_snapshot(f"➕ [虚拟信号] 首单开空 (Trigger: {current_price}, Cost: {bid_price})")
                    elif self.short_pos_prices:
                        last_entry = self.short_pos_prices[-1]
                        idx = len(self.short_pos_prices) - 1
                        step_cfg = self.config['copy_top']
                        step_ticks = step_cfg[idx] if idx < len(step_cfg) else step_cfg[-1]
                        step = step_ticks * price_tick
                        
                        if (current_price - last_entry) >= step:
                            self.short_pos_prices.append(bid_price)
                            self._print_snapshot(f"➕ [虚拟信号] 网格加空 (Trigger: {current_price}, Cost: {bid_price})")

                # --- 空单止盈逻辑 ---
                if self.short_pos_prices:
                    last_entry = self.short_pos_prices[-1]
                    dynamic_step = current_price * 0.01
                    
                    if (last_entry - current_price) >= dynamic_step:
                        self.last_short_exit_price = ask_price
                        self.short_pos_prices.pop()
                        self._print_snapshot(f"➖ [虚拟信号] 空单止盈 (Trigger: {current_price}, Buy: {ask_price})")

                # 空单连续止盈
                if self.short_pos_prices and self.last_short_exit_price is not None:
                    dynamic_step = current_price * 0.01
                    if (self.last_short_exit_price - current_price) >= dynamic_step:
                        self.last_short_exit_price = ask_price
                        self.short_pos_prices.pop()
                        self._print_snapshot(f"🚀 [虚拟信号] 空单追踪止盈 (Trigger: {current_price}, Buy: {ask_price})")

                # ==========================================================
                # ============= 状态同步 ===================================
                # ==========================================================
                
                self._sync_actual_position()

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
    
    #SYMBOL = "SHFE.rb2601" #收益率: -5.09%, 年化收益率: -17.02%, 最大回撤: 6.30%, 年化夏普率: -4.2021
    #SYMBOL = "DCE.m2601"   #收益率: 3.45%, 年化收益率: 12.89%, 最大回撤: 18.97%, 年化夏普率: 0.4438
    #SYMBOL = "DCE.v2601"   #收益率: -0.87%, 年化收益率: -3.07%, 最大回撤: 4.26%, 年化收益率: -3.07%
    #SYMBOL = "CZCE.FG601"  #收益率: -10.49%, 年化收益率: -32.69%, 最大回撤: 13.31%, 年化夏普率: -1.7583
    #SYMBOL = "CZCE.SA601"  #收益率: -0.85%, 年化收益率: -3.00%, 最大回撤: 3.83%, 年化夏普率: -0.6946
    #SYMBOL = "CZCE.RM601"  #收益率: -4.19%, 年化收益率: -14.16%, 最大回撤: 10.71%, 年化夏普率: -0.5254
    #SYMBOL = "CZCE.TA601"  #收益率: 2.23%, 年化收益率: 8.19%, 最大回撤: 1.19%, 年化夏普率: 1.4430
    #SYMBOL = "CZCE.SR601"  #收益率: -1.97%, 年化收益率: -6.85%, 最大回撤: 4.12%, 年化夏普率: -1.9474 
    #SYMBOL = "CZCE.SM601"  #收益率: -3.77%, 年化收益率: -12.99%, 最大回撤: 5.70%, 年化夏普率: -1.8686
    #SYMBOL = "CZCE.MA601"  #收益率: -9.75%, 年化收益率: -30.67%, 最大回撤: 11.18%, 年化夏普率: -2.2367

    # 创建API实例
    api = TqApi(
        account=TqSim(init_balance=100000),
        backtest=TqBacktest(start_dt=date(2025, 8, 18), end_dt=date(2025, 11, 29)),
        web_gui=True,
        auth=TqAuth("cadofa", "cadofa6688"),
        debug=False
    )
    # 运行策略
    strategy = GridStrategy(SYMBOL, api, STRATEGY_CONFIG)
    strategy.run()