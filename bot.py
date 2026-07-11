import os
import json
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
from sheets import SheetsManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
sheets = SheetsManager()

SYSTEM_PROMPT = """Ты помощник для учёта расходов кофейни. 

Когда пользователь описывает расход, извлеки:
1. Сумму (число)
2. Категорию из списка:
   - Продукты и сырьё
   - Десерты
   - Реклама
   - Продукты кухня
   - Продукты бар
   - Доставка
   - Зарплата персонала
   - Аренда
   - Оборудование и ремонт
   - Коммунальные услуги
   - Упаковка и расходники
3. Краткое описание (что именно куплено/оплачено)

Отвечай ТОЛЬКО в формате JSON без лишнего текста:
{"amount": число, "category": "название категории", "description": "краткое описание", "valid": true}

Если сообщение не про расход или нет суммы — верни:
{"valid": false}
"""

def parse_expense(text: str) -> dict:
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            max_tokens=300,
            temperature=0.1
        )
        raw = response.choices[0].message.content.strip()
        # Убираем возможные markdown блоки
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Ошибка Groq: {e}")
        return {"valid": False}

def get_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Итоги за сегодня"), KeyboardButton("📅 Итоги за месяц")],
        [KeyboardButton("📋 Последние записи"), KeyboardButton("❓ Помощь")]
    ], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я помогу вести учёт расходов кофейни.\n\n"
        "Просто напиши о расходе:\n"
        "• Купил зёрна арабики 5 кг за 3500 руб\n"
        "• Зарплата Маше 25000\n"
        "• Аренда за июль 45000\n\n"
        "Я сам разберу категорию и запишу в таблицу! ✅",
        reply_markup=get_keyboard()
    )

async def today_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = sheets.get_today_stats()
    if not stats["total"]:
        await update.message.reply_text("📊 Сегодня расходов ещё нет.", reply_markup=get_keyboard())
        return
    text = f"📊 Расходы за сегодня ({stats['date']}):\n\n"
    for cat, amount in stats["by_category"].items():
        text += f"• {cat}: {amount:,.0f} ₽\n"
    text += f"\n💰 Итого: {stats['total']:,.0f} ₽"
    await update.message.reply_text(text, reply_markup=get_keyboard())

async def month_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = sheets.get_month_stats()
    if not stats["total"]:
        await update.message.reply_text("📅 В этом месяце расходов ещё нет.", reply_markup=get_keyboard())
        return
    text = f"📅 Расходы за {stats['month']}:\n\n"
    for cat, amount in stats["by_category"].items():
        text += f"• {cat}: {amount:,.0f} ₽\n"
    text += f"\n💰 Итого: {stats['total']:,.0f} ₽"
    await update.message.reply_text(text, reply_markup=get_keyboard())

async def recent_records(update: Update, context: ContextTypes.DEFAULT_TYPE):
    records = sheets.get_recent_records(10)
    if not records:
        await update.message.reply_text("📋 Записей пока нет.", reply_markup=get_keyboard())
        return
    text = "📋 Последние 10 записей:\n\n"
    for r in records:
        text += f"• {r['date']} | {r['category']} | {r['description']} | {r['amount']:,.0f} ₽\n"
    await update.message.reply_text(text, reply_markup=get_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Как пользоваться:\n\n"
        "Пиши о расходе в свободной форме:\n"
        "› Молоко 20 литров 800 рублей\n"
        "› Ремонт кофемашины 5000\n"
        "› Свет за июнь 3200р\n\n"
        "Категории:\n"
        "☕ Продукты и сырьё\n"
        "👥 Зарплата персонала\n"
        "🏠 Аренда\n"
        "🔧 Оборудование и ремонт\n"
        "💡 Коммунальные услуги\n"
        "📦 Упаковка и расходники",
        reply_markup=get_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📊 Итоги за сегодня":
        await today_stats(update, context)
        return
    elif text == "📅 Итоги за месяц":
        await month_stats(update, context)
        return
    elif text == "📋 Последние записи":
        await recent_records(update, context)
        return
    elif text == "❓ Помощь":
        await help_command(update, context)
        return

    await update.message.reply_text("⏳ Обрабатываю...")
    expense = parse_expense(text)

    if not expense.get("valid"):
        await update.message.reply_text(
            "❓ Не понял запись. Попробуй так:\n"
            "Купил молоко 10 литров за 400 рублей",
            reply_markup=get_keyboard()
        )
        return

    now = datetime.now()
    row = {
        "date": now.strftime("%d.%m.%Y"),
        "time": now.strftime("%H:%M"),
        "category": expense["category"],
        "description": expense["description"],
        "amount": expense["amount"]
    }

    success = sheets.add_expense(row)

    if success:
        await update.message.reply_text(
            f"✅ Записано!\n\n"
            f"📁 {expense['category']}\n"
            f"📝 {expense['description']}\n"
            f"💰 {expense['amount']:,.0f} ₽\n"
            f"📅 {row['date']} {row['time']}",
            reply_markup=get_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Ошибка при сохранении в таблицу.",
            reply_markup=get_keyboard()
        )

def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("today", today_stats))
    app.add_handler(CommandHandler("month", month_stats))
    app.add_handler(CommandHandler("recent", recent_records))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
