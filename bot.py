import os
import json
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
from sheets import SheetsManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация клиентов
claude_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
sheets = SheetsManager()

CATEGORIES = {
    "продукты": "Продукты и сырьё",
    "сырьё": "Продукты и сырьё",
    "кофе": "Продукты и сырьё",
    "молоко": "Продукты и сырьё",
    "зарплата": "Зарплата персонала",
    "персонал": "Зарплата персонала",
    "аренда": "Аренда",
    "оборудование": "Оборудование и ремонт",
    "ремонт": "Оборудование и ремонт",
    "коммунальные": "Коммунальные услуги",
    "свет": "Коммунальные услуги",
    "вода": "Коммунальные услуги",
    "упаковка": "Упаковка и расходники",
    "стаканы": "Упаковка и расходники",
    "расходники": "Упаковка и расходники",
}

SYSTEM_PROMPT = """Ты помощник для учёта расходов кофейни. 

Когда пользователь описывает расход, извлеки:
1. Сумму (число)
2. Категорию из списка:
   - Продукты и сырьё
   - Зарплата персонала
   - Аренда
   - Оборудование и ремонт
   - Коммунальные услуги
   - Упаковка и расходники
3. Краткое описание (что именно куплено/оплачено)

Отвечай ТОЛЬКО в формате JSON:
{
  "amount": число,
  "category": "название категории",
  "description": "краткое описание",
  "valid": true/false
}

Если сообщение не про расход — верни {"valid": false}.
Если сумма не указана — верни {"valid": false}.
"""

def parse_expense_with_claude(text: str) -> dict:
    """Используем Claude для парсинга расхода из свободного текста"""
    try:
        response = claude_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}]
        )
        result = json.loads(response.content[0].text)
        return result
    except Exception as e:
        logger.error(f"Ошибка Claude: {e}")
        return {"valid": False}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["📊 Итоги за сегодня", "📅 Итоги за месяц"],
        ["📋 Последние записи", "❓ Помощь"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "👋 Привет! Я помогу вести учёт расходов твоей кофейни.\n\n"
        "Просто напиши мне о расходе в свободной форме, например:\n"
        "• *Купил зёрна арабики 5 кг за 3500 руб*\n"
        "• *Зарплата Маше 25000*\n"
        "• *Аренда за июль 45000*\n"
        "• *Стаканы 500 штук 1200р*\n\n"
        "Я сам разберу категорию и запишу в таблицу! ✅",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Как пользоваться ботом:*\n\n"
        "*Запись расхода* — просто напиши что купил и за сколько:\n"
        "› Молоко 20 литров 800 рублей\n"
        "› Ремонт кофемашины 5000\n"
        "› Свет за июнь 3200р\n\n"
        "*Категории расходов:*\n"
        "☕ Продукты и сырьё\n"
        "👥 Зарплата персонала\n"
        "🏠 Аренда\n"
        "🔧 Оборудование и ремонт\n"
        "💡 Коммунальные услуги\n"
        "📦 Упаковка и расходники\n\n"
        "*Кнопки меню:*\n"
        "📊 Итоги за сегодня\n"
        "📅 Итоги за месяц\n"
        "📋 Последние записи",
        parse_mode="Markdown"
    )


async def today_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = sheets.get_today_stats()
    if not stats["total"]:
        await update.message.reply_text("📊 Сегодня расходов ещё нет.")
        return
    
    text = f"📊 *Расходы за сегодня ({stats['date']}):*\n\n"
    for cat, amount in stats["by_category"].items():
        text += f"• {cat}: *{amount:,.0f} ₽*\n"
    text += f"\n💰 *Итого: {stats['total']:,.0f} ₽*"
    
    await update.message.reply_text(text, parse_mode="Markdown")


async def month_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = sheets.get_month_stats()
    if not stats["total"]:
        await update.message.reply_text("📅 В этом месяце расходов ещё нет.")
        return
    
    text = f"📅 *Расходы за {stats['month']}:*\n\n"
    for cat, amount in stats["by_category"].items():
        text += f"• {cat}: *{amount:,.0f} ₽*\n"
    text += f"\n💰 *Итого: {stats['total']:,.0f} ₽*"
    
    await update.message.reply_text(text, parse_mode="Markdown")


async def recent_records(update: Update, context: ContextTypes.DEFAULT_TYPE):
    records = sheets.get_recent_records(10)
    if not records:
        await update.message.reply_text("📋 Записей пока нет.")
        return
    
    text = "📋 *Последние 10 записей:*\n\n"
    for r in records:
        text += f"• {r['date']} | {r['category']} | {r['description']} | *{r['amount']:,.0f} ₽*\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    # Обработка кнопок меню
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
    
    # Парсим расход через Claude
    await update.message.reply_text("⏳ Обрабатываю...")
    
    expense = parse_expense_with_claude(text)
    
    if not expense.get("valid"):
        await update.message.reply_text(
            "❓ Не понял запись. Попробуй написать так:\n"
            "*Купил молоко 10 литров за 400 рублей*\n"
            "или\n"
            "*Зарплата баристе 20000*",
            parse_mode="Markdown"
        )
        return
    
    # Сохраняем в Google Sheets
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
            f"✅ *Записано!*\n\n"
            f"📁 Категория: {expense['category']}\n"
            f"📝 Описание: {expense['description']}\n"
            f"💰 Сумма: *{expense['amount']:,.0f} ₽*\n"
            f"📅 Дата: {row['date']} {row['time']}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Ошибка при сохранении. Проверь настройки Google Sheets.")


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("today", today_stats))
    app.add_handler(CommandHandler("month", month_stats))
    app.add_handler(CommandHandler("recent", recent_records))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
