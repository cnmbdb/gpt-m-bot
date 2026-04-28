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
    echo "❌ 错误: 未找到 python3，请先安装 Python 3.10+"
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
    pip3 install -q python-telegram-bot[ext]==20.7 requests>=2.31.0
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
echo "🎉 所有服务已启动！"
echo ""
echo "   计费服务: http://127.0.0.1:4313"
echo "   Telegram: 运行中"
echo ""
echo "   停止服务: ./stop.sh"
echo ""

echo "$BILLING_PID $BOT_PID" > "$SCRIPT_DIR/.pids"

wait
