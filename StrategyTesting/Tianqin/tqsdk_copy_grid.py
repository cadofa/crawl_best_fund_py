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

    # ---------------- [调试信息打印辅助函数] ----------------
    def _print_snapshot(self, action_msg):
        """
        打印动作描述及当前账户权益简报
        """
        pos = self.api.get_position(self.symbol)
        print(f"   [调试] 成交动作: {action_msg}")
        print(f"   [调试] 账户权益: {self.account.balance:.2f}")
        print(f"   [调试] 实际持仓列表: [多单] {pos.pos_long} 手")
        print(f"   [调试] 实际持仓列表: [空单] {pos.pos_short} 手")
        print("=" * 80 + "\n")

    # ---------------- [盈亏计算函数] ----------------
    def get_long_float_pnl(self):
        if not self.long_pos_prices: return 0.0
        current_price = self.quote.last_price
        multiplier = self.quote.volume_multiple
        if math.isnan(current_price) or math.isnan(multiplier): return 0.0
        pnl = 0.0
        for entry_price in self.long_pos_prices:
            pnl += (current_price - entry_price) * multiplier
        return pnl

    def get_short_float_pnl(self):
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

    # ---------------- [原子化交易执行器] ----------------
    def _execute_order_core(self, direction, offset, volume, price_type_desc):
        """
        底层下单函数，负责发送指令并确认是否成交
        返回: (bool 是否成功, float 成交价格)
        """
        if volume <= 0: return False, 0.0
        
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

        # 下单价格选择 (对手价)
        limit_price = self.quote.ask_price1 if direction == "BUY" else self.quote.bid_price1
        if math.isnan(limit_price): limit_price = self.quote.last_price
        
        order = self.api.insert_order(
            symbol=self.symbol,
            direction=direction,
            offset=final_offset,
            volume=volume,
            limit_price=limit_price
        )
        
        # 等待委托结束
        while order.status == "ALIVE":
            self.api.wait_update()
            
        if order.status == "FINISHED" and order.volume_left == 0:
            return True, order.trade_price
        else:
            return False, 0.0

    def _trade_action(self, action_type, record_price):
        """
        执行具体的策略动作，并自动处理净头寸逻辑
        action_type: "OPEN_LONG", "OPEN_SHORT", "CLOSE_LONG", "CLOSE_SHORT"
        record_price: 策略逻辑中记录的成本价
        """
        pos = self.api.get_position(self.symbol)
        success = False
        trade_price = 0.0
        volume = 1
        
        executed_msg = ""
        
        # === 逻辑 1: 开多单 (Open Long) ===
        if action_type == "OPEN_LONG":
            # 如果有空单，先平空 (Cover)
            if pos.pos_short > 0:
                success, trade_price = self._execute_order_core("BUY", "CLOSE", volume, "平空")
                if success: executed_msg = f"买入平空 (Cover) {trade_price}"
            else:
                # 没空单，才开多 (Open)
                success, trade_price = self._execute_order_core("BUY", "OPEN", volume, "开多")
                if success: executed_msg = f"买入开仓 (Open) {trade_price}"
            
            # 只有成交成功，才更新虚拟列表
            if success:
                self.long_pos_prices.append(record_price)

        # === 逻辑 2: 开空单 (Open Short) ===
        elif action_type == "OPEN_SHORT":
            # 如果有多单，先平多 (Sell)
            if pos.pos_long > 0:
                success, trade_price = self._execute_order_core("SELL", "CLOSE", volume, "平多")
                if success: executed_msg = f"卖出平多 (Sell) {trade_price}"
            else:
                # 没多单，才开空 (Short)
                success, trade_price = self._execute_order_core("SELL", "OPEN", volume, "开空")
                if success: executed_msg = f"卖出开仓 (Short) {trade_price}"

            if success:
                self.short_pos_prices.append(record_price)

        # === 逻辑 3: 平多单 (Close Long) ===
        elif action_type == "CLOSE_LONG":
            if pos.pos_long > 0:
                success, trade_price = self._execute_order_core("SELL", "CLOSE", volume, "止盈平多")
                if success: executed_msg = f"卖出平仓 (CloseLong) {trade_price}"
            else:
                # 实际没持仓但虚拟有，直接移除虚拟，修正偏差
                success = True
                executed_msg = "修正虚拟持仓(无实盘)"

            if success and self.long_pos_prices:
                self.long_pos_prices.pop()

        # === 逻辑 4: 平空单 (Close Short) ===
        elif action_type == "CLOSE_SHORT":
            if pos.pos_short > 0:
                success, trade_price = self._execute_order_core("BUY", "CLOSE", volume, "止盈平空")
                if success: executed_msg = f"买入平仓 (CloseShort) {trade_price}"
            else:
                success = True
                executed_msg = "修正虚拟持仓(无实盘)"

            if success and self.short_pos_prices:
                self.short_pos_prices.pop()

        return success, executed_msg

    # ---------------- [主循环] ----------------
    def run(self):
        print("策略启动，开始初始化数据...")
        try:
            while True:
                self.api.wait_update()
                
                # --- 1. 数据准备 ---
                current_price = self.quote.last_price
                
                # 获取真实对手价用于【记账】
                ask_price = self.quote.ask_price1
                bid_price = self.quote.bid_price1
                
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

                # 获取当前计数
                curr_long_count = len(self.long_pos_prices)
                curr_short_count = len(self.short_pos_prices)

                # ==========================================================
                # ============= 修复点：无条件平衡逻辑 =======================
                # ==========================================================
                
                # 原理：只要两边数量不一致，就优先补齐少的一边，不再判断趋势
                # 这保证了多空持仓差距永远在 1 以内
                
                # 逻辑 A: 多单少，强制开多
                if curr_long_count < curr_short_count:
                    ok, msg = self._trade_action("OPEN_LONG", ask_price)
                    if ok:
                        self._print_snapshot(f"⚖️ [平衡] 补齐多单 -> {msg}")
                        curr_long_count += 1 # 更新计数
                        # 发生了平衡交易后，跳过本帧后续的网格逻辑，避免重复下单
                        continue 

                # 逻辑 B: 空单少，强制开空
                elif curr_short_count < curr_long_count:
                    ok, msg = self._trade_action("OPEN_SHORT", bid_price)
                    if ok:
                        self._print_snapshot(f"⚖️ [平衡] 补齐空单 -> {msg}")
                        curr_short_count += 1
                        continue

                # ==========================================================
                # ============= 标准网格逻辑 (在已平衡的基础上运行) ===========
                # ==========================================================

                # --- 3. 标准网格多单逻辑 ---
                if current_price > ma60 and ma3_curr > ma3_prev and not is_long_banned:
                    should_buy = False
                    log_msg = ""
                    
                    if not self.long_pos_prices:
                        should_buy = True
                        log_msg = "➕ [策略] 首单开多"
                    elif self.long_pos_prices:
                        last_entry = self.long_pos_prices[-1]
                        idx = len(self.long_pos_prices) - 1
                        step_cfg = self.config['copy_bottom']
                        step_ticks = step_cfg[idx] if idx < len(step_cfg) else step_cfg[-1]
                        step = step_ticks * price_tick
                        
                        if (last_entry - current_price) >= step:
                            should_buy = True
                            log_msg = "➕ [策略] 网格加多"

                    if should_buy:
                        ok, msg = self._trade_action("OPEN_LONG", ask_price)
                        if ok: self._print_snapshot(f"{log_msg} -> {msg}")
                
                # --- 多单止盈逻辑 ---
                if self.long_pos_prices:
                    last_entry = self.long_pos_prices[-1]
                    dynamic_step = current_price * 0.01
                    
                    if (current_price - last_entry) >= dynamic_step:
                        ok, msg = self._trade_action("CLOSE_LONG", 0) 
                        if ok:
                            self.last_long_exit_price = bid_price 
                            self._print_snapshot(f"➖ [策略] 多单止盈 -> {msg}")

                # 多单连续止盈
                if self.long_pos_prices and self.last_long_exit_price is not None:
                    dynamic_step = current_price * 0.01
                    if (current_price - self.last_long_exit_price) >= dynamic_step:
                        ok, msg = self._trade_action("CLOSE_LONG", 0)
                        if ok:
                            self.last_long_exit_price = bid_price
                            self._print_snapshot(f"🚀 [策略] 多单追踪止盈 -> {msg}")

                # --- 4. 标准网格空单逻辑 ---
                if current_price < ma60 and ma3_curr < ma3_prev and not is_short_banned:
                    should_sell = False
                    log_msg = ""

                    if not self.short_pos_prices:
                        should_sell = True
                        log_msg = "➕ [策略] 首单开空"
                    elif self.short_pos_prices:
                        last_entry = self.short_pos_prices[-1]
                        idx = len(self.short_pos_prices) - 1
                        step_cfg = self.config['copy_top']
                        step_ticks = step_cfg[idx] if idx < len(step_cfg) else step_cfg[-1]
                        step = step_ticks * price_tick
                        
                        if (current_price - last_entry) >= step:
                            should_sell = True
                            log_msg = "➕ [策略] 网格加空"
                    
                    if should_sell:
                        ok, msg = self._trade_action("OPEN_SHORT", bid_price)
                        if ok: self._print_snapshot(f"{log_msg} -> {msg}")

                # --- 空单止盈逻辑 ---
                if self.short_pos_prices:
                    last_entry = self.short_pos_prices[-1]
                    dynamic_step = current_price * 0.01
                    
                    if (last_entry - current_price) >= dynamic_step:
                        ok, msg = self._trade_action("CLOSE_SHORT", 0)
                        if ok:
                            self.last_short_exit_price = ask_price
                            self._print_snapshot(f"➖ [策略] 空单止盈 -> {msg}")

                # 空单连续止盈
                if self.short_pos_prices and self.last_short_exit_price is not None:
                    dynamic_step = current_price * 0.01
                    if (self.last_short_exit_price - current_price) >= dynamic_step:
                        ok, msg = self._trade_action("CLOSE_SHORT", 0)
                        if ok:
                            self.last_short_exit_price = ask_price
                            self._print_snapshot(f"🚀 [策略] 空单追踪止盈 -> {msg}")

                # ==========================================================
                # ============= 状态同步 (兜底) ============================
                # ==========================================================
                # 通常上面的 _trade_action 已经处理了，这里留作双重保险
                # self._sync_actual_position() 

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
    
    SYMBOL = "SHFE.rb2601" #收益率: -5.09%, 年化收益率: -17.02%, 最大回撤: 6.30%, 年化夏普率: -4.2021
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