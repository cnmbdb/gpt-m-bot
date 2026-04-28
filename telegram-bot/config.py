import os
import json

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

BILLING_URL = os.getenv("BILLING_URL", "http://127.0.0.1:4313")

ADMIN_IDS = [825512163, 8277934317]

IMAGE_COST = 50
IMAGE_COST_M2 = 100  # gpt-image-2 费用更贵（暂时不可用）
RECHARGE_RATE = 100
NEW_USER_BONUS = 50
DEFAULT_IMAGE_MODEL = "gpt-image-1"
IMAGE_MODELS = {
    "gpt-image-1": {"name": "GPT Image 1", "cost": IMAGE_COST, "quality": "standard"},
    "gpt-image-1.5": {"name": "GPT Image 1.5", "cost": IMAGE_COST, "quality": "standard"},
}
TRC20_ADDRESS = "TKYp9dbDs6kHKtFhFR6srEJvDARNYkq9Qe"
GEN_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "billing-service", "gen-openclaw-style.js")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
LANG_FILE = os.path.join(DATA_DIR, "language-preferences.json")

os.makedirs(DATA_DIR, exist_ok=True)
if not os.path.exists(LANG_FILE):
    with open(LANG_FILE, "w") as f:
        json.dump({}, f)

WELCOME_ZH = """✨ **AI 生图** — 发送「帮我画一个图」+ 你的描述，我会用 GPT Image 1 生成高质量图片
💬 **智能对话** — 问我任何问题，我会尽力帮你解答
🔧 **工具能力** — 文件读写、代码执行、网页搜索、浏览器操作等

───

**常用命令：**
• `/start` 🚀 开始使用
• `/me` 👤 查看余额和消费记录
• `/recharge` 💸 充值余额

**计费说明：**
• 1 USDT = 100 积分
• 生图费用：GPT Image 1.5 = 50 积分/张，GPT Image 1 = 50 积分/张
• 新用户首次使用赠送 50 积分
• 充值地址（TRC20）：`TKYp9dbDs6kHKtFhFR6srEJvDARNYkq9Qe`
• 发送 `/recharge` 即可快速充值

───

有任何问题，直接发消息给我就行！"""

WELCOME_EN = """✨ **AI Image Generation** — Send 「Draw me a picture」+ your description, I'll generate high-quality images with GPT Image 1
💬 **Smart Chat** — Ask me anything, I'll do my best to help
🔧 **Tools** — File read/write, code execution, web search, browser automation, and more

───

**Commands:**
• `/start` 🚀 Start
• `/me` 👤 Check balance & history
• `/recharge` 💸 Top up balance

**Pricing:**
• 1 USDT = 100 credits
• GPT Image 1.5 = 50 credits/image, GPT Image 1 = 50 credits/image
• New users get 50 free credits
• Top-up address (TRC20): `TKYp9dbDs6kHKtFhFR6srEJvDARNYkq9Qe`
• Send `/recharge` to top up quickly

───

Feel free to message me if you need anything!"""

WELCOME_RU = """✨ **AI Генерация изображений** — Отправьте «Нарисуй мне картинку» + ваше описание, я создам качественные изображения с GPT Image 1
💬 **Умный чат** — Задайте мне любой вопрос, я постараюсь помочь
🔧 **Инструменты** — Чтение/запись файлов, выполнение кода, веб-поиск, автоматизация браузера и многое другое

───

**Команды:**
• `/start` 🚀 Начать
• `/me` 👤 Проверить баланс и историю
• `/recharge` 💸 Пополнить баланс

**Цены:**
• 1 USDT = 100 кредитов
• GPT Image 1.5 = 50 кредитов/изображение, GPT Image 1 = 50 кредитов/изображение
• Новые пользователи получают 50 бесплатных кредитов
• Адрес для пополнения (TRC20): `TKYp9dbDs6kHKtFhFR6srEJvDARNYkq9Qe`
• Отправьте `/recharge` для быстрого пополнения

───

Не стесняйтесь обращаться, если вам нужна помощь!"""

WELCOMES = {
    "zh": WELCOME_ZH,
    "en": WELCOME_EN,
    "ru": WELCOME_RU,
}

LANG_SELECT_MSG = "🌐 请选择语言 / Choose language / Выберите язык"
