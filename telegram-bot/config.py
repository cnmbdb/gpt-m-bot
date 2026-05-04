import os
import json

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

BILLING_URL = os.getenv("BILLING_URL", "http://127.0.0.1:4313")

ADMIN_IDS = [825512163, 8277934317]

IMAGE_COST = 50
IMAGE_COST_M2 = 50
RECHARGE_RATE = 100
NEW_USER_BONUS = 100
DEFAULT_IMAGE_MODEL = "gpt-m2"

GPT_API_BASE_URL = os.getenv("GPT_API_BASE_URL", "http://127.0.0.1:3000")
GPT_API_AUTH_KEY = os.getenv("GPT_API_AUTH_KEY", "chatgpt2api")
GPT_API_IMAGES_DIR = os.getenv("GPT_API_IMAGES_DIR", "/Users/a2333/IDE/gpt-huatu/gpt-api/data/images")

DEFAULT_IMAGE_MODEL = "gpt-m2"

IMAGE_MODELS = {
    "gpt-m2": {
        "name": "AI",
        "cost": IMAGE_COST,
        "quality": "high",
        "provider": "local",
        "local_model": "gpt-image-2",
    },
}
TRC20_ADDRESS = "TWD2GwSeLt7mRdDc3DPUfDU4B7cy81MsbM"
GEN_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "billing-service", "gen-openclaw-style.js")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
LANG_FILE = os.path.join(DATA_DIR, "language-preferences.json")

os.makedirs(DATA_DIR, exist_ok=True)
if not os.path.exists(LANG_FILE):
    with open(LANG_FILE, "w") as f:
        json.dump({}, f)

WELCOME_ZH = """🎉 **AI 生图** — 发送「帮我画一个图」+ 你的描述，我会用 AI 生成高质量图片
💭 **智能对话** — 问我任何问题，我会尽力帮你解答
⚙️ **工具能力** — 文件读写、代码执行、网页搜索、浏览器操作等

───

**常用命令：**
• `/start` 🚀 开始使用
• `/me` 👤 查看余额和消费记录
• `/recharge` 💰 充值余额

**计费说明：**
• 1 USDT = 100 积分
• 生图费用：AI = 50 积分/张
• 新用户首次使用赠送 100 积分
• 充值地址（TRC20）：`TWD2GwSeLt7mRdDc3DPUfDU4B7cy81MsbM`
• 发送 `/recharge` 即可快速充值

───

有任何问题，直接发消息给我就行！"""

WELCOME_EN = """🎉 **AI Image Generation** — Send 「Draw me a picture」+ your description, I'll generate high-quality images with AI
💭 **Smart Chat** — Ask me anything, I'll do my best to help
⚙️ **Tools** — File read/write, code execution, web search, browser automation, and more

───

**Commands:**
• `/start` 🚀 Start
• `/me` 👤 Check balance & history
• `/recharge` 💰 Top up balance

**Pricing:**
• 1 USDT = 100 credits
• AI = 50 credits/image
• New users get 100 free credits
• Top-up address (TRC20): `TWD2GwSeLt7mRdDc3DPUfDU4B7cy81MsbM`
• Send `/recharge` to top up quickly

───

Feel free to message me if you need anything!"""

WELCOME_RU = """🎉 **AI Генерация изображений** — Отправьте «Нарисуй мне картинку» + ваше описание, я создам качественные изображения с AI
💭 **Умный чат** — Задайте мне любой вопрос, я постараюсь помочь
⚙️ **Инструменты** — Чтение/запись файлов, выполнение кода, веб-поиск, автоматизация браузера и многое другое

───

**Команды:**
• `/start` 🚀 Начать
• `/me` 👤 Проверить баланс и историю
• `/recharge` 💰 Пополнить баланс

**Цены:**
• 1 USDT = 100 кредитов
• AI = 50 кредитов/изображение
• Новые пользователи получают 50 бесплатных кредитов
• Адрес для пополнения (TRC20): `TWD2GwSeLt7mRdDc3DPUfDU4B7cy81MsbM`
• Отправьте `/recharge` для быстрого пополнения

───

Не стесняйтесь обращаться, если вам нужна помощь!"""

WELCOMES = {
    "zh": WELCOME_ZH,
    "en": WELCOME_EN,
    "ru": WELCOME_RU,
}

LANG_SELECT_MSG = "🌐 请选择语言 / Choose language / Выберите язык"
