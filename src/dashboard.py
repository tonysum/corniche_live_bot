import streamlit as st
import json
import pandas as pd
from pathlib import Path
import time
import os
from datetime import datetime, timedelta, UTC
from collections import deque

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

def save_command(cmd):
    """保存指令到状态文件"""
    try:
        state = load_state()
        if "pending_commands" not in state:
            state["pending_commands"] = []
        state["pending_commands"].append(cmd)
        STATE_FILE.write_text(json.dumps(state, indent=2))
        return True
    except Exception as e:
        st.error(f"发送指令失败: {e}")
        return False

def load_logs(lines=100):
    """加载最近的日志"""
    if LOG_FILE.exists():
        try:
            # 读取最后 N 行
            # 使用简单的读取方式，如果文件很大可能需要优化
            with open(LOG_FILE, 'r') as f:
                return "".join(deque(f, lines))
        except Exception as e:
            return f"Error reading logs: {e}"
    return "No log file found."

@st.fragment(run_every=50)
def sidebar_status():
    state = load_state()
    last_heartbeat = state.get("last_heartbeat", "Unknown")
    is_dry_run = state.get("is_dry_run", True)
    
    st.subheader("🤖 运行状态")
    mode_str = "🟢 模拟模式 (Dry Run)" if is_dry_run else "🔴 实盘模式 (LIVE)"
    st.info(f"当前模式: {mode_str}")

    if last_heartbeat != "Unknown":
        try:
            hb_dt = datetime.fromisoformat(last_heartbeat).replace(tzinfo=UTC)
            diff = (datetime.now(UTC) - hb_dt).total_seconds()
            if diff < 120:
                st.success(f"引擎在线\n心跳: {diff:.0f}s ago")
            else:
                st.error(f"引擎离线?\n最后心跳: {diff:.0f}s ago")
        except:
            st.warning("心跳异常")

# === 侧边栏：长期稳定项 ===
st.sidebar.title("Corniche Bot")
auto_refresh = st.sidebar.checkbox("Auto Refresh (50s)", value=True)

with st.sidebar:
    if auto_refresh:
        sidebar_status()
    else:
        sidebar_status()

# 侧边栏：手动下单 (放在外面保证输入不被打断)
st.sidebar.markdown("---")
st.sidebar.subheader("🎯 手动下单 (Manual Order)")
with st.sidebar.form("manual_order_form"):
    m_symbol = st.text_input("交易对 (如 BTCUSDT)").upper()
    m_side = st.selectbox("方向", ["BUY", "SELL"])
    m_type = st.selectbox("类型", ["MARKET", "LIMIT"])
    
    # 根据类型动态显示输入框
    m_price = 0.0
    if m_type == "LIMIT":
        m_price = st.number_input("委托价格", min_value=0.0, value=0.0, step=0.0001, format="%.4f")
    
    # 允许选择 按金额 或 按数量 下单
    qty_mode = st.radio("下单模式", ["按金额 (USDT)", "按数量 (Qty)"], horizontal=True)
    m_amount = 0.0
    m_qty = 0.0
    if qty_mode == "按金额 (USDT)":
        m_amount = st.number_input("下单金额 (USDT)", min_value=0.0, value=100.0, step=10.0)
    else:
        m_qty = st.number_input("下单数量", min_value=0.0, value=0.0, step=0.001, format="%.3f")
        
    m_leverage = st.slider("杠杆倍数", min_value=1, max_value=50, value=4)
    submit_order = st.form_submit_button("🚀 投递开仓指令")
    
    if submit_order:
        if m_symbol:
            # 基础检查
            if m_type == "LIMIT" and m_price <= 0:
                st.sidebar.error("限价单必须输入价格")
            elif qty_mode == "按数量 (Qty)" and m_qty <= 0:
                st.sidebar.error("请输入下单数量")
            else:
                cmd = {
                    "action": "OPEN",
                    "symbol": m_symbol,
                    "side": m_side,
                    "type": m_type,
                    "price": m_price if m_type == "LIMIT" else None,
                    "amount": m_amount if qty_mode == "按金额 (USDT)" else 0,
                    "quantity": m_qty if qty_mode == "按数量 (Qty)" else 0,
                    "leverage": m_leverage,
                    "timestamp": datetime.now(UTC).isoformat()
                }
                if save_command(cmd):
                    st.sidebar.success(f"已发送: {m_side} {m_symbol}")
        else:
            st.sidebar.error("请输入交易对")

# === 主界面 ===
st.title("📈 实盘交易监控看板")

@st.fragment(run_every=50)
def main_content():
    # 加载数据
    state = load_state()
    positions = state.get("positions", {})
    pending = state.get("pending_signals", [])
    history = state.get("history", [])
    balance = state.get("balance", 0.0)
    updated_at = state.get("updated_at", "Unknown")

    # 顶部指标
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("资金余额", f"{balance:.2f} USDT")
    col2.metric("持仓数量", len(positions))
    col3.metric("待建仓信号", len(pending))

    # 处理更新时间显示
    if updated_at and updated_at != "Unknown":
        try:
            utc_dt = datetime.fromisoformat(updated_at).replace(tzinfo=UTC)
            bj_dt = utc_dt + timedelta(hours=8)
            col4.markdown(
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
            col4.metric("最后更新", updated_at)

    # 1. 持仓管理
    st.subheader("🛡 当前持仓 (Positions)")
    if positions:
        pos_data = []
        for symbol, p in positions.items():
            entry_time = p.get('entry_time', '')
            hold_time_str = "N/A"
            hours = 0
            if entry_time:
                try:
                    et = datetime.fromisoformat(entry_time).replace(tzinfo=UTC)
                    duration = datetime.now(UTC) - et
                    hours = duration.total_seconds() / 3600
                    hold_time_str = f"{hours:.1f}h"
                except: pass
            
            # TP 逻辑
            current_tp = 0.33
            max_up_12h = p.get('max_up_12h', 0)
            max_up_24h = p.get('max_up_24h', 0)
            if hours >= 12 and max_up_12h < 0.025: current_tp = 0.20
            if hours >= 24 and max_up_24h < 0.05: current_tp = 0.11
            
            virtual_entry = p.get('virtual_entry_price', p.get('entry_price', 0))
            target_exit_price = virtual_entry * (1 + current_tp)
            current_price = p.get('current_price', 0)
            dist_to_exit = (target_exit_price - current_price) / current_price if current_price > 0 else 0
            current_pnl = (current_price - virtual_entry) / virtual_entry if virtual_entry > 0 and current_price > 0 else 0

            pos_data.append({
                "Symbol": symbol,
                "Current Price": f"{current_price:.4f}" if current_price else "N/A",
                "PnL %": f"{current_pnl*100:.2f}%",
                "Target Exit": f"{target_exit_price:.4f}",
                "Dist to Exit": f"{dist_to_exit*100:.1f}%",
                "Hold Time": hold_time_str,
                "Entry Time": entry_time.replace('T', ' ').split('.')[0],
                "Signal Time": p.get('signal_time', 'N/A').replace('T', ' ').split('.')[0],
                "Virtual Entry": f"{virtual_entry:.4f}",
                "Added?": "✅" if p.get('is_virtual_added') else "❌"
            })
        st.dataframe(pd.DataFrame(pos_data), width='stretch')

        # 紧急操作
        st.markdown("---")
        st.caption("🚨 紧急操作 (Emergency Controls)")
        cols = st.columns(max(len(positions), 1))
        for i, symbol in enumerate(positions.keys()):
            if cols[i].button(f"平仓 {symbol}", key=f"close_{symbol}"):
                cmd = {"action": "CLOSE", "symbol": symbol, "timestamp": datetime.now(UTC).isoformat()}
                if save_command(cmd): st.toast(f"已发送 {symbol} 平仓指令")
    else:
        st.info("当前无持仓")

    # 2. 待建仓信号
    st.subheader("📋 待建仓信号 (Pending Signals)")
    if pending:
        pend_data = []
        for p in pending:
            timeout = p.get('timeout_time', '')
            expire_in = "N/A"
            if timeout:
                try:
                    to = datetime.fromisoformat(timeout).replace(tzinfo=UTC)
                    diff = to - datetime.now(UTC)
                    expire_in = f"{diff.total_seconds()/3600:.1f}h" if diff.total_seconds() > 0 else "Expired"
                except: pass
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
        st.dataframe(pd.DataFrame(pend_data), width='stretch')
    else: st.info("当前无等待信号")

    # 3. 历史成交
    st.subheader("📊 历史成交 (Trade History)")
    if history:
        hist_data = []
        for h in history:
            pnl = h.get('pnl_pct', 0)
            hist_data.append({
                "Symbol": h.get('symbol'),
                "Reason": h.get('reason'),
                "Entry Price": f"{h.get('entry_price', 0):.4f}",
                "Exit Price": f"{h.get('exit_price', 0):.4f}",
                "PnL %": f"{pnl*100:.2f}%",
                "Entry Time": h.get('entry_time', '').replace('T', ' ').split('.')[0],
                "Exit Time": h.get('exit_time', '').replace('T', ' ').split('.')[0]
            })
        st.dataframe(pd.DataFrame(hist_data), width='stretch')
    else: st.info("暂无历史成交记录")

    # 4. 实时日志
    st.subheader("📝 运行日志 (Latest 100 lines)")
    logs = load_logs(100)
    st.code(logs, language="text")

    # 底部说明
    st.markdown("---")
    utc_now = datetime.now(UTC)
    bj_now = utc_now + timedelta(hours=8)
    st.caption(f"Server Time: {utc_now.strftime('%Y-%m-%d %H:%M:%S')} (UTC) / {bj_now.strftime('%Y-%m-%d %H:%M:%S')} (BJ)")

if auto_refresh:
    main_content()
else:
    main_content()

