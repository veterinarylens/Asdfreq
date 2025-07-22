# handlers/registration.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup # <-- تم إضافة InlineKeyboardMarkup هنا
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode, ChatAction

from core.config import logger
import db.database as db
from services.scraper_service import ScraperService
from .constants import AWAIT_COLLEGE, AWAIT_UNIVERSITY_ID

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يبدأ عملية تسجيل رقم جامعي جديد للمستخدم."""
    query = update.callback_query
    await query.answer()

    scraper = ScraperService()
    colleges, _ = scraper.fetch_colleges_and_token()
    if not colleges:
        await query.message.edit_text("خطأ في الاتصال بخادم الجامعة. لا يمكن التسجيل حاليًا.")
        return ConversationHandler.END
        
    rows = [[InlineKeyboardButton(college['name'], callback_data=f"reg_college_{college['id']}")] for college in colleges]
    keyboard = InlineKeyboardMarkup(rows)
    
    await query.message.edit_text(
        "لتسجيل رقمك، يرجى اختيار كليتك من القائمة:",
        reply_markup=keyboard
    )
    return AWAIT_COLLEGE

async def college_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يخزن الكلية المختارة ويطلب الرقم الجامعي."""
    query = update.callback_query
    await query.answer()
    context.user_data['reg_college_id'] = query.data.split('_')[-1]
    
    await query.message.edit_text("✅ تم اختيار الكلية.\n\nالآن، أرسل رقمك الجامعي المكون من 10 أرقام.")
    return AWAIT_UNIVERSITY_ID

async def university_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    يتحقق من الرقم الجامعي، يحفظه مع النتائج الأولية، وينهي عملية التسجيل.
    """
    university_id = update.message.text.strip()
    chat = update.effective_chat
    
    if not (university_id.isdigit() and len(university_id) == 10):
        await chat.send_message("⚠️ الرقم الجامعي غير صالح. يجب أن يتكون من 10 أرقام. يرجى المحاولة مرة أخرى.")
        return AWAIT_UNIVERSITY_ID

    await chat.send_chat_action(ChatAction.TYPING)
    # نحذف رسالة المستخدم التي تحتوي على الرقم
    await update.message.delete() 
    # ونعدل الرسالة السابقة للبوت
    previous_message = context.user_data.get('last_bot_message')
    if previous_message:
        processing_message = await previous_message.edit_text("🔍 جاري التحقق من الرقم وجلب النتائج الأولية...")
    else: # في حالة عدم وجود رسالة سابقة، نرسل واحدة جديدة
        processing_message = await chat.send_message("🔍 جاري التحقق من الرقم وجلب النتائج الأولية...")

    user_id = update.effective_user.id
    college_id = context.user_data['reg_college_id']
    
    scraper = ScraperService()
    _, token = scraper.fetch_colleges_and_token()
    if not token:
        await processing_message.edit_text("خطأ: لا يمكن الاتصال بخادم الجامعة حاليًا.")
        return ConversationHandler.END

    result = scraper.fetch_full_student_data(college_id, university_id, token)
    
    if not result.get('success'):
        await processing_message.edit_text(f"⚠️ فشل التحقق: {result.get('error', 'حدث خطأ غير معروف.')}")
        return ConversationHandler.END

    # حفظ البيانات في قاعدة البيانات
    db.save_user_number_and_results(
        user_id=user_id,
        college_id=college_id,
        university_id=university_id,
        student_info=result['info'],
        marks=result['marks']
    )
    
    name = result.get('info', {}).get('name', '')
    await processing_message.edit_text(
        f"✅ تم التسجيل بنجاح!\nأهلاً بك يا <b>{name}</b>. يمكنك الآن استخدام ميزات البوت.",
        parse_mode=ParseMode.HTML
    )
    
    # استيراد محلي لتجنب الاستيراد الدائري
    from .main_handlers import show_main_menu
    await show_main_menu(update, context, message_to_replace=processing_message) # عرض القائمة الرئيسية بعد التسجيل الناجح
    
    return ConversationHandler.END

async def registration_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء عملية التسجيل."""
    query = update.callback_query
    await query.message.edit_text("تم إلغاء عملية التسجيل.")
    
    from .main_handlers import show_main_menu
    await show_main_menu(update, context)
    
    return ConversationHandler.END