# handlers/results_browser.py

from telegram import Update, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from utils.formatting import build_keyboard, display_results_page
from .constants import PAGING_RESULTS, AWAIT_SEMESTER_FILTER, AWAIT_GPA_YEAR

# --- دوال التصفح (Pagination) ---

async def page_flipper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    page = context.user_data.get('page', 0)
    
    if query.data == "page_next":
        context.user_data['page'] += 1
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
    
    year_map_text = {"1": "الأول", "2": "الثاني", "3": "الثالث", "4": "الرابع", "5": "الخامس", "6": "السادس"}
    available_years = sorted(list(set(
        (f"{val}️⃣ السنة {text}", val)
        for mark in full_marks
        for val, text in year_map_text.items()
        if text in mark.get('semester', '')
    )))

    if not available_years:
        await query.answer("لم يتم العثور على سنوات دراسية في النتائج.", show_alert=True)
        return PAGING_RESULTS

    rows = [[InlineKeyboardButton(text, callback_data=f"filter_year_{val}")] for text, val in available_years]
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
    
    if not year_text: return PAGING_RESULTS

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
    query = update.callback_query
    await query.answer()
    full_marks = context.user_data.get('full_marks_unfiltered', [])
    
    year_map_text = {"1": "الأول", "2": "الثاني", "3": "الثالث", "4": "الرابع", "5": "الخامس", "6": "السادس"}
    available_years = sorted(list(set(
        (text, val)
        for mark in full_marks
        for val, text in year_map_text.items()
        if text in mark.get('semester', '')
    )), key=lambda item: item[1])
    
    if not available_years:
        await query.answer("لا يمكن حساب المعدل.", show_alert=True)
        return PAGING_RESULTS

    rows = [[InlineKeyboardButton(f"السنة {text}", callback_data=f"gpa_calc_year_{val}")] for text, val in available_years]
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
    
    marks_to_calculate, title = [], ""
    if choice == "all":
        marks_to_calculate, title = full_marks, "التراكمي (كل السنوات)"
    elif choice in year_map_text:
        year_text = year_map_text[choice]
        marks_to_calculate = [mark for mark in full_marks if year_text in mark.get('semester', '')]
        title = f"السنة {year_text}"

    total_sum, subject_count = 0, 0
    for mark_data in marks_to_calculate:
        try:
            total_sum += float(mark_data.get('mark', '0'))
            subject_count += 1
        except (ValueError, TypeError): continue

    if subject_count > 0:
        gpa = total_sum / subject_count
        result_text = f"🧮 <b>معدل {title}:</b>\n\n<code>{gpa:.2f} %</code>\n(بناءً على {subject_count} مادة)"
    else:
        result_text = f"⚠️ لم يتم العثور على علامات صالحة لحساب معدل <b>{title}</b>."
    
    reply_markup = build_keyboard([], back_callback="gpa_menu_show")
    await query.message.edit_text(result_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    return AWAIT_GPA_YEAR