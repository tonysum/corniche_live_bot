#!/bin/bash

# 获取脚本所在目录
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# 检查 .env
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "Please edit .env with your API keys!"
    exit 1
fi

# 启动选项
case "$1" in
    start)
        echo "Starting Trading Bot..."
        # 使用 nohup 后台运行，日志重定向到 /dev/null (因为程序内部已经写日志了)
        nohup python src/main.py > /dev/null 2>&1 &
        echo "Bot started with PID $!"
        
        echo "Starting Dashboard..."
        nohup streamlit run src/dashboard.py --server.port 8501 > /dev/null 2>&1 &
        echo "Dashboard started on port 8501"
        ;;
    stop)
        echo "Stopping processes..."
        pkill -f "src/main.py"
        pkill -f "streamlit run src/dashboard.py"
        echo "Stopped."
        ;;
    status)
        pgrep -a python | grep "src/main.py"
        pgrep -a streamlit
        ;;
    *)
        echo "Usage: $0 {start|stop|status}"
        exit 1
        ;;
esac
