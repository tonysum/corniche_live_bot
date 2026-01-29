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
        echo "Starting with PM2..."
        pm2 start ecosystem.config.js
        ;;
    stop)
        echo "Stopping processes with PM2..."
        pm2 stop ecosystem.config.js
        ;;
    restart)
        echo "Restarting with PM2..."
        pm2 restart ecosystem.config.js
        ;;
    status)
        pm2 status
        ;;
    monit)
        pm2 monit
        ;;
    log)
        pm2 logs
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|monit|log}"
        exit 1
        ;;
esac
