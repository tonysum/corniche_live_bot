# Corniche Live Bot

基于买量暴涨策略 (Buy Surge Strategy) 的加密货币实盘交易系统，采用 PM2 进行进程管理和自动监控。

## 目录结构

```
corniche_live_bot/
├── src/
│   ├── main.py          # 交易主程序
│   ├── dashboard.py     # 监控看板 (Streamlit)
│   └── binance_api.py   # API 封装
├── logs/                # 运行日志 (包含 trading.log)
├── data/                # 状态文件 (json)
├── run.sh               # ⚠️ 核心管理脚本 (集成 PM2)
├── ecosystem.config.js  # PM2 配置文件
└── requirements.txt     # 依赖列表
```

## 部署指南

### 1. 准备环境 (Ubuntu/Debian)

```bash
# 1. 安装 Python 环境
sudo apt update
sudo apt install python3-pip python3-venv nodejs npm -y

# 2. 安装 PM2 (全局安装)
sudo npm install pm2 -g

# 3. 克隆代码
git clone <your-repo-url> corniche_live_bot
cd corniche_live_bot
```

### 2. 初始化配置

1.  复制并编辑环境变量：
    ```bash
    cp .env.example .env
    nano .env  # 填入 API Key 和 Secret
    ```
2.  确保虚拟环境和依赖已就绪：
    ```bash
    # 第一次运行 run.sh 会自动创建 venv 并安装依赖
    ./run.sh start
    ```

---

## 管理命令 (`./run.sh`)

项目已集成 PM2，建议优先使用 `./run.sh` 进行日常管理：

| 命令 | 功能描述 |
| :--- | :--- |
| **`./run.sh start`** | 启动/重启所有进程 (Bot + Dashboard) |
| **`./run.sh stop`** | 停止所有进程 |
| **`./run.sh status`** | 查看当前运行状态、CPU 和内存占用 |
| **`./run.sh monit`** | **进入可视化监控面板** (查看实时日志堆栈) |
| **`./run.sh log`** | 查看 PM2 捕获的聚合日志流 |
| **`./run.sh restart`** | 重新启动所有服务 |

---

## 监控看板 (Web)

- **服务端口**：默认 `8501`。
- **本地访问**：浏览器打开 `http://localhost:8501`。
- **VPS 远程同步**：建议使用 SSH 隧道：
  ```bash
  ssh -L 8501:localhost:8501 user@your_server_ip
  ```

---

## 核心配置与注意事项

### 1. 实盘开关
默认模式为 **模拟交易 (Dry Run)**。如需正式实盘，请修改 `src/main.py` 的初始化逻辑：
```python
trader = RealTimeBuySurgeStrategyV3(dry_run=False)
```

### 2. 日志说明
- **业务日志**：`logs/trading.log` (看板显示此文件)。
- **进程日志**：由 PM2 维护，可通过 `./run.sh log` 查看，包含系统报错和崩溃信息。

### 3. 2GB 内存 VPS 优化
项目已内置 `collections.deque` 日志滚动读取方案，即便 `trading.log` 过大也不会撑爆 VPS 内存。
