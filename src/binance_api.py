import os
import logging
import re
from pathlib import Path
from typing import Optional, List
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

    def get_exchange_info(self) -> dict:
        """获取交易所信息（带简单缓存）"""
        if self._exchange_info_cache:
            return self._exchange_info_cache
        try:
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
            self.client.rest_api.change_initial_leverage(symbol=symbol, leverage=leverage)
            logging.info(f"已设置 {symbol} 杠杆为 {leverage}x")
        except Exception as e:
            logging.error(f"设置杠杆失败: {e}")

    def change_margin_type(self, symbol: str, margin_type: str = "ISOLATED"):
        """调整保证金模式 (ISOLATED/CROSSED)"""
        try:
            # 使用 Enum 转换参数
            margin_type_enum = ChangeMarginTypeMarginTypeEnum(margin_type.upper())
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
        close_position: bool = False
    ):
        """发送订单 (增强版)"""
        try:
            # 1. 如果是平仓单，自动获取持仓数量
            if close_position:
                positions = self.get_position_risk(symbol=symbol)
                target_pos = next((p for p in positions if float(p.get('positionAmt', 0)) != 0), None)
                
                if not target_pos:
                    raise ValueError(f"未找到 {symbol} 的持仓，无法执行自动平仓")
                
                pos_amt = float(target_pos['positionAmt'])
                side = "SELL" if pos_amt > 0 else "BUY"
                quantity = abs(pos_amt)
                reduce_only = True
                logging.info(f"自动平仓模式: {symbol} 持仓={pos_amt} -> 下单 {side} {quantity}")

            # 2. 获取交易对过滤器信息 (精度)
            tick_size, step_size = self.get_symbol_filters(symbol)
            
            # 3. 调整价格精度
            if price is not None and tick_size:
                original_price = price
                price = self.adjust_precision(price, tick_size)
                if price != original_price:
                    logging.info(f"价格精度调整: {original_price} -> {price}")
            
            if stop_price is not None and tick_size:
                stop_price = self.adjust_precision(stop_price, tick_size)

            # 4. 调整数量精度
            if quantity > 0 and step_size:
                original_qty = quantity
                quantity = self.adjust_precision(quantity, step_size)
                if quantity != original_qty:
                    logging.info(f"数量精度调整: {original_qty} -> {quantity}")
            
            if quantity <= 0:
                raise ValueError(f"下单数量无效: {quantity}")

            # 5. 构建参数
            params = {
                "symbol": symbol,
                "type": ord_type,
                "quantity": quantity,
            }

            # 处理订单方向 (Side)
            try:
                side_enum = NewOrderSideEnum(side.upper())
                params["side"] = side_enum
            except ValueError:
                logging.warning(f"无效的 Side: {side}, 尝试直接使用字符串")
                params["side"] = side
            
            # 处理价格
            if price is not None:
                params["price"] = price
                if "MARKET" not in ord_type:
                    try:
                        tif_enum = NewOrderTimeInForceEnum(time_in_force)
                        params["time_in_force"] = tif_enum
                    except ValueError:
                        params["time_in_force"] = NewOrderTimeInForceEnum.GTC
            elif ord_type == "LIMIT":
                raise ValueError("LIMIT 订单必须指定 price")
            
            if stop_price is not None:
                params["stop_price"] = stop_price
                
            if reduce_only:
                params["reduce_only"] = "true"

            # 6. 发送订单
            response = self.client.rest_api.new_order(**params)
            logging.info(f"下单成功: {symbol} {side} {ord_type} {quantity}")
            return response.data()
            
        except Exception as e:
            logging.error(f"下单失败: {symbol} {side} {ord_type} {quantity} - {e}")
            raise

    def get_account_balance(self) -> float:
        """获取 USDT 可用余额"""
        try:
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
            if symbol:
                response = self.client.rest_api.position_information_v2(symbol=symbol)
            else:
                response = self.client.rest_api.position_information_v2()
            
            data = response.data()
            return [pos.to_dict() for pos in data]
        except Exception as e:
            logging.error(f"获取持仓失败: {e}")
            return []

    def get_top_long_short_ratio(self, symbol: str, period: str = "5m", limit: int = 1) -> float:
        """获取顶级交易者账户多空比"""
        try:
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
