import telebot
import bot_config

bot = telebot.TeleBot(bot_config.TELEGRAM_TOKEN)

print("請去 Telegram 傳任何訊息給你的 Bot，等待中...")

@bot.message_handler(func=lambda m: True)
def get_id(message):
    cid = message.chat.id
    name = message.from_user.first_name or ""
    print(f"\n你的 Chat ID：{cid}")
    print(f"請把這行填入 bot_config.py：")
    print(f"ALLOWED_CHAT_IDS = [{cid}]")
    bot.reply_to(message, f"你的 Chat ID：{cid}")
    bot.stop_polling()

bot.infinity_polling(timeout=60)
