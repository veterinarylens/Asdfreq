# handlers/main_handlers.py

import json
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode, ChatAction

import db.database as db
from services.scraper_service import ScraperService
from utils.formatting import build_main_menu, format_new_marks_message, display_results_page
from utils.decorators import rate_limit
from .constants import PAGING_RESULTS

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message_to_replace=None) -> None:
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    user_data = db.get_user_data(user_id)
    text, keyboard = build_main_menu(user_data)

    target_message = message_to_replace or (query.message if query else update.message)
    try:
        await target_message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        await update.effective_chat.send_message(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

async def show_all_my_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يعرض كل النتائج المخزنة للمستخدم مع ميزات التصفح والفرز."""
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("🔍 جارٍ تحميل نتائجك المخزنة...")
    
    user_id = update.effective_user.id
    user_data = db.get_user_data(user_id)
    
    all_marks = json.loads(user_data.get('last_known_marks', '[]'))
    student_info = json.loads(user_data.get('student_info', '{}'))
    
    # تجهيز البيانات للعرض
    context.user_data.update({
        'student_info': student_info,
        'university_id': user_data.get('university_id'),
        'full_marks_unfiltered': all_marks,
        'marks_to_display': sorted(all_marks, key=lambda x: x.get('date', ''), reverse=True),
        'page': 0
    })
    
    await display_results_page(update, context, message_to_edit=query.message)
    return PAGING_RESULTS

@rate_limit(60)
async def check_new_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("🔄 جاري التحقق من موقع الجامعة...")

    user_id = update.effective_user.id
    user_data = db.get_user_data(user_id)
    
    college_id = user_data.get('college_id')
    university_id = user_data.get('university_id')
    old_marks = json.loads(user_data.get('last_known_marks', '[]'))

    scraper = ScraperService()
    _, token = scraper.fetch_colleges_and_token()
    if not token:
        await query.message.edit_text("⚠️ خطأ في الاتصال بالخادم. يرجى المحاولة لاحقًا.", reply_markup=build_main_menu(user_data)[1])
        return

    result = scraper.fetch_full_student_data(college_id, university_id, token)

    if not result.get('success'):
        await query.message.edit_text(f"⚠️ {result.get('error')}", reply_markup=build_main_menu(user_data)[1])
        return

    new_marks_list = scraper.find_new_marks(old_marks, result['marks'])

    if new_marks_list:
        db.update_user_marks(user_id, result['marks'])
        response_text = format_new_marks_message(new_marks_list, "🎉 تم العثور على نتائج جديدة!")
        await query.message.edit_text(response_text, parse_mode=ParseMode.HTML, reply_markup=build_main_menu(db.get_user_data(user_id))[1])
    else:
        await query.message.edit_text("✅ لا توجد نتائج جديدة. بياناتك محدّثة.", reply_markup=build_main_menu(user_data)[1])

async def toggle_notifications_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    new_status = db.toggle_notifications(user_id)
    await query.answer(f"أصبحت الإشعارات التلقائية {' مفعلة' if new_status else 'متوقفة'}", show_alert=True)
    await show_main_menu(update, context)

async def delete_my_data_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (نفس الكود السابق بدون تغيير)
    pass
async def delete_my_data_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (نفس الكود السابق بدون تغيير)
    pass
async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (نفس الكود السابق بدون تغيير)
    pass