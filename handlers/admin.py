# handlers/admin.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup # <-- تم إضافة InlineKeyboardMarkup هنا
from telegram.ext import ContextTypes, ConversationHandler, filters
from telegram.constants import ParseMode
import json

from core.config import ADMIN_ID, logger
import db.database as db
from .constants import ADMIN_AWAIT_TARGET_USER_ID, ADMIN_AWAIT_MARKS_JSON

# فلتر للتحقق مما إذا كان المستخدم هو المشرف
admin_filter = filters.User(user_id=ADMIN_ID)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يعرض لوحة تحكم المشرف."""
    query = update.callback_query
    await query.answer()
    
    rows = [
        [InlineKeyboardButton("✍️ تعديل نتائج مستخدم", callback_data="admin_set_marks_start")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]
    ]
    keyboard = InlineKeyboardMarkup(rows) # <-- الآن هذا السطر سيعمل بشكل صحيح
    await query.message.edit_text("<b>🛠️ لوحة تحكم المشرف</b>", parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def start_set_marks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """(للمشرف) يبدأ عملية تعديل نتائج مستخدم."""
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("أرسل المعرف الرقمي (User ID) للمستخدم الذي تريد تعديل نتائجه:")
    return ADMIN_AWAIT_TARGET_USER_ID

async def target_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """(للمشرف) يستقبل ID المستخدم ويطلب بيانات JSON."""
    try:
        target_user_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("معرف غير صالح. يجب أن يكون رقمًا.")
        return ADMIN_AWAIT_TARGET_USER_ID

    context.user_data['admin_target_user_id'] = target_user_id
    last_marks_json = db.admin_get_last_marks(target_user_id)

    if not last_marks_json:
        await update.message.reply_text(f"لم يتم العثور على المستخدم {target_user_id} أو ليس لديه نتائج مخزنة.")
        return ConversationHandler.END

    # حذف رسالة المستخدم التي تحتوي على الـ ID
    await update.message.delete()
    
    # تعديل الرسالة السابقة بدلاً من إرسال رسائل جديدة
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=update.effective_message.message_id - 1, # نفترض أن رسالة البوت هي السابقة مباشرة
        text="النتائج الحالية للمستخدم هي (يمكنك تعديلها وإعادة إرسالها):"
    )
    
    await update.effective_chat.send_message(
        f"<code>{json.dumps(json.loads(last_marks_json), indent=2, ensure_ascii=False)}</code>",
        parse_mode=ParseMode.HTML
    )
    await update.effective_chat.send_message(
        "أرسل الآن بيانات JSON الجديدة للنتائج. اكتب /cancel للإلغاء."
    )
    return ADMIN_AWAIT_MARKS_JSON


async def marks_json_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """(للمشرف) يستقبل JSON ويقوم بتحديث قاعدة البيانات."""
    marks_json_string = update.message.text
    target_user_id = context.user_data.get('admin_target_user_id')

    try:
        json.loads(marks_json_string)
    except json.JSONDecodeError:
        await update.message.reply_text("خطأ في تنسيق JSON. يرجى إعادة المحاولة.")
        return ADMIN_AWAIT_MARKS_JSON
        
    if db.admin_set_last_marks(target_user_id, marks_json_string):
        await update.message.reply_text(f"✅ تم تحديث نتائج المستخدم {target_user_id} بنجاح.")
    else:
        await update.message.reply_text(f"❌ فشل تحديث نتائج المستخدم {target_user_id}.")

    # استيراد محلي لتجنب الاستيراد الدائري
    from .main_handlers import show_main_menu
    await show_main_menu(update, context)
    return ConversationHandler.END

async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """(للمشرف) إلغاء عملية التعديل."""
    await update.message.reply_text("تم إلغاء العملية.")
    
    # استيراد محلي لتجنب الاستيراد الدائري
    from .main_handlers import show_main_menu
    await show_main_menu(update, context)
    return ConversationHandler.END