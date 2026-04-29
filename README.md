# Telegram AI 生图机器人

基于 Python + Node.js 的 Telegram 机器人，支持 USDT/TRC20 充值、积分计费、GPT Image 1 图片生成、多语言界面、以及邀请返现。

---

## 目录结构

```
gpt-huatu/
├── billing-service/              # 计费服务 (Node.js Express)
│   ├── server.js                # API 服务主文件
│   ├── check-limits.js           # 限额检查脚本
│   ├── gen-openclaw-style.js     # 图片生成脚本
│   ├── package.json
│   └── data/
│       ├── billing.json          # 用户/订单数据
│       ├── pending_transfers.json
│       └── transactions.json     # 交易流水
├── telegram-bot/                 # Telegram 机器人 (Python)
│   ├── bot.py                   # 主入口
│   ├── config.py               # 配置（欢迎语、语言文案等）
│   ├── handlers/
│   │   └── commands.py         # 命令处理器
│   ├── services/
│   │   ├── billing.py         # 计费服务客户端
│   │   ├── language.py        # 语言偏好 + 活跃时间管理
│   │   └── image.py           # 图片生成服务
│   ├── requirements.txt
│   └── data/
│       └── language-preferences.json  # 用户语言设置
├── .env                         # 环境变量（需自行创建）
├── start.sh                    # 一键启动脚本
├── stop.sh                     # 停止脚本
└── README.md
```

---

## 环境要求

- Node.js >= 16
- Python >= 3.10

---

## 快速启动

```bash
# 复制并配置环境变量
cp .env.example .env  # 手动编辑 .env 填入 TOKEN 和 API Key

# 一键启动（计费服务 + Telegram 机器人）
./start.sh

# 停止
./stop.sh
```

---

## 环境变量 (.env)

```bash
# Telegram Bot Token（从 @BotFather 获取）
TELEGRAM_BOT_TOKEN="your_bot_token_here"

# OpenAI API Key（用于 GPT Image 1）
OPENAI_API_KEY="your_openai_api_key_here"

# 计费服务地址（默认本地）
BILLING_URL="http://127.0.0.1:4313"
```

---

## 功能一览

### 1. 多语言支持
- 支持简体中文（🇨🇳）、English（🇺🇸）、Русский（🇷🇺）
- 新用户首次使用或超过 7 天未活跃，再次触发时弹出语言选择
- 界面文案全部支持三种语言

### 2. AI 生图
- 发送 `用 Image 2 帮我画一个图 [描述]`，或点击底部按钮输入描述
- 使用 OpenAI GPT Image 1 模型生成高质量图片
- 每张图片消耗 **50 积分**

### 3. USDT 充值
- 充值地址：TRC20（波场链）
- 比例：1 USDT = 100 积分
- 创建订单后 15 分钟内完成转账，点击确认按钮等待链上确认
- 到账自动积分入账

### 4. 邀请返现（/pdd）
- 发送 `/pdd` 查看专属推荐链接
- 好友通过你的推荐链接注册（`/start?start=pdd_{你的user_id}`）
- 好友充值满 **10 USDT** 后，你立即获得 **300 积分** 返现
- 推荐统计实时更新

### 5. 新用户福利
- 首次充值后自动领取 100 积分新用户奖励

---

## 命令列表

| 命令 | 描述 |
|------|------|
| `/start` | 开始使用 / 重新打开菜单（支持推荐链接 `/start?start=pdd_xxx`） |
| `/recharge` | 充值余额（创建 USDT 充值订单） |
| `/me` | 个人中心 — 查看余额和交易记录 |
| `/pdd` | 分享赚钱 — 查看推荐链接和返现统计 |
| `/help` | 使用帮助 |

---

## 底部菜单按钮

机器人主界面底部有 Reply 键盘按钮：

| 按钮 | 功能 |
|------|------|
| 🎨 AI 生图 | 输入图片描述，开始生成 |
| 💰 充值余额 | 创建充值订单 |
| 👤 个人中心 | 查看余额和交易记录 |
| 💰 分享赚钱 | 查看推荐链接和返现统计 |
| ❓ 帮助 | 显示帮助信息 |

---

## 计费规则

| 项目 | 数值 |
|------|------|
| 1 USDT | 100 积分 |
| 生图费用 | 50 积分/张 |
| 新用户奖励 | 100 积分 |
| 推荐返现 | 被推荐人充值 ≥10 USDT 时，推荐人获得 300 积分 |
| 充值有效期 | 订单创建后 15 分钟内有效 |

---

## 计费服务 API

计费服务运行于 `http://127.0.0.1:4313`，以下为全部接口：

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/user/:userId` | GET | 获取/注册用户 |
| `/balance/:userId` | GET | 查询余额 |
| `/deduct` | POST | 扣费（生图时调用） |
| `/recharge` | POST | 创建充值订单 |
| `/order/:orderId` | GET | 查询订单状态 |
| `/orders/:userId` | GET | 用户订单列表 |
| `/refund` | POST | 退款 |
| `/claim-bonus` | POST | 领取新用户福利 |
| `/notify-transfer` | POST | 链上确认回调（充值到账） |
| `/bind-referrer` | POST | 绑定推荐人关系 |
| `/referral/:userId` | GET | 查询推荐统计（推荐人数、已获返现、待返现） |
| `/transactions/:userId` | GET | 交易流水 |
| `/pending-orders` | GET | 待处理订单列表 |
| `/admin/add-balance` | POST | 管理员手动加余额 |
| `/admin/users` | GET | 所有用户列表 |

---

## 推荐返现流程

```
用户 A
    │
    │ 发送 /pdd
    ▼
获取推荐链接: https://t.me/<BotName>/start?start=pdd_用户A的ID
    │
    │ 分享给用户 B
    ▼
用户 B 点击链接 → 打开 Bot → 自动绑定 A 为推荐人
    │
    │ 用户 B 充值 ≥10 USDT
    ▼
系统自动给用户 A 发放 300 积分返现
```

- 推荐关系绑定一次有效，不可重复绑定
- 自己不能推荐自己
- 推荐人必须已存在（至少调用过机器人一次）

---

## 管理员

管理员不受所有限制（无限生图、新用户福利等）。

当前管理员：
- `825512163` (@HFTGID)
- `8277934317` (@psps)

在 `telegram-bot/config.py` 中配置 `ADMIN_IDS` 列表即可添加管理员。

---

## 数据存储

所有数据存储在本地 JSON 文件中，无外部数据库依赖：

| 文件 | 内容 |
|------|------|
| `billing-service/data/billing.json` | 用户信息、余额、推荐关系 |
| `billing-service/data/pending_transfers.json` | 待确认充值订单 |
| `billing-service/data/transactions.json` | 所有交易流水记录 |
| `telegram-bot/data/language-preferences.json` | 用户语言设置和最后活跃时间 |

> ⚠️ 数据仅存在本地，请定期备份重要数据文件。
