import streamlit as st
import json
import pandas as pd
from pathlib import Path
import time
import os
from datetime import datetime, timedelta

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
auto_refresh = st.sidebar.checkbox("Auto Refresh (50s)", value=True)

# === 主界面 ===
st.title("📈 实盘交易监控看板")

# 加载数据
state = load_state()
positions = state.get("positions", {})
pending = state.get("pending_signals", [])
history = state.get("history", [])
updated_at = state.get("updated_at", "Unknown")

# 顶部指标
col1, col2, col3, col4 = st.columns(4)
col1.metric("持仓数量", len(positions))
col2.metric("待建仓信号", len(pending))

# 处理更新时间显示
if updated_at and updated_at != "Unknown":
    try:
        utc_dt = datetime.fromisoformat(updated_at)
        bj_dt = utc_dt + timedelta(hours=8)
        
        # 使用 HTML 自定义显示，支持多行显示以适应小屏幕
        col3.markdown(
            f"""
            <div style="font-size: 14px; opacity: 0.6; margin-bottom: 4px;">最后更新</div>
            <div style="font-size: 22px; font-weight: 600; line-height: 1.4;">
                {utc_dt.strftime('%H:%M:%S')} <span style="font-size: 0.6em; opacity: 0.6;">UTC</span><br>
                {bj_dt.strftime('%H:%M:%S')} <span style="font-size: 0.6em; opacity: 0.6;">BJ</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    except:
        col3.metric("最后更新", updated_at)
else:
    col3.metric("最后更新", updated_at)

# 1. 持仓管理
st.subheader("🛡 当前持仓 (Positions)")
if positions:
    pos_data = []
    for symbol, p in positions.items():
        entry_time = p.get('entry_time', '')
        # 计算持仓时间
        hold_time_str = "N/A"
        hours = 0
        if entry_time:
            try:
                et = datetime.fromisoformat(entry_time)
                duration = datetime.utcnow() - et
                hours = duration.total_seconds() / 3600
                hold_time_str = f"{hours:.1f}h"
            except:
                pass
        
        # 计算预计平仓价 (复制 main.py 逻辑)
        current_tp = 0.33 # 默认 33%
        max_up_12h = p.get('max_up_12h', 0)
        max_up_24h = p.get('max_up_24h', 0)
        
        if hours >= 12 and max_up_12h < 0.025:
            current_tp = 0.20
        if hours >= 24 and max_up_24h < 0.05:
            current_tp = 0.11
        
        virtual_entry = p.get('virtual_entry_price', p.get('entry_price', 0))
        target_exit_price = virtual_entry * (1 + current_tp)
        
        # 计算距离平仓百分比
        current_price = p.get('current_price', 0)
        dist_to_exit = 0
        if current_price > 0:
            dist_to_exit = (target_exit_price - current_price) / current_price
        
        # 计算当前盈亏
        current_pnl = 0
        if virtual_entry > 0 and current_price > 0:
            current_pnl = (current_price - virtual_entry) / virtual_entry

        pos_data.append({
            "Symbol": symbol,
            "Current Price": f"{current_price:.4f}" if current_price else "N/A",
            "PnL %": f"{current_pnl*100:.2f}%",
            "Target Exit": f"{target_exit_price:.4f}",
            "Dist to Exit": f"{dist_to_exit*100:.1f}%",
            "Hold Time": hold_time_str,
            "Max Up 12h": f"{max_up_12h*100:.1f}%",
            "Max Up 24h": f"{max_up_24h*100:.1f}%",
            "Virtual Entry": f"{virtual_entry:.4f}",
            "Added?": "✅" if p.get('is_virtual_added') else "❌"
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
                diff = to - datetime.utcnow()
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

# 3. 历史成交
st.subheader("📊 历史成交 (Trade History)")
if history:
    hist_data = []
    for h in history:
        # 格式化 PnL 颜色
        pnl = h.get('pnl_pct', 0)
        pnl_str = f"{pnl*100:.2f}%"
        
        hist_data.append({
            "Symbol": h.get('symbol'),
            "Reason": h.get('reason'),
            "Entry Price": f"{h.get('entry_price', 0):.4f}",
            "Exit Price": f"{h.get('exit_price', 0):.4f}",
            "PnL %": pnl_str,
            "Entry Time": h.get('entry_time', '').replace('T', ' ').split('.')[0],
            "Exit Time": h.get('exit_time', '').replace('T', ' ').split('.')[0]
        })
    st.dataframe(pd.DataFrame(hist_data), use_container_width=True)
else:
    st.info("暂无历史成交记录")

# 4. 实时日志
st.subheader("📝 运行日志 (Latest 100 lines)")
logs = load_logs(100)
st.code(logs, language="text")

# 底部说明
st.markdown("---")
utc_now = datetime.utcnow()
bj_now = utc_now + timedelta(hours=8)
st.caption(f"Server Time: {utc_now.strftime('%Y-%m-%d %H:%M:%S')} (UTC) / {bj_now.strftime('%Y-%m-%d %H:%M:%S')} (BJ)")

if auto_refresh:
    time.sleep(50)
    st.rerun()

