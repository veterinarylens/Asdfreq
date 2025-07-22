# handlers/onboarding.py

from telegram import Update, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from utils.formatting import build_keyboard, get_main_menu_keyboard
from .constants import AWAIT_ONBOARDING_CHOICE

async def onboarding_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يبدأ محادثة الترحيب والتوجيه للمستخدم الجديد.
    """
    user = update.effective_user
    text = (
        f"السلام عليكم ورحمة الله وبركاته، أهلاً بك يا {user.first_name} في بوت نتائج جامعة حماة!\n\n"
        "لتسهيل الوصول لنتائجك وتلقي إشعارات فور صدورها، يمكنك إضافة رقمك الجامعي الآن."
    )
    rows = [[
        InlineKeyboardButton("➕ إضافة رقمي الجامعي الآن", callback_data="add_number_onboarding"),
        InlineKeyboardButton("⏩ تخطي للمرة الحالية", callback_data="skip_onboarding")
    ]]
    keyboard = build_keyboard(rows, add_main_menu=False) # لا نريد زر القائمة الرئيسية هنا
    
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)
    
    # تحديد أن رسالة الترحيب قد عُرضت
    context.user_data['onboarding_shown'] = True
    
    return AWAIT_ONBOARDING_CHOICE


async def skip_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    عندما يختار المستخدم تخطي إضافة الرقم في البداية.
    """
    query = update.callback_query
    await query.answer()
    
    text = "حسناً، يمكنك دائماً إضافة أرقامك لاحقاً من قائمة الإعدادات.\n\nاختر ما تريد من القائمة:"
    await query.message.edit_text(text, reply_markup=get_main_menu_keyboard())
    
    return ConversationHandler.END