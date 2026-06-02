#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

ENV_FILE="$SCRIPT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

BILLING_PORT="${BILLING_PORT:-4313}"
TRC20_ADDRESS="${TRC20_ADDRESS:-TWD2GwSeLt7mRdDc3DPUfDU4B7cy81MsbM}"

echo "=========================================="
echo "      项目健康检查"
echo "=========================================="
echo ""

all_ok=true

echo "📡 1. Telegram Bot"
echo "------------------------------------------"
BOT_PID=$(ps aux | grep "python.*bot.py" | grep -v grep | awk '{print $2}' | head -1)
if [ -n "$BOT_PID" ]; then
    echo "   ✅ 运行中 (PID: $BOT_PID)"
else
    echo "   ❌ 未运行"
    all_ok=false
fi
echo ""

echo "💰 2. Billing Service (端口 ${BILLING_PORT})"
echo "------------------------------------------"
BILLING_PID=$(ps aux | grep "node.*server.js" | grep -v grep | grep -v Trae | awk '{print $2}' | head -1)
if [ -n "$BILLING_PID" ]; then
    echo "   ✅ 进程运行中 (PID: $BILLING_PID)"
else
    echo "   ❌ 进程未运行"
    all_ok=false
fi

BILLING_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:${BILLING_PORT}/health 2>/dev/null)
if [ "$BILLING_HEALTH" = "200" ]; then
    echo "   ✅ API 响应正常"
    BILLING_BALANCE=$(curl -s http://127.0.0.1:${BILLING_PORT}/health 2>/dev/null | grep -o '"status":"ok"' || echo "")
    if [ -n "$BILLING_BALANCE" ]; then
        echo "   ✅ 健康检查通过"
    fi
else
    echo "   ❌ API 无响应 (HTTP $BILLING_HEALTH)"
    all_ok=false
fi
echo ""

echo "🖼️ 3. GPT API Proxy (Docker 端口 3000)"
echo "------------------------------------------"
DOCKER_STATUS=$(docker ps --filter "name=chatgpt2api" --format "{{.Status}}" 2>/dev/null)
if [ -n "$DOCKER_STATUS" ]; then
    echo "   ✅ Docker 容器运行中 ($DOCKER_STATUS)"
else
    echo "   ❌ Docker 容器未运行"
    all_ok=false
fi

GPT_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "${GPT_API_BASE_URL:-http://127.0.0.1:3000}/v1/models" 2>/dev/null)
if [ "$GPT_HEALTH" = "401" ] || [ "$GPT_HEALTH" = "200" ]; then
    echo "   ✅ API 响应正常 (HTTP $GPT_HEALTH)"
else
    echo "   ⚠️ API 响应异常 (HTTP $GPT_HEALTH)"
fi
echo ""

echo "🔗 4. TRON API 连通性"
echo "------------------------------------------"
TRON_CHECK=$(curl -s -o /dev/null -w "%{http_code}" "https://api.trongrid.io/v1/accounts/${TRC20_ADDRESS}" 2>/dev/null)
if [ "$TRON_CHECK" = "200" ]; then
    echo "   ✅ Trongrid API 可达"
else
    echo "   ⚠️ Trongrid API 异常 (HTTP $TRON_CHECK)"
fi
echo ""

echo "📊 5. 数据统计"
echo "------------------------------------------"
BILLING_FILE="$SCRIPT_DIR/billing-service/data/billing.json"
if [ -f "$BILLING_FILE" ]; then
    USER_COUNT=$(grep -c '"id":' "$BILLING_FILE" 2>/dev/null || echo "0")
    echo "   👥 用户数: $USER_COUNT"
fi

ORDER_COUNT=$(curl -s http://127.0.0.1:${BILLING_PORT}/pending-orders 2>/dev/null | grep -o '"orderId"' | wc -l || echo "0")
echo "   📋 待处理订单: $ORDER_COUNT"
echo ""

echo "=========================================="
if [ "$all_ok" = true ]; then
    echo "      ✅ 所有服务正常"
else
    echo "      ⚠️ 部分服务异常，请检查"
fi
echo "=========================================="
