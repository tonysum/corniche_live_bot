import streamlit as st
import json
import pandas as pd
from pathlib import Path
import time
import os
from datetime import datetime

# 设置页面配置
st.set_page_config(
    page_title="Corniche Live Bot Monitor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 路径设置
BASE_DIR = Path(__file__).parent.parent
LOG_FILE = BASE_DIR / "logs" / "trading.log"
STATE_FILE = BASE_DIR / "data" / "trading_state.json"

def load_state():
    """加载状态文件"""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception as e:
            st.error(f"Error loading state: {e}")
            return {}
    return {}

def load_logs(lines=100):
    """加载最近的日志"""
    if LOG_FILE.exists():
        try:
            # 读取最后 N 行
            # 使用简单的读取方式，如果文件很大可能需要优化
            with open(LOG_FILE, 'r') as f:
                content = f.readlines()
                return "".join(content[-lines:])
        except Exception as e:
            return f"Error reading logs: {e}"
    return "No log file found."

# === 侧边栏 ===
st.sidebar.title("Corniche Bot")
auto_refresh = st.sidebar.checkbox("Auto Refresh (10s)", value=True)

# === 主界面 ===
st.title("📈 实盘交易监控看板")

# 加载数据
state = load_state()
positions = state.get("positions", {})
pending = state.get("pending_signals", [])
updated_at = state.get("updated_at", "Unknown")

# 顶部指标
col1, col2, col3, col4 = st.columns(4)
col1.metric("持仓数量", len(positions))
col2.metric("待建仓信号", len(pending))
col3.metric("最后更新", updated_at.split('T')[1][:8] if 'T' in updated_at else updated_at)

# 1. 持仓管理
st.subheader("🛡 当前持仓 (Positions)")
if positions:
    pos_data = []
    for symbol, p in positions.items():
        entry_time = p.get('entry_time', '')
        # 计算持仓时间
        hold_time_str = "N/A"
        if entry_time:
            try:
                et = datetime.fromisoformat(entry_time)
                duration = datetime.now() - et
                hours = duration.total_seconds() / 3600
                hold_time_str = f"{hours:.1f}h"
            except:
                pass
                
        pos_data.append({
            "Symbol": symbol,
            "Entry Price": p.get('entry_price'),
            "Quantity": p.get('quantity'),
            "Virtual Entry": p.get('virtual_entry_price'),
            "Added?": "✅" if p.get('is_virtual_added') else "❌",
            "Hold Time": hold_time_str,
            "Max Up 12h": f"{p.get('max_up_12h', 0)*100:.1f}%",
            "Max Up 24h": f"{p.get('max_up_24h', 0)*100:.1f}%"
        })
    st.dataframe(pd.DataFrame(pos_data), use_container_width=True)
else:
    st.info("当前无持仓")

# 2. 待建仓信号
st.subheader("📋 待建仓信号 (Pending Signals)")
if pending:
    pend_data = []
    for p in pending:
        # 计算倒计时
        timeout = p.get('timeout_time', '')
        expire_in = "N/A"
        if timeout:
            try:
                to = datetime.fromisoformat(timeout)
                diff = to - datetime.now()
                if diff.total_seconds() > 0:
                    expire_in = f"{diff.total_seconds()/3600:.1f}h"
                else:
                    expire_in = "Expired"
            except:
                pass
                
        pend_data.append({
            "Symbol": p.get('symbol'),
            "Signal Close": p.get('signal_close'),
            "Surge Ratio": f"{p.get('buy_surge_ratio', 0):.2f}x",
            "Target Price": p.get('target_entry_price'),
            "Drop Required": f"{p.get('drop_pct', 0)*100:.1f}%",
            "Current Price": p.get('current_price'),
            "Distance": f"{p.get('distance_pct', 0)*100:.1f}%",
            "Signal Time": p.get('signal_time', '').replace('T', ' '),
            "Timeout Time": p.get('timeout_time', '').split('.')[0].replace('T', ' '),
            "Expire In": expire_in,
            "Created At": p.get('created_at', '').split('.')[0].replace('T', ' ')
        })
    st.dataframe(pd.DataFrame(pend_data), use_container_width=True)
else:
    st.info("当前无等待信号")

# 3. 实时日志
st.subheader("📝 运行日志 (Latest 100 lines)")
logs = load_logs(100)
st.code(logs, language="text")

# 底部说明
st.markdown("---")
st.caption(f"Server Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if auto_refresh:
    time.sleep(10)
    st.rerun()

