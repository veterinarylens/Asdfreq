# handlers/temp_search.py

from telegram import Update, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode, ChatAction

from services.scraper_service import ScraperService
from utils.formatting import build_keyboard, display_results_page
from utils.decorators import rate_limit
from .constants import AWAIT_TEMP_COLLEGE, AWAIT_TEMP_ID, PAGING_RESULTS

async def temp_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    scraper = ScraperService()
    colleges, _ = scraper.fetch_colleges_and_token()
    if not colleges:
        await query.message.edit_text("خطأ في الاتصال بالخادم.", reply_markup=build_keyboard([], back_callback="main_menu"))
        return ConversationHandler.END

    rows = [[InlineKeyboardButton(c['name'], callback_data=f"temp_college_{c['id']}")] for c in colleges]
    await query.message.edit_text(
        "للبحث عن نتائج طالب، اختر الكلية أولاً:",
        reply_markup=build_keyboard(rows, back_callback="main_menu")
    )
    return AWAIT_TEMP_COLLEGE

async def temp_search_college_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['temp_college_id'] = query.data.split('_')[-1]
    await query.message.edit_text("✅ تم اختيار الكلية. الآن، أرسل الرقم الجامعي (10 أرقام).")
    return AWAIT_TEMP_ID

@rate_limit(20)
async def temp_search_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    university_id = update.message.text.strip()
    await update.message.delete()
    processing_message = await context.bot.send_message(chat_id=update.effective_chat.id, text="🔍 جارٍ البحث...")

    if not (university_id.isdigit() and len(university_id) == 10):
        await processing_message.edit_text("⚠️ رقم جامعي غير صالح.")
        return AWAIT_TEMP_ID

    scraper = ScraperService()
    _, token = scraper.fetch_colleges_and_token()
    if not token:
        await processing_message.edit_text("⚠️ خطأ في الاتصال بالخادم.")
        return ConversationHandler.END

    college_id = context.user_data['temp_college_id']
    result = scraper.fetch_full_student_data(college_id, university_id, token)

    if not result.get('success'):
        await processing_message.edit_text(f"⚠️ {result.get('error')}")
        return ConversationHandler.END

    # تجهيز البيانات للعرض
    context.user_data.update({
        'student_info': result['info'],
        'university_id': university_id,
        'full_marks_unfiltered': result['marks'],
        'marks_to_display': sorted(result['marks'], key=lambda x: x.get('date', ''), reverse=True),
        'page': 0
    })

    await display_results_page(update, context, message_to_edit=processing_message)
    return PAGING_RESULTS