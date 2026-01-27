# Corniche Live Bot

基于买量暴涨策略 (Buy Surge Strategy) 的加密货币实盘交易系统。

## 目录结构

```
corniche_live_bot/
├── src/
│   ├── main.py          # 交易主程序
│   ├── dashboard.py     # 监控看板 (Streamlit)
│   └── binance_api.py   # API 封装
├── logs/                # 运行日志
├── data/                # 状态文件 (json)
├── run.sh               # 启动/停止脚本
└── requirements.txt     # 依赖列表
```

## 部署指南

### 1. 准备环境 (Ubuntu/Debian)

```bash
# 安装 Python3 和 pip
sudo apt update
sudo apt install python3-pip python3-venv -y

# 克隆代码 (或上传代码包)
git clone <your-repo-url> corniche_live_bot
cd corniche_live_bot
```

### 2. 配置

1.  复制环境变量文件：
    ```bash
    cp .env.example .env
    ```
2.  编辑 `.env` 填入您的币安 API Key：
    ```bash
    nano .env
    ```

### 3. 安装依赖 (SDK)

**注意**：本项目依赖 `binance_sdk_derivatives_trading_usds_futures`。请确保该文件夹在 `src/` 目录下，或者在 `PYTHONPATH` 中。
如果 SDK 是作为子模块存在的，请先复制过来：
```bash
cp -r ../backend/binance_sdk_derivatives_trading_usds_futures src/
```

### 4. 启动

使用辅助脚本一键启动交易机器人和监控看板：

```bash
./run.sh start
```

*   交易机器人将在后台运行。
*   监控看板将在端口 8501 启动。

### 5. 访问监控看板

**方法 A：SSH 隧道 (推荐，安全)**
在您的本地电脑终端运行：
```bash
ssh -L 8501:localhost:8501 user@your_server_ip
```
然后在本地浏览器访问：`http://localhost:8501`

**方法 B：直接访问**
如果服务器防火墙允许 8501 端口：
访问 `http://your_server_ip:8501`

## 运维命令

*   **停止服务**：`./run.sh stop`
*   **查看状态**：`./run.sh status`
*   **查看日志**：`tail -f logs/trading.log`

## 注意事项

*   默认模式为 **模拟交易 (Dry Run)**。如需实盘，请修改 `src/main.py` 最后一行：
    ```python
    trader = RealTimeBuySurgeStrategyV3(dry_run=False)
    ```
