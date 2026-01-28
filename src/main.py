import time
import json
import logging
import threading
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# 使用当前目录下的 binance_api
from binance_api import BinanceAPI, kline2df

# 设置目录路径
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"

# 确保目录存在
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# 重新配置日志
root_logger = logging.getLogger()
if root_logger.handlers:
    for handler in root_logger.handlers:
        root_logger.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "trading.log"),
        logging.StreamHandler()
    ],
    force=True
)

class RealTimeBuySurgeStrategyV3:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(RealTimeBuySurgeStrategyV3, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, dry_run: bool = True):
        if self._initialized:
            return
            
        self.dry_run = dry_run
        self.api = BinanceAPI()
        self.state_file = DATA_DIR / "trading_state.json"
        
        # 加载状态
        state = self.load_state()
        self.positions = state.get("positions", {})
        self.pending_signals = state.get("pending_signals", [])
        self.history = state.get("history", [])
        
        # === 策略参数 ===
        self.leverage = 4
        self.position_size_ratio = 0.06  # 6%
        self.max_daily_positions = 6     # 最大持仓数
        
        self.buy_surge_threshold = 2.2
        self.buy_surge_max = 3.0
        
        # 风控参数
        self.min_account_ratio = 0.70    # 最小多空比
        self.enable_trader_filter = False 
        
        # 止盈止损
        self.take_profit_pct = 0.33      # 33%
        self.stop_loss_pct = -0.18       # -18%
        
        # 虚拟补仓
        self.enable_add_position = True
        self.add_position_trigger_pct = -0.18 # -18%
        self.use_virtual_add_position = True
        
        # 时间限制
        self.max_hold_hours = 72
        self.wait_timeout_hours = 37     # 信号等待超时
        
        # 弱势平仓
        self.enable_weak_24h_exit = True
        self.weak_24h_threshold = 0.08   # 8%
        
        # 等待回调配置 (倍数, 回调比例)
        self.wait_drop_pct_config = [
            (3, -0.07),     # 2-3倍：等待7%回调
            (5, -0.04),     # 3-5倍：等待4%回调
            (10, -0.03),    # 5-10倍：等待3%回调
            (9999, -0.01),  # 10倍以上：等待1%回调
        ]
        
        # 运行时状态
        self.last_scan_hour = None
        self.is_running = False
        self.stop_event = threading.Event()
        self.thread = None
        self._initialized = True
        
        mode_str = "🟢 模拟模式 (Dry Run)" if self.dry_run else "🔴 实盘模式 (Real Money)"
        logging.info(f"策略初始化完成. 当前模式: {mode_str}")

    def start(self):
        """启动策略线程"""
        if self.is_running:
            logging.warning("策略已经在运行中")
            return

        logging.info("启动实盘策略线程...")
        self.is_running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """停止策略线程"""
        if not self.is_running:
            return

        logging.info("正在停止实盘策略线程...")
        self.is_running = False
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
            self.thread = None
        logging.info("实盘策略线程已停止")

    def get_status(self) -> Dict:
        """获取运行状态"""
        return {
            "is_running": self.is_running,
            "dry_run": self.dry_run,
            "positions_count": len(self.positions),
            "pending_signals_count": len(self.pending_signals),
            "last_scan_hour": self.last_scan_hour
        }

    def log_detailed_status(self):
        """打印详细状态表"""
        # 1. 待建仓信号表 (Pending Entry Signals)
        if self.pending_signals:
            data = []
            for s in self.pending_signals:
                try:
                    curr_price = self.get_current_price(s['symbol'])
                    # 计算距离目标价的百分比
                    dist_pct = (curr_price - s['target_entry_price']) / curr_price if curr_price else 0
                except:
                    curr_price = 0
                    dist_pct = 0
                
                data.append({
                    "Symbol": s['symbol'],
                    "Surge(x)": f"{s['buy_surge_ratio']:.2f}",
                    "SigPrice": s['signal_close'],
                    "TargetEntry": f"{s['target_entry_price']:.4f}",
                    "DropReq": f"{s['drop_pct']*100:.1f}%",
                    "CurrPrice": curr_price,
                    "DistToEntry": f"{dist_pct*100:.1f}%",
                    "Expire": s['timeout_time'].split('T')[1][:5]
                })
            
            df = pd.DataFrame(data)
            try:
                table_str = df.to_markdown(index=False)
            except:
                table_str = df.to_string(index=False)
                
            logging.info(f"\n=== 📋 待建仓信号 (Pending Entries) ===\n{table_str}")

        # 2. 持仓监控表 (Active Positions)
        if self.positions:
            data = []
            for symbol, pos in self.positions.items():
                try:
                    curr_price = self.get_current_price(symbol)
                    entry_price = pos['entry_price']
                    # PnL based on Virtual Entry
                    virtual_entry = pos['virtual_entry_price']
                    pnl_pct = (curr_price - virtual_entry) / virtual_entry if virtual_entry else 0
                    
                    entry_time = datetime.fromisoformat(pos['entry_time'])
                    hold_hours = (datetime.utcnow() - entry_time).total_seconds() / 3600
                    
                    # 动态止盈目标计算
                    current_tp = self.take_profit_pct
                    if hold_hours >= 12 and pos.get('max_up_12h', 0) < 0.025: current_tp = 0.20
                    if hold_hours >= 24 and pos.get('max_up_24h', 0) < 0.05: current_tp = 0.11
                    
                    data.append({
                        "Symbol": symbol,
                        "Entry": f"{entry_price:.4f}",
                        "Curr": f"{curr_price:.4f}",
                        "PnL%": f"{pnl_pct*100:.2f}%",
                        "Hold(h)": f"{hold_hours:.1f}",
                        "MaxUp12h": f"{pos.get('max_up_12h',0)*100:.1f}%",
                        "TP_Target": f"{current_tp*100:.0f}%",
                        "Added?": "Yes" if pos['is_virtual_added'] else "No"
                    })
                except:
                    continue
            
            if data:
                df = pd.DataFrame(data)
                try:
                    table_str = df.to_markdown(index=False)
                except:
                    table_str = df.to_string(index=False)
                logging.info(f"\n=== 🛡 持仓监控 (Active Positions) ===\n{table_str}")

    def _run_loop(self):
        """后台运行循环"""
        logging.info("实盘交易引擎启动...")
        
        while not self.stop_event.is_set():
            try:
                now = datetime.utcnow()
                
                # 1. 每小时第 2 分钟执行全市场扫描
                should_scan = False
                if self.last_scan_hour is None:
                    logging.info("🚀 首次启动，立即执行扫描...")
                    should_scan = True
                elif now.minute == 2 and self.last_scan_hour != now.hour:
                    should_scan = True
                
                if should_scan:
                    self.scan_market()
                    self.last_scan_hour = now.hour
                else:
                    # 仅在未扫描时打印心跳，避免刷屏
                    if now.second % 60 == 0: 
                        logging.info(f"💓 运行中... 下次扫描将在 {now.hour + 1}:02 (当前 {now.strftime('%H:%M')})")
                
                # 2. 每分钟处理待建仓信号
                self.process_pending_signals()
                
                # 3. 每分钟监控持仓
                self.monitor_positions()
                
                # 打印详细状态表
                self.log_detailed_status()
                
                # 休眠 60 秒
                self.stop_event.wait(60)
                
            except Exception as e:
                logging.error(f"主循环出错: {e}")
                import traceback
                logging.error(traceback.format_exc())
                self.stop_event.wait(60)

    def load_state(self) -> Dict:
        """加载状态"""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                logging.info(f"已加载状态: {len(data.get('positions', {}))} 持仓, {len(data.get('pending_signals', []))} 待建仓")
                return data
            except Exception as e:
                logging.error(f"加载状态文件失败: {e}")
                return {}
        return {}

    def save_state(self):
        """保存状态"""
        try:
            data = {
                "positions": self.positions,
                "pending_signals": self.pending_signals,
                "history": self.history,
                "updated_at": datetime.utcnow().isoformat()
            }
            self.state_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logging.error(f"保存状态文件失败: {e}")

    def get_kline_data(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        """获取K线数据"""
        raw_data = self.api.kline_candlestick_data(symbol=symbol, interval=interval, limit=limit)
        if not raw_data:
            return pd.DataFrame()
        return kline2df(raw_data)

    def get_wait_drop_pct(self, buy_surge_ratio: float) -> float:
        """根据买量倍数获取等待回调比例"""
        for max_ratio, drop_pct in self.wait_drop_pct_config:
            if buy_surge_ratio < max_ratio:
                return drop_pct
        return self.wait_drop_pct_config[-1][1]

    def get_current_price(self, symbol: str) -> float:
        """获取当前价格"""
        try:
            response = self.api.client.rest_api.symbol_price_ticker(symbol=symbol)
            data = response.data()
            
            # SDK 可能返回列表或单个对象
            if isinstance(data, list):
                if not data:
                    raise ValueError("Price data is empty list")
                ticker = data[0]
            else:
                ticker = data
                
            # 尝试获取价格
            if hasattr(ticker, 'price'):
                return float(ticker.price)
            elif isinstance(ticker, dict) and 'price' in ticker:
                return float(ticker['price'])
            elif hasattr(ticker, 'actual_instance'):
                inner = ticker.actual_instance
                if hasattr(inner, 'price'):
                    return float(inner.price)
                elif isinstance(inner, dict) and 'price' in inner:
                    return float(inner['price'])
            
            logging.warning(f"Price object structure: {ticker}")
            return 0.0
        except Exception as e:
            logging.error(f"获取价格失败 {symbol}: {e}")
            raise

    def scan_market(self):
        """扫描全市场寻找交易机会"""
        logging.info("🔍 开始全市场扫描...")
        
        symbols = self.api.in_exchange_trading_symbols(symbol_pattern=r"USDT$")
        logging.info(f"获取到 {len(symbols)} 个交易对")
        
        count = 0
        api_call_count = 0 
        
        scan_progress_data = []
        
        for symbol in symbols:
            if self.stop_event.is_set(): break
            
            api_call_count += 1
            if api_call_count % 100 == 0:
                logging.info(f"⏳ API频率保护: 已扫描 {api_call_count} 个，暂停 1s...")
                time.sleep(1)

            if symbol in self.positions:
                continue
            
            try:
                df_1h = self.get_kline_data(symbol, "1h", limit=48)
                if df_1h.empty or len(df_1h) < 25:
                    continue
                
                last_closed_candle = df_1h.iloc[-2]
                current_buy_volume = last_closed_candle['active_buy_volume']
                signal_close = float(last_closed_candle['close'])
                # K线时间是UTC，转换为本地时间 (CST UTC+8)
                signal_time = last_closed_candle['trade_date'] + pd.Timedelta(hours=8)
                
                prev_24h_df = df_1h.iloc[-26:-2] 
                if prev_24h_df.empty:
                    continue
                    
                avg_buy_volume = prev_24h_df['active_buy_volume'].mean()
                
                if avg_buy_volume == 0:
                    continue
                    
                buy_surge_ratio = current_buy_volume / avg_buy_volume
                
                # 收集用于实时显示的数据
                if buy_surge_ratio > 1.5:
                    scan_progress_data.append({
                        "Symbol": symbol,
                        "Price": signal_close,
                        "Surge": f"{buy_surge_ratio:.2f}x",
                        "AvgVol": f"{avg_buy_volume:.1f}",
                        "CurrVol": f"{current_buy_volume:.1f}"
                    })
                    if len(scan_progress_data) >= 5:
                        df_prog = pd.DataFrame(scan_progress_data)
                        try:
                            table_str = df_prog.to_markdown(index=False)
                        except:
                            table_str = df_prog.to_string(index=False)
                        logging.info(f"\n📊 扫描中发现的高买量币种:\n{table_str}")
                        scan_progress_data = [] 

                # 检查信号
                if self.buy_surge_threshold <= buy_surge_ratio <= self.buy_surge_max:
                    logging.info(f"💡 发现潜在信号: {symbol} 买量倍数={buy_surge_ratio:.2f} 价格={signal_close}")
                    
                    if self.enable_trader_filter:
                        ratio = self.api.get_top_long_short_ratio(symbol, period="1h")
                        if ratio > 0 and ratio < self.min_account_ratio:
                            logging.info(f"   ❌ 多空比过滤: {ratio} < {self.min_account_ratio}")
                            continue
                    
                    drop_pct = self.get_wait_drop_pct(buy_surge_ratio)
                    target_price = signal_close * (1 + drop_pct)
                    
                    timeout_time = datetime.utcnow() + timedelta(hours=self.wait_timeout_hours)
                    
                    signal_info = {
                        "symbol": symbol,
                        "signal_time": signal_time.isoformat(),
                        "signal_close": signal_close,
                        "buy_surge_ratio": buy_surge_ratio,
                        "target_entry_price": target_price,
                        "drop_pct": drop_pct,
                        "timeout_time": timeout_time.isoformat(),
                        "created_at": datetime.utcnow().isoformat()
                    }
                    
                    existing_index = next((i for i, s in enumerate(self.pending_signals) if s['symbol'] == symbol), -1)
                    if existing_index != -1:
                        old_signal = self.pending_signals[existing_index]
                        logging.info(f"   🔄 更新信号 {symbol}: 目标价 {old_signal['target_entry_price']:.4f} -> {target_price:.4f}")
                        
                        # 保留已有的实时数据字段，避免被覆盖
                        if 'current_price' in old_signal:
                            signal_info['current_price'] = old_signal['current_price']
                        if 'distance_pct' in old_signal:
                            signal_info['distance_pct'] = old_signal['distance_pct']
                            
                        self.pending_signals[existing_index] = signal_info
                    else:
                        self.pending_signals.append(signal_info)
                        logging.info(f"   ✅ 加入等待列表: 目标价 {target_price:.6f} (回调 {drop_pct*100:.1f}%)")
                        count += 1
                    
            except Exception as e:
                logging.error(f"扫描 {symbol} 出错: {e}")
                continue
        
        if scan_progress_data:
            df_prog = pd.DataFrame(scan_progress_data)
            try:
                table_str = df_prog.to_markdown(index=False)
            except:
                table_str = df_prog.to_string(index=False)
            logging.info(f"\n📊 扫描中发现的高买量币种 (剩余):\n{table_str}")

        self.save_state()
        logging.info(f"扫描结束，新增 {count} 个信号，当前等待: {len(self.pending_signals)}")

    def process_pending_signals(self):
        """处理待建仓信号"""
        if not self.pending_signals:
            return
            
        logging.info(f"🔄 检查待建仓信号 ({len(self.pending_signals)}个)...")
        now = datetime.now()
        remaining_signals = []
        
        for signal in self.pending_signals:
            symbol = signal['symbol']
            target_price = signal['target_entry_price']
            timeout_time = datetime.fromisoformat(signal['timeout_time'])
            
            if now > timeout_time:
                logging.info(f"⏰ 信号超时移除: {symbol}")
                continue
                
            if len(self.positions) >= self.max_daily_positions:
                remaining_signals.append(signal)
                continue
            
            try:
                current_price = self.get_current_price(symbol)
                
                # 更新实时信息到状态中，供看板使用
                signal['current_price'] = current_price
                if current_price > 0:
                    signal['distance_pct'] = (current_price - target_price) / current_price
                else:
                    signal['distance_pct'] = 0

                if current_price <= target_price:
                    logging.info(f"🚀 触发建仓: {symbol} 现价{current_price} <= 目标{target_price}")
                    self.open_position(symbol, current_price, signal)
                else:
                    remaining_signals.append(signal)
                    
            except Exception as e:
                logging.error(f"检查信号 {symbol} 失败: {e}")
                remaining_signals.append(signal)
        
        self.pending_signals = remaining_signals
        self.save_state()

    def open_position(self, symbol: str, price: float, signal_info: Dict):
        """执行开仓"""
        quantity = 0.0
        
        try:
            balance = self.api.get_account_balance()
            if balance <= 0 and not self.dry_run:
                logging.error("账户余额不足")
                return
            
            if self.dry_run: balance = 10000.0
                
            position_amount = balance * self.position_size_ratio * self.leverage
            quantity = position_amount / price
            
            logging.info(f"准备下单 {symbol}: 数量={quantity:.4f}, 金额={position_amount:.2f}")
            
            real_entry_price = price
            
            if not self.dry_run:
                self.api.change_leverage(symbol, self.leverage)
                self.api.change_margin_type(symbol, "ISOLATED")
                
                response = self.api.post_order(
                    symbol=symbol,
                    side="BUY",
                    ord_type="MARKET",
                    quantity=quantity
                )
                real_entry_price = float(response.get('avgPrice', price))
                quantity = float(response.get('executedQty', quantity))
            else:
                logging.info(f"[模拟] 下单成功: {symbol} BUY {quantity}")
            
            self.positions[symbol] = {
                "symbol": symbol,
                "entry_time": datetime.utcnow().isoformat(),
                "signal_time": signal_info.get('signal_time'),
                "entry_price": real_entry_price,
                "quantity": quantity,
                "buy_surge_ratio": signal_info['buy_surge_ratio'],
                "virtual_entry_price": real_entry_price, 
                "is_virtual_added": False,
                "max_up_12h": 0.0, 
                "max_up_24h": 0.0
            }
            self.save_state()
            
        except Exception as e:
            logging.error(f"开仓失败 {symbol}: {e}")

    def monitor_positions(self):
        """监控持仓"""
        if not self.positions:
            return
            
        logging.info(f"🛡 监控持仓 ({len(self.positions)}个)...")
        
        for symbol in list(self.positions.keys()):
            try:
                pos = self.positions[symbol]
                current_price = self.get_current_price(symbol)
                pos['current_price'] = current_price # 保存当前价到状态
                entry_time = datetime.fromisoformat(pos['entry_time'])
                hold_hours = (datetime.now() - entry_time).total_seconds() / 3600
                entry_price = pos['entry_price']
                current_up = (current_price - entry_price) / entry_price
                
                if hold_hours <= 12:
                    pos['max_up_12h'] = max(pos.get('max_up_12h', 0), current_up)
                if hold_hours <= 24:
                    pos['max_up_24h'] = max(pos.get('max_up_24h', 0), current_up)
                
                virtual_entry = pos['virtual_entry_price']
                pnl_pct = (current_price - virtual_entry) / virtual_entry
                
                # 动态止盈
                current_tp = self.take_profit_pct
                if hold_hours >= 12 and pos.get('max_up_12h', 0) < 0.025: 
                    current_tp = 0.20 
                if hold_hours >= 24 and pos.get('max_up_24h', 0) < 0.05: 
                    current_tp = 0.11 
                
                if pnl_pct >= current_tp:
                    self.close_position(symbol, f"take_profit_dynamic_{current_tp*100:.0f}%", current_price)
                    continue
                    
                # 虚拟补仓
                if not pos['is_virtual_added'] and pnl_pct <= self.add_position_trigger_pct:
                    logging.info(f"📉 {symbol} 触发虚拟补仓! 当前跌幅 {pnl_pct*100:.2f}%")
                    new_virtual = (virtual_entry + current_price) / 2
                    self.positions[symbol]['virtual_entry_price'] = new_virtual
                    self.positions[symbol]['is_virtual_added'] = True
                    self.save_state()
                    continue
                
                # 真实止损
                if pnl_pct <= self.stop_loss_pct:
                    self.close_position(symbol, "stop_loss", current_price)
                    continue
                
                # 时间止损
                if hold_hours >= self.max_hold_hours:
                    self.close_position(symbol, "timeout_72h", current_price)
                    continue
                    
                # 弱势平仓
                if self.enable_weak_24h_exit and hold_hours >= 24:
                    if pos.get('max_up_24h', 0) < self.weak_24h_threshold:
                         self.close_position(symbol, "weak_trend_24h", current_price)
                         continue

            except Exception as e:
                logging.error(f"监控 {symbol} 失败: {e}")
        
        self.save_state()

    def close_position(self, symbol: str, reason: str, price: float):
        """平仓"""
        try:
            pos = self.positions[symbol]
            quantity = pos['quantity']
            
            logging.info(f"执行平仓 {symbol}: 原因={reason}, 价格={price}")
            
            # 计算盈亏记录到历史
            entry_price = pos.get('entry_price', price)
            pnl_pct = (price - entry_price) / entry_price
            
            history_entry = {
                "symbol": symbol,
                "reason": reason,
                "entry_price": entry_price,
                "exit_price": price,
                "pnl_pct": pnl_pct,
                "entry_time": pos.get('entry_time'),
                "exit_time": datetime.utcnow().isoformat(),
                "quantity": pos.get('quantity')
            }
            self.history.insert(0, history_entry) # 新的排在前面
            self.history = self.history[:100] # 只保留最近100条
            
            if not self.dry_run:
                self.api.post_order(
                    symbol=symbol,
                    side="SELL", 
                    ord_type="MARKET",
                    quantity=0,
                    close_position=True
                )
            else:
                logging.info(f"[模拟] 平仓成功: {symbol}")
                
            del self.positions[symbol]
            self.save_state()
            
        except Exception as e:
            logging.error(f"平仓失败 {symbol}: {e}")

if __name__ == "__main__":
    # 默认开启 DRY_RUN 模式，安全第一
    # 如果要实盘，请修改为 dry_run=False
    trader = RealTimeBuySurgeStrategyV3(dry_run=True)
    
    logging.info("========================================")
    logging.info("   RealTime Buy Surge Strategy V3   ")
    logging.info("   Based on hm_20260126.py logic    ")
    logging.info("========================================")
    
    trader.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        trader.stop()
