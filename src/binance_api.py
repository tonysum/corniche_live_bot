import os
import logging
import re
from pathlib import Path
from typing import Optional, List, Any, Dict
import math
import pandas as pd
from dotenv import load_dotenv

from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
    ConfigurationRestAPI,
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL,
)
from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
    KlineCandlestickDataIntervalEnum,
    TopTraderLongShortRatioPositionsPeriodEnum
)
from binance_sdk_derivatives_trading_usds_futures.rest_api.models.enums import (
    NewOrderTimeInForceEnum,
    NewOrderSideEnum,
    ChangeMarginTypeMarginTypeEnum
)

# 🔧 加载 .env 文件 (从项目根目录)
# 假设当前文件在 src/binance_api.py
src_dir = Path(__file__).parent
project_root = src_dir.parent
env_path = project_root / '.env'

if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    # logging.info(f"已加载环境变量文件: {env_path}")
else:
    # 尝试默认路径 (如果作为独立包运行)
    load_dotenv()

# Configure logging (will be overridden by main app usually)
logging.basicConfig(level=logging.INFO)

def snake_to_camel(snake_str: str) -> str:
    """将snake_case转换为camelCase"""
    components = snake_str.split('_')
    return components[0] + ''.join(x.capitalize() for x in components[1:])

def convert_dict_keys(data: Any, convert_func=snake_to_camel) -> Any:
    """递归转换字典的键名"""
    if isinstance(data, dict):
        return {convert_func(k): convert_dict_keys(v, convert_func) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_dict_keys(item, convert_func) for item in data]
    else:
        return data

class BinanceAPI:
    """币安API客户端封装类"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_path: Optional[str] = None
    ):
        """
        初始化币安API客户端
        """
        self.api_key = api_key or os.getenv("BINANCE_API_KEY")
        self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET")
        self.base_path = base_path or os.getenv("BASE_PATH", DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL)
        
        if not self.api_key:
            raise ValueError("BINANCE_API_KEY 未设置。请在 .env 文件中配置。")
        if not self.api_secret:
            raise ValueError("BINANCE_API_SECRET 未设置。请在 .env 文件中配置。")
        
        # 创建配置和客户端
        configuration_rest_api = ConfigurationRestAPI(
            api_key=self.api_key,
            api_secret=self.api_secret,
            base_path=self.base_path
        )
        self.client = DerivativesTradingUsdsFutures(config_rest_api=configuration_rest_api)
        self._exchange_info_cache = None
        
        # 权重控制
        self.used_weight = 0
        self.max_weight = 1200
        self.last_weight_reset = pd.Timestamp.now()

    def _check_weight(self, weight: int = 1):
        """简单的权重检查与限速"""
        now = pd.Timestamp.now()
        # 每分钟重置权重
        if (now - self.last_weight_reset).total_seconds() > 60:
            self.used_weight = 0
            self.last_weight_reset = now
            
        if self.used_weight + weight > self.max_weight * 0.9: # 预留10%缓冲
            sleep_time = 60 - (now - self.last_weight_reset).total_seconds()
            if sleep_time > 0:
                logging.warning(f"⚠️ API权重接近临界值 ({self.used_weight}), 暂停 {sleep_time:.1f}s")
                import time
                time.sleep(sleep_time)
                self.used_weight = 0
                self.last_weight_reset = pd.Timestamp.now()
        
        self.used_weight += weight

    def get_exchange_info(self) -> dict:
        """获取交易所信息（带简单缓存）"""
        if self._exchange_info_cache:
            return self._exchange_info_cache
        try:
            self._check_weight(1)
            response = self.client.rest_api.exchange_information()
            self._exchange_info_cache = response.data()
            return self._exchange_info_cache
        except Exception as e:
            logging.error(f"获取交易所信息失败: {e}")
            return {}

    def get_symbol_filters(self, symbol: str) -> tuple:
        """获取交易对的精度过滤器"""
        exchange_info = self.get_exchange_info()
        if not exchange_info or not hasattr(exchange_info, 'symbols'):
            return None, None
            
        for s in exchange_info.symbols:
            if s.symbol == symbol:
                tick_size = None
                step_size = None
                for f in s.filters:
                    if f.filter_type == 'PRICE_FILTER':
                        tick_size = float(f.tick_size)
                    elif f.filter_type == 'LOT_SIZE':
                        step_size = float(f.step_size)
                return tick_size, step_size
        return None, None

    def adjust_precision(self, value: float, step_size: float) -> float:
        """调整精度"""
        if step_size <= 0 or value <= 0:
            return value
        
        # 计算精度位数
        step_str = f"{step_size:.10f}".rstrip('0').rstrip('.')
        if '.' in step_str:
            precision = len(step_str.split('.')[1])
        else:
            precision = 0
            
        # 向下取整
        adjusted = math.floor(value / step_size) * step_size
        return round(adjusted, precision)

    def change_leverage(self, symbol: str, leverage: int):
        """调整杠杆倍数"""
        try:
            self._check_weight(1)
            self.client.rest_api.change_initial_leverage(symbol=symbol, leverage=leverage)
            logging.info(f"已设置 {symbol} 杠杆为 {leverage}x")
        except Exception as e:
            logging.error(f"设置杠杆失败: {e}")

    def change_margin_type(self, symbol: str, margin_type: str = "ISOLATED"):
        """调整保证金模式 (ISOLATED/CROSSED)"""
        try:
            # 使用 Enum 转换参数
            margin_type_enum = ChangeMarginTypeMarginTypeEnum(margin_type.upper())
            self._check_weight(1)
            self.client.rest_api.change_margin_type(symbol=symbol, margin_type=margin_type_enum)
            logging.info(f"已设置 {symbol} 保证金模式为 {margin_type}")
        except ValueError:
             logging.error(f"无效的保证金模式: {margin_type}")
        except Exception as e:
            # 如果已经是该模式，API会报错 "No need to change margin type"，可以忽略
            if "No need to change" not in str(e):
                logging.error(f"设置保证金模式失败: {e}")

    def in_exchange_trading_symbols(
        self,
        symbol_pattern: str = r"usdt$",
        status: str = "TRADING"
    ) -> List[str]:
        """获取币安交易所所有合约交易对"""
        try:
            self._check_weight(1)
            response = self.client.rest_api.exchange_information()
            data = response.data()
            usdt_symbols = [
                t.symbol for t in data.symbols
                if re.search(symbol_pattern, t.symbol, flags=re.IGNORECASE) and t.status == status
            ]
            return usdt_symbols
        except Exception as e:
            logging.error(f"exchange_info() error: {e}")
            return []
    
    def kline_candlestick_data(
        self,
        symbol: str,
        interval: str,
        starttime: Optional[int] = None,
        endtime: Optional[int] = None,
        limit: Optional[int] = None
    ):
        """获取K线数据"""
        try:
            self._check_weight(1)
            response = self.client.rest_api.kline_candlestick_data(
                symbol=symbol,
                interval=interval,
                start_time=starttime,
                end_time=endtime,
                limit=limit,
            )
            data = response.data()
            return data
        except Exception as e:
            logging.error(f"kline_candlestick_data() error: {e}")
            return None
    
    def post_order(
        self,
        symbol: str,
        side: str,
        ord_type: str,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        close_position: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """发送订单 (重构版 - 参照 binance-order)"""
        try:
            # 1. 平仓逻辑增强
            if close_position:
                positions = self.get_position_risk(symbol=symbol)
                target_pos = next((p for p in positions if float(p.get('positionAmt', 0)) != 0), None)
                
                if not target_pos:
                    raise ValueError(f"未找到 {symbol} 的持仓，无法执行自动平仓")
                
                pos_amt = float(target_pos['positionAmt'])
                side = "SELL" if pos_amt > 0 else "BUY"
                quantity = abs(pos_amt)
                reduce_only = True
                logging.info(f"🔄 自动平仓模式: {symbol} 持仓={pos_amt} -> 下单 {side} {quantity}")

            # 2. 获取并应用精度过滤器
            tick_size, step_size = self.get_symbol_filters(symbol)
            
            if price is not None and tick_size:
                original_price = price
                price = self.adjust_precision(price, tick_size)
                if abs(price - original_price) > tick_size * 0.1:
                    logging.info(f"⚖️ 价格精度调整: {original_price} -> {price} (tick: {tick_size})")
            
            if stop_price is not None and tick_size:
                stop_price = self.adjust_precision(stop_price, tick_size)
            
            if quantity > 0 and step_size:
                original_qty = quantity
                quantity = self.adjust_precision(quantity, step_size)
                if abs(quantity - original_qty) > step_size * 0.1:
                    logging.info(f"⚖️ 数量精度调整: {original_qty} -> {quantity} (step: {step_size})")
            
            if quantity <= 0:
                raise ValueError(f"下单数量无效: {quantity} (调整自 {original_qty if 'original_qty' in locals() else 'None'})")

            # 3. 验证名义价值 (Notional Value >= 100 USDT)
            # 注意：仅在非 reduce_only 且有价格信息时验证
            if not reduce_only and price is not None:
                notional = quantity * price
                if notional < 100:
                    logging.warning(f"⚠️ 订单名义价值 {notional:.2f} USDT 低于 100 USDT，可能会被交易所拒绝")

            # 4. 构建参数 (使用 SDK 要求的 snake_case)
            params = {
                "symbol": symbol,
                "side": side.upper(),
                "type": ord_type.upper(),
                "quantity": quantity,
            }

            if price is not None:
                params["price"] = price
                if "MARKET" not in ord_type.upper():
                    params["time_in_force"] = time_in_force.upper()
            
            if stop_price is not None:
                params["stop_price"] = stop_price
                
            if reduce_only:
                params["reduce_only"] = "true"
            
            # 合并额外参数
            for k, v in kwargs.items():
                params[k] = v

            # 5. 执行下单
            self._check_weight(1)
            response = self.client.rest_api.new_order(**params)
            
            # 6. 处理响应并转换格式
            data = response.data()
            if hasattr(data, 'model_dump'):
                data = data.model_dump()
            elif hasattr(data, 'dict'):
                data = data.dict()
            
            logging.info(f"✅ 下单成功: {symbol} {side} {ord_type} {quantity}")
            return convert_dict_keys(data)
            
        except Exception as e:
            logging.error(f"❌ 下单失败: {symbol} {side} {ord_type} - {e}")
            raise
    
    def get_account_balance(self) -> float:
        """获取 USDT 可用余额"""
        try:
            self._check_weight(5)
            response = self.client.rest_api.futures_account_balance_v2()
            data = response.data()
            for asset in data:
                if asset.asset == "USDT":
                    return float(asset.available_balance)
            return 0.0
        except Exception as e:
            logging.error(f"获取余额失败: {e}")
            return 0.0

    def get_position_risk(self, symbol: Optional[str] = None) -> List[dict]:
        """获取持仓风险信息"""
        try:
            self._check_weight(5)
            if symbol:
                response = self.client.rest_api.position_information_v2(symbol=symbol)
            else:
                response = self.client.rest_api.position_information_v2()
            
            data = response.data()
            # 转换为字典列表并统一键名格式
            result = []
            for pos in data:
                pos_dict = pos.model_dump() if hasattr(pos, 'model_dump') else pos.to_dict() if hasattr(pos, 'to_dict') else pos
                result.append(convert_dict_keys(pos_dict))
            return result
        except Exception as e:
            logging.error(f"获取持仓失败: {e}")
            return []

    def get_top_long_short_ratio(self, symbol: str, period: str = "5m", limit: int = 1) -> float:
        """获取顶级交易者账户多空比"""
        try:
            self._check_weight(1)
            response = self.client.rest_api.top_trader_long_short_ratio_accounts(
                symbol=symbol,
                period=period,
                limit=limit
            )
            data = response.data()
            if data and len(data) > 0:
                item = data[-1]
                if isinstance(item, dict):
                    return float(item.get('longShortRatio', -1.0))
                else:
                    return float(getattr(item, 'long_short_ratio', -1.0))
            return -1.0
        except Exception as e:
            logging.error(f"获取多空比失败: {symbol} - {e}")
            return -1.0

def kline2df(data) -> pd.DataFrame:
    """K线数据转换为DataFrame"""
    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close",
        "volume", "close_time", "quote_volume", "trade_count",
        "active_buy_volume", "active_buy_quote_volume", "reserved_field"
    ])
   
    # 数据类型转换
    numeric_cols = ["open", "high", "low", "close", "volume", "quote_volume", 
                    "active_buy_volume", "active_buy_quote_volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col])
    
    # 时间戳转换
    df["trade_date"] = pd.to_datetime(df["open_time"] // 1000, unit="s")
        
    return df
