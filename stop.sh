#!/bin/bash
launchctl remove gpt-huatu.billing 2>/dev/null || true
launchctl remove gpt-huatu.telegram-bot 2>/dev/null || true

if [[ -f "$(dirname "$0")/.pids" ]]; then
    echo "正在停止服务..."
    IFS=' ' read -r B_PID T_PID < "$(dirname "$0")/.pids"
    kill $B_PID $T_PID 2>/dev/null || true
    rm -f "$(dirname "$0")/.pids"
    echo "已停止。"
else
    echo "未找到运行中的服务PID。"
fi
