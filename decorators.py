# utils/decorators.py

import time
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

def rate_limit(limit_seconds: int):
    """
    Decorator لمنع المستخدم من استدعاء دالة معينة بشكل متكرر.
    """
    def decorator(func):
        @wraps(func)
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            # التأكد من وجود update و user_id
            if not (update and update.effective_user):
                return await func(update, context, *args, **kwargs)
                
            user_id = update.effective_user.id
            # إنشاء مفتاح فريد لكل دالة لتجنب التضارب
            func_key = f'last_call_{func.__name__}'
            
            # جلب وقت آخر استدعاء من user_data
            last_called = context.user_data.get(func_key, 0)
            
            elapsed = time.time() - last_called
            
            if elapsed < limit_seconds:
                # حساب الوقت المتبقي
                remaining = round(limit_seconds - elapsed)
                if update.callback_query:
                    await update.callback_query.answer(
                        f"⏳ الرجاء الانتظار {remaining} ثانية قبل المحاولة مرة أخرى.",
                        show_alert=True
                    )
                else:
                    await update.effective_message.reply_text(
                        f"⏳ الرجاء الانتظار {remaining} ثانية قبل المحاولة مرة أخرى."
                    )
                return
            
            # تحديث وقت آخر استدعاء
            context.user_data[func_key] = time.time()
            return await func(update, context, *args, **kwargs)
        return wrapped
    return decorator