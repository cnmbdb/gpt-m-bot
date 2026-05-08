#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=========================================="
echo "  Telegram AI 生图机器人 启动脚本"
echo "=================================="

# 加载 .env 文件
ENV_FILE="$SCRIPT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
    echo "   读取配置文件: $ENV_FILE"
    set -a
    source "$ENV_FILE"
    set +a
fi

# 检测环境
if ! command -v node &> /dev/null; then
    echo "❌ 错误: 未找到 node，请先安装 Node.js"
    exit 1
fi
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3，请先安装 Python 3.11+"
    exit 1
fi

if [[ -z "$TELEGRAM_BOT_TOKEN" ]]; then
    echo "❌ 错误: TELEGRAM_BOT_TOKEN 未设置，请编辑 .env 文件"
    exit 1
fi
if [[ -z "$OPENAI_API_KEY" ]]; then
    echo "❌ 错误: OPENAI_API_KEY 未设置，请编辑 .env 文件"
    exit 1
fi

# 创建必要目录
mkdir -p "$SCRIPT_DIR/billing-service/data"
mkdir -p "$SCRIPT_DIR/telegram-bot/data"

# 初始化数据文件
init_file() {
    local file="$1"
    local content="$2"
    if [[ ! -f "$file" ]]; then
        echo "$content" > "$file"
    fi
}

init_file "$SCRIPT_DIR/billing-service/data/billing.json" '{"users":{},"orders":{}}'
init_file "$SCRIPT_DIR/billing-service/data/pending_transfers.json" '[]'
init_file "$SCRIPT_DIR/telegram-bot/data/language-preferences.json" '{}'

# 安装 Node.js 依赖
echo ""
echo "[1/3] 检查 Node.js 依赖..."
if [[ ! -d "$SCRIPT_DIR/billing-service/node_modules" ]]; then
    cd "$SCRIPT_DIR/billing-service" && npm install --silent
fi

# 安装 Python 依赖
echo ""
echo "[2/3] 检查 Python 依赖..."
if ! python3 -c "import telegram" 2>/dev/null; then
    echo "   安装 python-telegram-bot..."
    python3 -m pip install -q python-telegram-bot[ext]==20.7 requests>=2.31.0
fi

# 启动计费服务
echo ""
echo "[3/3] 启动服务..."
echo "------------------------------------------"

cd "$SCRIPT_DIR/billing-service"
node server.js &
BILLING_PID=$!
echo "   ✅ 计费服务已启动 (PID: $BILLING_PID, 端口: 4313)"

sleep 2

if ! curl -s http://127.0.0.1:4313/health > /dev/null 2>&1; then
    echo "   ❌ 计费服务启动失败，请检查端口 4313 是否被占用"
    kill $BILLING_PID 2>/dev/null || true
    exit 1
fi

cd "$SCRIPT_DIR/telegram-bot"
TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" OPENAI_API_KEY="$OPENAI_API_KEY" python3 bot.py &
BOT_PID=$!
echo "   ✅ Telegram 机器人已启动 (PID: $BOT_PID)"
echo "------------------------------------------"

echo ""
echo "🔍 启动健康检查..."
echo ""

# 健康检查函数
check_service() {
    local name=$1
    local check_func=$2
    if $check_func; then
        echo "   ✅ $name"
        return 0
    else
        echo "   ❌ $name"
        return 1
    fi
}

# Telegram Bot
check_bot() {
    BOT_RUNNING=$(ps aux | grep "python.*bot.py" | grep -v grep | awk '{print $2}' | head -1)
    [ -n "$BOT_RUNNING" ]
}

# Billing Service
check_billing() {
    curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4313/health 2>/dev/null | grep -q "200"
}

# Docker GPT API
check_docker() {
    docker ps --filter "name=chatgpt2api" --format "{{.Names}}" 2>/dev/null | grep -q "chatgpt2api"
}

# TRON API
check_tron() {
    curl -s -o /dev/null -w "%{http_code}" "https://api.trongrid.io/v1/accounts/TWD2GwSeLt7mRdDc3DPUfDU4B7cy81MsbM" 2>/dev/null | grep -q "200"
}

all_ok=true

echo "📡 Telegram Bot:"
check_service "Telegram Bot" check_bot || all_ok=false

echo "💰 Billing Service:"
check_service "Billing Service (4313)" check_billing || all_ok=false

echo "🖼️ GPT API Proxy (Docker):"
if check_service "GPT API Docker" check_docker; then
    GPT_STATUS=$(docker ps --filter "name=chatgpt2api" --format "{{.Status}}" 2>/dev/null)
    echo "      状态: $GPT_STATUS"
fi

echo "🔗 TRON API:"
check_service "Trongrid API" check_tron || all_ok=false

echo ""

if [ "$all_ok" = true ]; then
    echo "🎉 所有服务已启动并正常！"
else
    echo "⚠️ 部分服务异常，请检查"
fi
echo ""
echo "   计费服务: http://127.0.0.1:4313"
echo "   Telegram: 运行中"
echo ""
echo "   停止服务: ./stop.sh"
echo "   健康检查: ./health-check.sh"
echo ""

echo "$BILLING_PID $BOT_PID" > "$SCRIPT_DIR/.pids"

wait
