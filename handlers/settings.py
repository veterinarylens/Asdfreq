# handlers/settings.py

from telegram import Update, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from core.config import logger
import db.database as db
from services.scraper_service import ScraperService
from utils.formatting import build_keyboard
from utils.decorators import rate_limit
from .constants import (
    SETTINGS_MAIN, SETTINGS_MANAGE_NUMBERS, SETTINGS_NOTIFICATIONS,
    SETTINGS_AWAIT_DEFAULT_COLLEGE, AWAIT_ADD_COLLEGE, AWAIT_ADD_ALIAS, AWAIT_ADD_ID
)

# --- قائمة الإعدادات الرئيسية ---

async def settings_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يعرض قائمة الإعدادات الرئيسية."""
    query = update.callback_query
    await query.answer()
    rows = [
        [InlineKeyboardButton("🗂️ إدارة الأرقام المحفوظة", callback_data="manage_numbers_menu")],
        [InlineKeyboardButton("🔔 إدارة الإشعارات", callback_data="notifications_menu")],
        [InlineKeyboardButton("🎓 الكلية الافتراضية للبحث", callback_data="default_college_menu")],
    ]
    reply_markup = build_keyboard(rows, back_callback="main_menu")
    await query.message.edit_text(
        "<b>⚙️ الإعدادات</b>\nاختر القسم الذي تريد تعديله:",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )
    return SETTINGS_MAIN

# --- إدارة الأرقام (إضافة/حذف) ---

async def manage_numbers_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يعرض قائمة لإدارة الأرقام المحفوظة."""
    query = update.callback_query
    await query.answer()
    user_numbers = db.get_user_numbers(query.from_user.id)
    
    rows = [[InlineKeyboardButton("➕ إضافة رقم جديد", callback_data="add_number_start")]]
    if user_numbers:
        rows.extend(
            [[InlineKeyboardButton(f"🗑️ حذف: {num['alias']}", callback_data=f"delete_num_confirm_{num['id']}")] 
             for num in user_numbers]
        )
    
    reply_markup = build_keyboard(rows, back_callback="settings_main")
    await query.message.edit_text("<b>🗂️ إدارة الأرقام</b>", parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    return SETTINGS_MANAGE_NUMBERS

@rate_limit(5)
async def delete_number_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يحذف الرقم المختار بعد التأكيد."""
    query = update.callback_query
    number_id = int(query.data.split('_')[-1])
    db.delete_saved_number(number_id)
    await query.answer("🗑️ تم حذف الرقم بنجاح.", show_alert=True)
    
    # تحديث القائمة بعد الحذف
    return await manage_numbers_menu(update, context)

async def add_number_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يبدأ عملية إضافة رقم جديد."""
    query = update.callback_query
    await query.answer()
    
    # تحديد مصدر الطلب (من الإعدادات أو من التوجيه)
    context.user_data['add_number_source'] = "onboarding" if "onboarding" in query.data else "settings"
    
    scraper = ScraperService()
    colleges, _ = scraper.fetch_colleges_and_token()
    if not colleges:
        await query.message.edit_text("خطأ في الاتصال بالخادم.", reply_markup=build_keyboard([], back_callback="manage_numbers_menu"))
        return SETTINGS_MANAGE_NUMBERS
        
    rows = [[InlineKeyboardButton(college['name'], callback_data=f"add_college_{college['id']}")] for college in colleges]
    back_target = "onboarding_start" if context.user_data['add_number_source'] == "onboarding" else "manage_numbers_menu"
    
    await query.message.edit_text(
        "لإضافة رقم جديد، اختر الكلية أولاً:",
        reply_markup=build_keyboard(rows, back_callback=back_target)
    )
    return AWAIT_ADD_COLLEGE

async def add_number_college_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يخزن الكلية المختارة ويطلب الاسم المستعار."""
    query = update.callback_query
    await query.answer()
    context.user_data['add_college_id'] = query.data.split('_')[-1]
    
    back_target = "onboarding_start" if context.user_data.get('add_number_source') == "onboarding" else "manage_numbers_menu"
    
    await query.message.edit_text(
        "✅ تم اختيار الكلية.\n\nالآن، أرسل اسمًا مستعارًا لهذا الرقم (مثال: 'رقمي الشخصي'، 'أخي محمد').",
        reply_markup=build_keyboard([], back_callback=back_target)
    )
    return AWAIT_ADD_ALIAS

async def add_number_alias_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يخزن الاسم المستعار ويطلب الرقم الجامعي."""
    context.user_data['add_alias'] = update.message.text.strip()
    
    # مسح الرسالة التي تحتوي على الاسم المستعار للحفاظ على نظافة المحادثة
    await update.message.delete()
    
    # استعادة الرسالة السابقة لتعديلها
    # هذا يتطلب أن نحفظ message_id
    last_message = context.user_data.get('last_bot_message')
    if not last_message: return AWAIT_ADD_ALIAS # يجب أن تكون هناك رسالة سابقة

    back_target = "add_number_start"
    
    await last_message.edit_text(
        "✅ تم تحديد الاسم المستعار.\n\nالآن، أرسل الرقم الجامعي المكون من 10 أرقام.",
        reply_markup=build_keyboard([], back_callback=back_target)
    )
    return AWAIT_ADD_ID

@rate_limit(10)
async def add_number_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يتحقق من الرقم الجامعي، يحفظه، وينهي العملية."""
    university_id = update.message.text.strip()
    await update.message.delete()
    
    last_message = context.user_data.get('last_bot_message')
    if not last_message: return AWAIT_ADD_ID
    
    if not (university_id.isdigit() and len(university_id) == 10):
        await context.bot.send_message(
            update.effective_chat.id, 
            "⚠️ الرقم الجامعي غير صالح. يجب أن يتكون من 10 أرقام. يرجى المحاولة مرة أخرى."
        )
        return AWAIT_ADD_ID

    # استعادة البيانات من context
    user_id = update.effective_user.id
    alias = context.user_data['add_alias']
    college_id = context.user_data['add_college_id']
    
    db.add_saved_number(user_id, alias, college_id, university_id)
    
    await last_message.edit_text(
        f"👍 تم حفظ الرقم (<b>{alias}</b>) بنجاح!",
        parse_mode=ParseMode.HTML
    )
    
    # بعد تأخير بسيط، نعود إلى القائمة المناسبة
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    
    source = context.user_data.get('add_number_source')
    if source == 'onboarding':
        from .onboarding import skip_onboarding
        return await skip_onboarding(update, context)
    else:
        # نحتاج إلى إنشاء update وهمي للعودة إلى القائمة
        from unittest.mock import Mock
        mock_query = Mock(message=last_message, from_user=update.effective_user, answer=lambda *args, **kwargs: None)
        mock_update = Mock(callback_query=mock_query)
        return await manage_numbers_menu(mock_update, context)

# --- إدارة الإشعارات ---

async def notifications_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يعرض قائمة الأرقام لتبديل حالة الإشعارات."""
    query = update.callback_query
    await query.answer()
    user_numbers = db.get_user_numbers(query.from_user.id)
    
    if not user_numbers:
        await query.message.edit_text("ليس لديك أرقام محفوظة لتفعيل الإشعارات.", reply_markup=build_keyboard([], back_callback="settings_main"))
        return SETTINGS_MAIN
        
    rows = []
    for num in user_numbers:
        status_emoji = "🔔" if num['notifications_enabled'] else "🔕"
        action_text = "إيقاف" if num['notifications_enabled'] else "تفعيل"
        rows.append([InlineKeyboardButton(f"{status_emoji} {num['alias']}", callback_data=f"toggle_notif_{num['id']}")])
    
    await query.message.edit_text(
        "<b>🔔 إدارة الإشعارات</b>\nاضغط على أي رقم لـ (تفعيل/إيقاف) إشعارات صدور علامات جديدة له.", 
        parse_mode=ParseMode.HTML, 
        reply_markup=build_keyboard(rows, back_callback="settings_main")
    )
    return SETTINGS_NOTIFICATIONS

async def toggle_notification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يبدل حالة الإشعار ويعيد تحميل القائمة."""
    query = update.callback_query
    number_id = int(query.data.split('_')[-1])
    new_status = db.toggle_notification_for_number(number_id)
    status_text = "مفعلة" if new_status else "متوقفة"
    await query.answer(f"✅ أصبحت الإشعارات {status_text} لهذا الرقم.", show_alert=True)
    
    # تحديث القائمة لإظهار التغيير
    return await notifications_menu(update, context)


# --- إدارة الكلية الافتراضية ---

async def set_default_college_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يعرض قائمة لاختيار الكلية الافتراضية."""
    query = update.callback_query
    await query.answer()
    
    scraper = ScraperService()
    colleges, _ = scraper.fetch_colleges_and_token()
    if not colleges:
        await query.message.edit_text("خطأ في الاتصال بالخادم.", reply_markup=build_keyboard([], back_callback="settings_main"))
        return SETTINGS_MAIN
    
    rows = [[InlineKeyboardButton(c['name'], callback_data=f"save_def_college_{c['id']}")] for c in colleges]
    rows.append([InlineKeyboardButton("🚫 إزالة الكلية الافتراضية", callback_data="save_def_college_none")])
    
    current_default_id = db.get_default_search_college(query.from_user.id)
    current_college_name = "لا يوجد"
    if current_default_id:
        current_college_name = next((c['name'] for c in colleges if c['id'] == current_default_id), "غير معروفة")
    
    text = f"<b>🎓 الكلية الافتراضية</b>\nالكلية الحالية: <b>{current_college_name}</b>\n\nاختر كلية جديدة لتسريع عمليات البحث المؤقت والإضافة:"
    await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=build_keyboard(rows, back_callback="settings_main"))
    return SETTINGS_AWAIT_DEFAULT_COLLEGE

async def save_default_college(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يحفظ الكلية الافتراضية المختارة."""
    query = update.callback_query
    college_id = query.data.split('save_def_college_')[-1]
    college_id_to_save = None if college_id == 'none' else college_id
    
    db.set_default_search_college(query.from_user.id, college_id_to_save)
    await query.answer("✅ تم حفظ الإعداد بنجاح.", show_alert=True)
    
    return await set_default_college_menu(update, context)