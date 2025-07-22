# handlers/results.py

from telegram import Update, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode, ChatAction

from core.config import logger
import db.database as db
from services.scraper_service import ScraperService
from utils.formatting import build_keyboard, display_results_page
from .constants import (
    AWAIT_SAVED_NUMBER_CHOICE, PAGING_RESULTS, AWAIT_SEMESTER_FILTER, AWAIT_GPA_YEAR
)

# --- نقطة الدخول ودوال جلب البيانات ---

async def my_results_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نقطة الدخول لعرض النتائج المحفوظة."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    user_numbers = db.get_user_numbers(user_id)
    if not user_numbers:
        rows = [[InlineKeyboardButton("➕ إضافة رقم الآن", callback_data="add_number_start")]]
        await query.message.edit_text(
            "لم تقم بحفظ أي أرقام بعد. يمكنك إضافتها من الإعدادات.", 
            reply_markup=build_keyboard(rows, back_callback="settings_main")
        )
        return ConversationHandler.END

    if len(user_numbers) == 1:
        # إذا كان هناك رقم واحد فقط، ابدأ بالجلب مباشرة
        await query.message.edit_text("🔍 جارٍ جلب بيانات رقمك الوحيد...")
        context.user_data['number_info'] = user_numbers[0]
        return await fetch_and_display_results(update, context, message_to_handle=query.message)
    
    # إذا كان هناك عدة أرقام، اعرض قائمة للاختيار
    rows = [[InlineKeyboardButton(f"👤 {num['alias']}", callback_data=f"select_num_{num['id']}")] for num in user_numbers]
    await query.message.edit_text(
        "لديك عدة أرقام محفوظة. اختر واحداً لعرض نتائجه:", 
        reply_markup=build_keyboard(rows, back_callback="main_menu")
    )
    return AWAIT_SAVED_NUMBER_CHOICE

async def selected_number_for_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يعالج اختيار المستخدم لرقم معين من القائمة."""
    query = update.callback_query
    await query.answer()
    number_id = int(query.data.split('_')[-1])
    number_info = next((num for num in db.get_user_numbers(query.from_user.id) if num['id'] == number_id), None)
    
    if not number_info:
        await query.message.edit_text("خطأ: لم يتم العثور على الرقم.", reply_markup=build_keyboard([], back_callback="main_menu"))
        return ConversationHandler.END

    await query.message.edit_text(f"🔍 جارٍ جلب بيانات: <b>{number_info['alias']}</b>...", parse_mode=ParseMode.HTML)
    context.user_data['number_info'] = number_info
    return await fetch_and_display_results(update, context, message_to_handle=query.message)


async def fetch_and_display_results(update: Update, context: ContextTypes.DEFAULT_TYPE, message_to_handle) -> int:
    """تجلب البيانات الفعلية من الخدمة وتعرضها."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    number_info = context.user_data['number_info']
    
    scraper = ScraperService()
    _, token = scraper.fetch_colleges_and_token()
    if not token:
        await message_to_handle.edit_text("خطأ: لا يمكن الاتصال بخادم الجامعة حاليًا.", reply_markup=build_keyboard([], back_callback="main_menu"))
        return ConversationHandler.END

    result = scraper.fetch_full_student_data(number_info['college_id'], number_info['university_id'], token)
    
    if not result.get('success'):
        await message_to_handle.edit_text(f"⚠️ {result.get('error', 'حدث خطأ غير معروف.')}", reply_markup=build_keyboard([], back_callback="main_menu"))
        return ConversationHandler.END

    # تحديث تجزئة العلامات في قاعدة البيانات
    new_hash = scraper.generate_marks_hash(result['marks'])
    if 'id' in number_info: # تأكد من أنه رقم محفوظ وليس بحث مؤقت
        db.update_marks_hash(number_info['id'], new_hash)

    # تخزين البيانات في user_data للاستخدام في التصفح والفرز
    context.user_data.update({
        'student_info': result['info'],
        'university_id': number_info['university_id'],
        'full_marks_unfiltered': result['marks'],
        'marks_to_display': sorted(result['marks'], key=lambda x: x.get('date', ''), reverse=True), # الأحدث أولاً افتراضيًا
        'page': 0
    })
    
    await display_results_page(update, context, message_to_edit=message_to_handle)
    return PAGING_RESULTS

# --- دوال التصفح (Pagination) ---

async def page_flipper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يتعامل مع أزرار التالي والسابق."""
    query = update.callback_query
    page = context.user_data.get('page', 0)
    
    if query.data == "page_next":
        context.user_data['page'] = page + 1
    elif query.data == "page_prev":
        context.user_data['page'] = max(0, page - 1)
        
    await display_results_page(update, context, message_to_edit=query.message)
    return PAGING_RESULTS


# --- دوال الفرز والتصنيف (Sorting) ---

async def show_sort_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    rows = [
        [InlineKeyboardButton("🗓️ الأحدث أولاً", callback_data="sort_newest"), InlineKeyboardButton("🕰️ الأقدم أولاً", callback_data="sort_oldest")],
        [InlineKeyboardButton("🧑‍🏫 حسب السنة الدراسية", callback_data="sort_by_year_show")],
    ]
    reply_markup = build_keyboard(rows, back_callback="back_to_results")
    await query.message.edit_text("اختر طريقة الفرز والتصنيف:", reply_markup=reply_markup)
    return PAGING_RESULTS

async def sort_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    full_marks = context.user_data.get('full_marks_unfiltered', [])
    
    if query.data == "sort_newest":
        context.user_data['marks_to_display'] = sorted(full_marks, key=lambda x: x.get('date', ''), reverse=True)
    elif query.data == "sort_oldest":
        context.user_data['marks_to_display'] = sorted(full_marks, key=lambda x: x.get('date', ''))
        
    context.user_data['page'] = 0
    await display_results_page(update, context, message_to_edit=query.message)
    return PAGING_RESULTS


async def show_year_filter_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    full_marks = context.user_data.get('full_marks_unfiltered', [])
    
    # استخلاص السنوات المتاحة من النتائج
    year_map_text = {"1": "الأول", "2": "الثاني", "3": "الثالث", "4": "الرابع", "5": "الخامس", "6": "السادس"}
    available_years = set()
    for mark in full_marks:
        for val, text in year_map_text.items():
            if text in mark.get('semester', ''):
                available_years.add((f"{val}️⃣ السنة {text}", val))

    if not available_years:
        await query.answer("لم يتم العثور على سنوات دراسية في النتائج.", show_alert=True)
        return PAGING_RESULTS

    rows = [[InlineKeyboardButton(text, callback_data=f"filter_year_{val}")] for text, val in sorted(available_years)]
    reply_markup = build_keyboard(rows, back_callback="sort_menu_show")
    await query.message.edit_text("اختر السنة لعرض نتائجها فقط:", reply_markup=reply_markup)
    return PAGING_RESULTS


async def filter_by_year(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    chosen_year_val = query.data.split('_')[-1]
    full_marks = context.user_data.get('full_marks_unfiltered', [])
    
    year_map_text = {"1": "الأول", "2": "الثاني", "3": "الثالث", "4": "الرابع", "5": "الخامس", "6": "السادس"}
    year_text = year_map_text.get(chosen_year_val)
    
    if not year_text:
        return PAGING_RESULTS # في حالة وجود بيانات خاطئة

    # تخزين النتائج المفلترة حسب السنة مؤقتًا
    context.user_data['year_filtered_marks'] = [mark for mark in full_marks if year_text in mark.get('semester', '')]
    
    rows = [
        [InlineKeyboardButton("1️⃣ الفصل الأول", callback_data="filter_semester_1"),
         InlineKeyboardButton("2️⃣ الفصل الثاني", callback_data="filter_semester_2")],
        [InlineKeyboardButton("♾️ عرض كل نتائج السنة", callback_data="filter_semester_all")],
    ]
    reply_markup = build_keyboard(rows, back_callback="sort_by_year_show")
    await query.message.edit_text(f"تم اختيار السنة {year_text}. الآن اختر الفصل:", reply_markup=reply_markup)
    return AWAIT_SEMESTER_FILTER


async def filter_by_semester(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    semester_choice = query.data.split('_')[-1]
    year_filtered_marks = context.user_data.get('year_filtered_marks', [])
    
    if semester_choice == "1":
        context.user_data['marks_to_display'] = [m for m in year_filtered_marks if "الأول" in m.get('semester', '')]
    elif semester_choice == "2":
        context.user_data['marks_to_display'] = [m for m in year_filtered_marks if "الثاني" in m.get('semester', '')]
    else: # "all"
        context.user_data['marks_to_display'] = year_filtered_marks
        
    context.user_data['page'] = 0
    await display_results_page(update, context, message_to_edit=query.message)
    return PAGING_RESULTS


# --- دوال حساب المعدل (GPA) ---

async def show_gpa_year_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # نفس منطق show_year_filter_menu لكن بأزرار مختلفة
    query = update.callback_query
    await query.answer()
    full_marks = context.user_data.get('full_marks_unfiltered', [])
    
    year_map_text = {"1": "الأول", "2": "الثاني", "3": "الثالث", "4": "الرابع", "5": "الخامس", "6": "السادس"}
    available_years = set()
    for mark in full_marks:
        for val, text in year_map_text.items():
            if text in mark.get('semester', ''):
                available_years.add((text, val))
    
    if not available_years:
        await query.answer("لا يمكن حساب المعدل لعدم وجود سنوات دراسية واضحة.", show_alert=True)
        return PAGING_RESULTS

    rows = [[InlineKeyboardButton(f"السنة {text}", callback_data=f"gpa_calc_year_{val}")] for text, val in sorted(available_years, key=lambda item: item[1])]
    rows.append([InlineKeyboardButton("📈 المعدل التراكمي (كل السنوات)", callback_data="gpa_calc_year_all")])
    
    reply_markup = build_keyboard(rows, back_callback="back_to_results")
    await query.message.edit_text("اختر السنة لحساب المعدل:", reply_markup=reply_markup)
    return AWAIT_GPA_YEAR

async def calculate_and_show_gpa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    choice = query.data.split('gpa_calc_year_')[-1]
    full_marks = context.user_data.get('full_marks_unfiltered', [])
    
    year_map_text = {"1": "الأول", "2": "الثاني", "3": "الثالث", "4": "الرابع", "5": "الخامس", "6": "السادس"}
    
    marks_to_calculate = []
    title = ""
    if choice == "all":
        marks_to_calculate = full_marks
        title = "التراكمي (كل السنوات)"
    elif choice in year_map_text:
        year_text = year_map_text[choice]
        marks_to_calculate = [mark for mark in full_marks if year_text in mark.get('semester', '')]
        title = f"السنة {year_text}"

    total_sum, subject_count = 0, 0
    for mark_data in marks_to_calculate:
        try:
            # محاولة تحويل العلامة إلى رقم. تجاهل المواد التي ليس لها علامة رقمية (مثل "منقول").
            mark_value = float(mark_data.get('mark', '0'))
            total_sum += mark_value
            subject_count += 1
        except (ValueError, TypeError):
            continue

    if subject_count > 0:
        gpa = total_sum / subject_count
        result_text = f"🧮 <b>معدل {title}:</b>\n\n<code>{gpa:.2f} %</code>\n\n(بناءً على {subject_count} مادة ذات علامات رقمية)"
    else:
        result_text = f"⚠️ لم يتم العثور على علامات رقمية صالحة لحساب معدل <b>{title}</b>."
    
    reply_markup = build_keyboard([], back_callback="gpa_menu_show")
    await query.message.edit_text(result_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    return AWAIT_GPA_YEAR