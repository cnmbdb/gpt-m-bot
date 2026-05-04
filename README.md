# Telegram AI 生图机器人

基于 Python + Node.js 的 Telegram 机器人，支持 USDT/TRC20 充值（自动链上检测）、积分计费、GPT Image 2 图片生成、多语言界面、邀请返现、以及多轮图片编辑功能。

---

## 目录结构

```
gpt-huatu/
├── billing-service/              # 计费服务 (Node.js Express)
│   ├── server.js                # API 服务主文件
│   ├── check-limits.js         # 限额检查脚本
│   ├── package.json
│   └── data/
│       ├── billing.json          # 用户/订单数据
│       ├── pending_transfers.json
│       └── transactions.json
├── telegram-bot/                 # Telegram 机器人 (Python)
│   ├── bot.py                   # 主入口
│   ├── config.py                # 配置
│   ├── handlers/
│   │   └── commands.py         # 命令处理器
│   ├── services/
│   │   ├── billing.py          # 计费服务客户端
│   │   ├── language.py         # 语言偏好管理
│   │   └── image.py            # 图片生成服务
│   └── data/
├── gpt-api/                     # 本地 gpt-image-2 反代服务 (chatgpt2api Docker)
│   ├── docker-compose.yml
│   └── .env
├── .env                         # 环境变量
├── start.sh                     # 一键启动脚本（含健康检查）
├── stop.sh                      # 停止脚本
├── health-check.sh              # 健康检查脚本
└── README.md
```

---

## 环境要求

- Node.js >= 16
- Python >= 3.10
- Docker (用于 gpt-api 本地反代服务)
- USDT (TRC20) 用于充值

---

## 快速启动

```bash
# 一键启动（所有服务 + 健康检查）
./start.sh

# 停止
./stop.sh

# 健康检查
./health-check.sh
```

---

## 环境变量 (.env)

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here
BILLING_URL=http://127.0.0.1:4313
GPT_API_BASE_URL=http://127.0.0.1:3000
GPT_API_AUTH_KEY=chatgpt2api
GPT_API_IMAGES_DIR=/path/to/gpt-huatu/gpt-api/data/images
```

---

## 架构说明

```
用户请求 (Telegram)
       ↓
Telegram 机器人 (Python)
       ↓
  ┌────┴────┐
  ↓         ↓
计费服务    GPT API 本地反代
(Node.js)   (chatgpt2api Docker)
端口:4313   端口:3000
              ↓
         图片生成后保存到本地目录
         /gpt-api/data/images/
              ↓
         机器人直接读本地文件
         发送给用户（无需网络下载）
```

- **telegram-bot**: 处理用户交互、扣费、协调
- **billing-service**: 用户余额、订单、交易记录、TRON 自动轮询检测
- **gpt-api**: 本地运行 chatgpt2api，通过 ChatGPT 账号调用 gpt-image-2，图片保存到 `data/images/` 目录供 bot 直接读取

---

## 启动服务（共 3 个）

| 服务 | 技术栈 | 端口 | 启动命令 |
|------|--------|------|----------|
| Telegram Bot | Python | - | `python3 bot.py` |
| Billing Service | Node.js | 4313 | `node server.js` |
| GPT API Proxy | Docker | 3000 | `docker start chatgpt2api` |

---

## 健康检查

启动后自动检查所有服务状态：

```bash
./start.sh
# 输出示例：
# 🔍 启动健康检查...
# 📡 Telegram Bot:        ✅
# 💰 Billing Service:     ✅
# 🖼️ GPT API Docker:      ✅
# 🔗 TRON API:            ✅
# 🎉 所有服务已启动并正常！
```

或单独检查：

```bash
./health-check.sh
```

---

## 功能一览

### 1. AI 生图（GPT Image 2）

点击底部「🎨 AI 生图」按钮：
- **生成图片**：输入描述 → 生成图片（消耗 50 积分）
- **参考图片生成**：发送参考图片+文案描述 → 基于参考图生成图片（消耗 50 积分）
  - 支持**单张或多张**参考图片
- **修改图片**：发送图片+描述 → 修改图片（消耗 50 积分）
  - 支持**单张或多张**图片同时修改
- **继续修改**：生成/修改完成后，点击「✏️ 继续修改图片」按钮，输入修改指令（消耗 40 积分/次）
- 图片生成后可无限次继续修改，每次仅需 40 积分

### 2. USDT 充值（自动链上检测）

- 地址：TRC20（波场链）`TWD2GwSeLt7mRdDc3DPUfDU4B7cy81MsbM`
- 比例：1 USDT = 100 积分
- 订单有效期：15 分钟
- **防错充机制**：每个订单金额自动添加随机小数（0.01~0.99 USDT），转账时需精确到小数点后2位
- **自动到账**：系统每 15 秒轮询 Trongrid API，检测到转账后自动发放积分，无需手动确认
- **通知机制**：充值成功后同时通知用户和管理员

### 3. 新用户福利

- 首次充值后自动领取 100 积分

### 4. 邀请返现（/pdd）

- 发送 `/pdd` 查看推荐链接
- 好友通过推荐链接注册并充值满 10 USDT，你获得 300 积分返现

### 5. 多语言支持

- 支持简体中文（🇨🇳）、English（🇺🇸）、Русский（🇷🇺）
- 新用户或超过 7 天未活跃时触发语言选择

---

## 命令列表

| 命令 | 描述 |
|------|------|
| `/start` | 开始使用 / 重新打开菜单 |
| `/recharge` | 充值余额 |
| `/me` | 个人中心 — 余额和交易记录 |
| `/pdd` | 分享赚钱 — 推荐链接和返现统计 |
| `/sc` | 生成图片 |
| `/gt` | 修改图片 |
| `/zs` | 管理员：增减用户积分（隐藏命令）|

---

## 底部菜单按钮

| 按钮 | 功能 |
|------|------|
| 🎨 AI 生图 | 生成或修改图片 |
| 💰 充值余额 | 创建充值订单 |
| 💰 分享赚钱 | 推荐链接和返现 |
| 👤 个人中心 | 余额和交易记录 |
| ❓ 帮助 | 使用说明和收费标准 |

---

## 计费规则

| 项目 | 数值 |
|------|------|
| 1 USDT | 100 积分 |
| 首次生成图片 | 50 积分/张 |
| 首次修改图片 | 50 积分/张 |
| 继续修改 | 40 积分/次 |
| 新用户奖励 | 100 积分 |
| 推荐返现 | 被推荐人充值 ≥10 USDT 时，获得 300 积分 |
| 充值有效期 | 订单创建后 15 分钟内有效 |

---

## 计费服务 API

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/user/:userId` | GET | 获取/注册用户 |
| `/balance/:userId` | GET | 查询余额 |
| `/deduct` | POST | 扣费 |
| `/recharge` | POST | 创建充值订单（自动添加随机小数） |
| `/order/:orderId` | GET | 查询订单状态 |
| `/refund` | POST | 退款 |
| `/claim-bonus` | POST | 领取新用户福利 |
| `/bind-referrer` | POST | 绑定推荐人关系 |
| `/referral/:userId` | GET | 推荐统计 |
| `/transactions/:userId` | GET | 交易流水 |
| `/add-balance` | POST | 增加用户余额 |
| `/admin/add-balance` | POST | 管理员手动加余额 |
| `/admin/users` | GET | 所有用户列表 |
| `/pending-orders` | GET | 待处理订单列表 |

---

## 管理员命令 /zs

仅管理员可用（不显示在命令菜单）：

**方式一：回复消息后操作（推荐）**
```
1. 管理员回复用户的消息
2. 发送 /zs +100  → 给该用户加100积分
3. 发送 /zs -50   → 扣除该用户50积分
```

**方式二：直接指定用户ID**
```bash
/zs 825512163 +100    # 给用户加 100 积分
/zs 825512163 -50     # 扣除用户 50 积分
/zs 825512163 +100 8277934317 -50  # 一次操作多个用户
```

---

## 管理员

管理员不受限制（无限生图、新用户福利等）。

当前管理员：
- `825512163`
- `8277934317`

在 `telegram-bot/config.py` 中配置 `ADMIN_IDS` 列表即可添加管理员。

---

## 数据存储

所有数据存储在本地 JSON 文件中：

| 文件 | 内容 |
|------|------|
| `billing-service/data/billing.json` | 用户信息、余额、推荐关系 |
| `billing-service/data/pending_transfers.json` | 待确认充值订单 |
| `billing-service/data/transactions.json` | 交易流水 |
| `telegram-bot/data/language-preferences.json` | 用户语言设置 |

> ⚠️ 数据仅存在本地，请定期备份重要数据文件。

---

## 图片生成流程

```
1. 点击「🎨 AI 生图」
2. 选择操作：
   ├─ 「🎨 生成图片」→ 输入描述 → 生成图片（50积分）
   ├─ 「🎨 生成图片」→ 发送参考图片+描述 → 基于参考图生成（50积分）
   │  └─ 支持单张或多张参考图片
   └─ 「✏️ 修改图片」→ 发送图片+描述 → 修改图片（50积分）
      └─ 支持单张或多张图片同时修改
3. gpt-api 生成图片 → 保存到本地 /gpt-api/data/images/
4. 机器人直接读取本地文件路径 → 发送给 Telegram 用户
5. 图片生成后，点击「✏️ 继续修改图片」
6. 输入修改指令 → 修改图片（40积分/次）
7. 重复步骤 5-6 可无限次继续修改
```

**本地文件流程（无需 ngrok）：**
- gpt-api 生成图片后，返回 URL: `http://127.0.0.1:3000/images/2026/05/05/xxx.png`
- 机器人将 URL 路径映射到本地: `/gpt-api/data/images/2026/05/05/xxx.png`
- 直接用本地文件路径发送给 Telegram，无网络下载延迟

---

## 充值自动到账流程

```
用户创建订单（金额如 10.37 USDT）
    ↓
用户向 TRC20 地址转账精确金额
    ↓
billing-service 每 15 秒轮询 trongrid.io
    ↓
检测到匹配金额 → 自动完成充值
    ↓
通知用户 + 通知两个管理员
```

---

## gpt-api 本地反代服务

位于 `gpt-api/` 目录，运行 chatgpt2api Docker 容器：

- 地址：`http://127.0.0.1:3000`
- 鉴权 key：`chatgpt2api`
- 模型：`gpt-image-2`
- 图片存储：`/gpt-api/data/images/`（Docker 挂载到宿主机）
- `config.json` 中 `base_url` 设为 `http://127.0.0.1:3000`，返回本地文件路径供 bot 直接读取

需要导入有效的 ChatGPT Plus 账号才能使用。
