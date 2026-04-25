import logging
import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from PyPDF2 import PdfReader
from openai import OpenAI

# إعداد السجلات (Logging)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- إعدادات الخادم المصغر لمنع التوقف ---
app = Flask('')

@app.route('/')
def home():
    return "البوت يعمل بنجاح!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.start()

# --- إعدادات البوت ---
# يفضل وضع التوكن في متغيرات البيئة (Environment Variables) للأمان
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8730374550:AAGus8qN4Rx4UimOxQtC11WutFIvZbuz01k")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# تهيئة عميل OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

# ذاكرة مؤقتة لتخزين محتوى الملفات لكل مستخدم
user_documents = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("مرحباً بك في بوت المواد الدراسية! 📚\n\nأرسل لي ملف PDF أو نص، وسأقوم بالإجابة على أي سؤال تطرحه حول محتواه.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    document = update.message.document

    if document.mime_type in ["application/pdf", "text/plain"]:
        await update.message.reply_text("جاري معالجة الملف، يرجى الانتظار ثواني... ⏳")
        
        file_id = document.file_id
        new_file = await context.bot.get_file(file_id)
        file_name = document.file_name
        file_path = f"./{file_name}"
        await new_file.download_to_drive(file_path)

        text_content = ""
        try:
            if document.mime_type == "application/pdf":
                with open(file_path, "rb") as f:
                    reader = PdfReader(f)
                    for page in reader.pages:
                        text_content += page.extract_text() or ""
            else: # text/plain
                with open(file_path, "r", encoding="utf-8") as f:
                    text_content = f.read()

            if text_content.strip():
                user_documents[user_id] = text_content
                await update.message.reply_text(f"✅ تم استلام ملف '{file_name}' بنجاح! تفضل بطرح سؤالك.")
            else:
                await update.message.reply_text("❌ الملف يبدو فارغاً أو تعذر استخراج النص منه.")
        
        except Exception as e:
            logger.error(f"Error processing file: {e}")
            await update.message.reply_text("عذراً، حدث خطأ أثناء معالجة الملف.")
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        await update.message.reply_text("⚠️ عذراً، أدعم ملفات PDF والنصوص فقط.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_question = update.message.text

    if user_id not in user_documents:
        await update.message.reply_text("الرجاء إرسال ملف أولاً قبل طرح الأسئلة.")
        return

    document_content = user_documents[user_id]

    try:
        # إرسال حالة "جاري الكتابة" للمستخدم
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "أنت مساعد خبير في تحليل المواد الدراسية. أجب بدقة واختصار بناءً على المحتوى المقدم فقط. إذا لم تجد الإجابة، قل أنك لم تجدها في الملف."},
                {"role": "user", "content": f"المحتوى المستخرج من الملف:\n{document_content[:15000]}\n\nالسؤال: {user_question}"} # تحديد الحد الأقصى للنص المرسل
            ]
        )
        answer = response.choices[0].message.content
        await update.message.reply_text(answer)
    except Exception as e:
        logger.error(f"Error with OpenAI API: {e}")
        await update.message.reply_text("عذراً، حدث خطأ في النظام أثناء محاولة الإجابة.")

def main() -> None:
    # تشغيل خادم الويب في الخلفية
    keep_alive()
    
    # تشغيل البوت
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
