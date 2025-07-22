# handlers/common.py (النسخة الصحيحة والمبسطة)

from telegram import Update
from telegram.ext import ContextTypes
from core.config import logger

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    معالج الأخطاء العام. يسجل الأخطاء ويرسل رسالة لطيفة للمستخدم.
    """
    logger.error("حدث استثناء أثناء معالجة تحديث:", exc_info=context.error)

    # التحقق من وجود كائن update والدردشة قبل محاولة إرسال رسالة
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ حدث خطأ تقني غير متوقع. تم إبلاغ المطور بالمشكلة.\n\n"
                     "يرجى المحاولة مرة أخرى لاحقًا أو العودة إلى /start."
            )
        except Exception as e:
            logger.error(f"فشل في إرسال رسالة الخطأ للمستخدم: {e}")