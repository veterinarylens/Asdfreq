# main.py (الإصدار الاحترافي مع الإعدادات وميزات UX المحسنة)

import logging
import requests
import json
import os
import random
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# --- الإعدادات الأساسية ---
import os
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
USER_DATA_FILE = "user_database.json"

BASE_URL = "http://app.hama-univ.edu.sy/StdMark/"
RESULT_URL = f"{BASE_URL}Home/Result"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Referer': BASE_URL
})

# حالات المحادثة
REG_AWAIT_COLLEGE, REG_AWAIT_ID = range(2)
TEMP_AWAIT_COLLEGE, TEMP_AWAIT_ID, TEMP_AWAIT_YEAR = range(2, 5)
MY_RESULTS_AWAIT_YEAR = 5
PAGING_RESULTS = 6
DELETE_CONFIRMATION = 7 # حالة جديدة لتأكيد الحذف

RESULTS_PER_PAGE = 4

# --- دوال إدارة بيانات المستخدمين ---
def load_user_data():
    if not os.path.exists(USER_DATA_FILE): return {}
    try:
        with open(USER_DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError): return {}

def save_user_data(data):
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=4)

# --- دوال الواجهة والتنقل المحسنة ---
def get_emoji_for_college(name: str) -> str:
    emoji_map = { "الطب": "🧑‍⚕️", "البشري": "🧑‍⚕️", "الصيدلة": "💊", "الأسنان": "🦷", "الهندسة": "📐", "المعلوماتية": "💻", "المدنية": "🏗️", "المعمارية": "🏛️", "الميكاترونيك": "🤖", "الزراعة": "🧑‍🌾", "البيطري": "🐾", "العلوم": "🔬", "التربية": "🧑‍🏫", "الرياضية": "🤸", "الآداب": "📖", "الاقتصاد": "📈", "الحقوق": "⚖️", "التمريض": "🩺" }
    for keyword, emoji in emoji_map.items():
        if keyword in name: return f"{emoji} {name}"
    return f"🎓 {name}"

def get_nav_buttons(back_callback: str = None):
    row = []
    if back_callback:
        row.append(InlineKeyboardButton("⬅️ رجوع", callback_data=back_callback))
    row.append(InlineKeyboardButton("❌ إلغاء الأمر", callback_data="cancel_op"))
    return row

async def cancel_inline_operation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ تم إلغاء الأمر.")
    return ConversationHandler.END

def extract_available_years_and_create_keyboard(all_marks: list, back_callback: str = None) -> InlineKeyboardMarkup:
    available_years = {}
    full_years_map = { "الأول": ("1️⃣ السنة الأولى", "1"), "الثاني": ("2️⃣ السنة الثانية", "2"), "الثالث": ("3️⃣ السنة الثالثة", "3"), "الرابع": ("4️⃣ السنة الرابعة", "4"), "الخامس": ("5️⃣ السنة الخامسة", "5"), "السادس": ("6️⃣ السنة السادسة", "6") }
    for mark in all_marks:
        semester_text = mark.get('semester', '')
        for year_keyword, (year_display, year_value) in full_years_map.items():
            if year_keyword in semester_text:
                available_years[year_value] = year_display
                break
    keyboard = []
    year_buttons = [InlineKeyboardButton(text, callback_data=val) for val, text in sorted(available_years.items())]
    for i in range(0, len(year_buttons), 2):
        keyboard.append(year_buttons[i:i+2])
    keyboard.append([InlineKeyboardButton("📚 كل السنوات", callback_data="all")])
    if back_callback:
        keyboard.append(get_nav_buttons(back_callback=back_callback))
    else:
        keyboard.append([InlineKeyboardButton("❌ إلغاء الأمر", callback_data="cancel_op")])
    return InlineKeyboardMarkup(keyboard)

# --- دوال استخلاص البيانات ---
def fetch_colleges_and_token():
    try:
        response = session.get(BASE_URL, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        token_input = soup.find("input", {"name": "__RequestVerificationToken"})
        if not token_input: return None, None
        token = token_input["value"]
        college_select = soup.find("select", {"name": "CollegeId"})
        if not college_select: return None, None
        colleges = [(get_emoji_for_college(opt.text.strip()), opt.get("value")) for opt in college_select.find_all("option")[1:] if opt.get("value")]
        return colleges, token
    except Exception as e:
        logger.error(f"فشل جلب الكليات: {e}", exc_info=True)
        return None, None

def fetch_full_student_data(college_id: str, university_id: str, token: str, year: str = ""):
    payload = {"UniversityId": university_id, "CollegeId": college_id, "__RequestVerificationToken": token, "Year": year}
    try:
        response = session.post(RESULT_URL, data=payload, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        error_div = soup.find("div", class_="validation-summary-errors")
        if error_div:
            return False, None, None, "الرقم غير صحيح أو غير موجود في هذه الكلية."

        student_info = {}
        # استخلاص البيانات من البطاقة العلوية إن وجدت
        info_card = soup.find("div", class_="card-body")
        if info_card:
            spans = info_card.find_all("span", class_="head")
            for span in spans:
                next_span = span.find_next_sibling("span", class_="bottom")
                if next_span:
                    if "الاسم" in span.text and "الأب" not in span.text:
                        student_info['name'] = next_span.text.strip()
                    elif "اسم الأب" in span.text:
                        student_info['father_name'] = next_span.text.strip()
                    elif "الكلية" in span.text:
                        student_info['college_name'] = next_span.text.strip()

        result_panels = soup.find_all('div', class_='panel-info')
        all_marks = []
        if result_panels:
            for panel in result_panels:
                panel_heading_div = panel.find('div', class_='panel-heading')
                heading = panel_heading_div.text.strip() if panel_heading_div else "فصل غير محدد"
                table = panel.find('table', class_='table')
                if table and (tbody := table.find('tbody')):
                    for row in tbody.find_all('tr'):
                        cols = [td.text.strip() for td in row.find_all('td')]
                        if len(cols) >= 5: all_marks.append({"subject": cols[0], "session": cols[1], "mark": cols[2], "status": cols[3], "date": cols[4], "semester": heading})
        
        # إذا لم يتم العثور على أي معلومات أو علامات، فالرقم غير صالح
        if not student_info and not all_marks:
             return False, None, None, "لم يتم العثور على أي بيانات لهذا الرقم الجامعي."

        all_marks.reverse()
        return True, student_info, all_marks, None
    except Exception as e:
        logger.error(f"فشل التحقق والجلب: {e}", exc_info=True)
        return False, None, None, "حدث خطأ أثناء الاتصال بالخادم."

# --- دوال عرض النتائج والتقليب ---
async def display_page(update: Update, context: ContextTypes.DEFAULT_TYPE, message_to_edit=None):
    query = update.callback_query
    if query: await query.answer()
    user_data = context.user_data
    page, marks = user_data.get('page', 0), user_data.get('marks', [])
    total_marks = len(marks)
    start_index = page * RESULTS_PER_PAGE
    end_index = start_index + RESULTS_PER_PAGE
    page_marks = marks[start_index:end_index]
    
    student_info = user_data.get('student_info', {})
    text = f"👤 <b>الاسم:</b> {student_info.get('name', 'غير متوفر')}\n"
    text += f"👨‍💼 <b>اسم الأب:</b> {student_info.get('father_name', 'غير متوفر')}\n"
    text += f"🎓 <b>الكلية:</b> {student_info.get('college_name', 'غير متوفرة')}\n"
    text += f"🆔 <b>الرقم الجامعي:</b> {user_data.get('university_id', '')}\n"
    text += f"--------------------------------------\n"
    text += f"📄 <b>عرض النتائج {start_index + 1}-{min(end_index, total_marks)} من {total_marks}</b>\n"

    for mark in page_marks:
        status = mark.get('status', '')
        status_emoji = "✅" if "ناجح" in status else "⛔" if "راسب" in status else "⚪"
        text += "--------------------------------------\n"
        text += f"🔹 <i>{mark.get('semester', '')}</i>\n"
        text += f"📖 <b>المادة:</b> {mark.get('subject', '')}\n{status_emoji} <b>الحالة:</b> {status}\n"
        text += f"📝 <b>العلامة:</b> {mark.get('mark', '')}\n🔄 <b>الدورة:</b> {mark.get('session', '')} | 📅 <b>التاريخ:</b> {mark.get('date', '')}\n"
    
    keyboard, row = [], []
    if page > 0: row.append(InlineKeyboardButton("⬅️ السابق", callback_data="prev_page"))
    if end_index < total_marks: row.append(InlineKeyboardButton("التالي ➡️", callback_data="next_page"))
    if row: keyboard.append(row)
    
    back_callback = "back_to_my_results_year_select" if context.user_data.get('is_my_results') else "back_to_temp_year_select"
    keyboard.append([InlineKeyboardButton("⬅️ رجوع لاختيار السنة", callback_data=back_callback)])
    keyboard.append([InlineKeyboardButton("🛑 إنهاء الاستعراض", callback_data="exit_paging")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    target_message = message_to_edit or (query.message if query else None)
    if target_message: await target_message.edit_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else: await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def page_flipper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    command = query.data
    if command == "exit_paging":
        await query.edit_message_text("تم إنهاء الاستعراض.")
        context.user_data.clear()
        return ConversationHandler.END
    page = context.user_data.get('page', 0)
    context.user_data['page'] = page + 1 if command == "next_page" else page - 1
    await display_page(update, context)
    return PAGING_RESULTS

# --- مسار التسجيل وتغيير الرقم ---
async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback=False):
    colleges, token = fetch_colleges_and_token()
    if not colleges:
        message_sender = update.callback_query.message if is_callback else update.message
        await message_sender.reply_text("عذراً، لا يمكن الاتصال بخادم الجامعة الآن.")
        return ConversationHandler.END
    context.bot_data['token'] = token
    keyboard = [[InlineKeyboardButton(name, callback_data=cid)] for name, cid in colleges]
    keyboard.append(get_nav_buttons())
    message_text = "الرجاء اختيار كليتك الافتراضية:"
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_sender = update.callback_query if is_callback else update.message
    if is_callback: await message_sender.edit_message_text(text=message_text, reply_markup=reply_markup)
    else: await message_sender.reply_text(message_text, reply_markup=reply_markup)
    return REG_AWAIT_COLLEGE

async def reg_college_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['reg_college_id'] = query.data
    await query.edit_message_text("✅ تم اختيار الكلية.\n\nالآن، يرجى إرسال رقمك الجامعي المكون من 10 أرقام.",
        reply_markup=InlineKeyboardMarkup([get_nav_buttons(back_callback="back_to_reg_college")]))
    return REG_AWAIT_ID

async def reg_receive_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    university_id = update.message.text.strip()
    if len(university_id) != 10 or not university_id.isdigit():
        await update.message.reply_text("⚠️ الرقم الجامعي يجب أن يتكون من 10 أرقام بالضبط. يرجى المحاولة مرة أخرى.")
        return REG_AWAIT_ID
    processing_message = await update.message.reply_text("⏳ جارٍ التحقق من الرقم...")
    college_id = context.user_data['reg_college_id']
    token = context.bot_data['token']
    is_valid, _, _, error_msg = fetch_full_student_data(college_id, university_id, token)
    if not is_valid:
        await processing_message.edit_text(f"⚠️ {error_msg}")
        return REG_AWAIT_ID
    await processing_message.edit_text("✅ تم التحقق من الرقم بنجاح!")
    user_db = load_user_data()
    user_id = str(update.effective_user.id)
    user_db[user_id] = {"college_id": college_id, "university_id": university_id}
    save_user_data(user_db)
    await update.message.reply_text("👍 تم حفظ بياناتك الافتراضية.")
    await show_main_menu(update, context)
    return ConversationHandler.END

# --- المسار الرئيسي والقائمة السفلية ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["إظهار نتائجي 📄"], ["إظهار نتائج أخرى 🔍", "الإعدادات ⚙️"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    user = update.effective_user
    welcome_messages = [f"أهلاً بعودتك، {user.first_name}! 👋", f"مرحباً مجدداً، {user.first_name}! 😊"]
    await update.message.reply_text(random.choice(welcome_messages), reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_db = load_user_data()
    user_id = str(update.effective_user.id)
    if user_id not in user_db:
        user = update.effective_user
        welcome_messages = [f"مرحباً بك {user.first_name} 👋!", f"يا أهلاً بك {user.first_name} ✨!"]
        await update.message.reply_text(f"{random.choice(welcome_messages)}\nللبدء، نحتاج لحفظ بياناتك.", reply_markup=ReplyKeyboardRemove())
        return await start_registration(update, context, is_callback=False)
    else:
        await show_main_menu(update, context)
        return ConversationHandler.END

# --- مسار "إظهار نتائجي" ---
async def show_my_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_db = load_user_data()
    user_id = str(update.effective_user.id)
    user_info = user_db.get(user_id)
    if not user_info:
        await update.message.reply_text("لم أجد بيانات محفوظة لك. يمكنك إضافتها من الإعدادات.")
        return ConversationHandler.END
    processing_message = await update.message.reply_text("🔍 جارٍ جلب بياناتك...")
    _, token = fetch_colleges_and_token()
    if not token:
        await processing_message.edit_text("فشل الاتصال بالخادم.")
        return ConversationHandler.END
    is_valid, student_info, all_marks, error_msg = fetch_full_student_data(user_info['college_id'], user_info['university_id'], token)
    if not is_valid:
        await processing_message.edit_text(f"خطأ: الرقم المحفوظ لم يعد صالحاً. {error_msg}")
        return ConversationHandler.END
    context.user_data.update({'student_info': student_info, 'university_id': user_info['university_id'], 'full_marks': all_marks, 'is_my_results': True})
    reply_markup = extract_available_years_and_create_keyboard(all_marks)
    await processing_message.edit_text("✅ تم جلب البيانات. اختر السنة لعرض نتائجها:", reply_markup=reply_markup)
    return MY_RESULTS_AWAIT_YEAR

# --- مسار البحث المؤقت ---
async def start_temp_search(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback=False):
    colleges, token = fetch_colleges_and_token()
    if not colleges:
        message_sender = update.callback_query.message if is_callback else update.message
        await message_sender.reply_text("عذراً، لا يمكن الاتصال بخادم الجامعة الآن.")
        return ConversationHandler.END
    context.bot_data['token'] = token
    keyboard = [[InlineKeyboardButton(name, callback_data=cid)] for name, cid in colleges]
    keyboard.append(get_nav_buttons())
    message_text = "بحث مؤقت: اختر الكلية:"
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_sender = update.callback_query if is_callback else update.message
    if is_callback: await message_sender.edit_message_text(text=message_text, reply_markup=reply_markup)
    else: await message_sender.reply_text(message_text, reply_markup=reply_markup)
    return TEMP_AWAIT_COLLEGE

async def temp_college_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['temp_college_id'] = query.data
    await query.edit_message_text("✅ تم اختيار الكلية.\n\nالآن، يرجى إرسال الرقم الجامعي للتحقق منه.",
        reply_markup=InlineKeyboardMarkup([get_nav_buttons(back_callback="back_to_temp_college")]))
    return TEMP_AWAIT_ID

async def temp_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    university_id = update.message.text.strip()
    if len(university_id) != 10 or not university_id.isdigit():
        await update.message.reply_text("⚠️ الرقم يجب أن يتكون من 10 خانات. يرجى إعادة المحاولة.")
        return TEMP_AWAIT_ID
    processing_message = await update.message.reply_text("⏳ جارٍ التحقق من الرقم...")
    college_id = context.user_data['temp_college_id']
    token = context.bot_data['token']
    is_valid, student_info, all_marks, error_msg = fetch_full_student_data(college_id, university_id, token)
    if not is_valid:
        await processing_message.edit_text(f"⚠️ {error_msg}")
        return TEMP_AWAIT_ID
    context.user_data.update({'university_id': university_id, 'student_info': student_info, 'full_marks': all_marks, 'is_my_results': False})
    reply_markup = extract_available_years_and_create_keyboard(all_marks, back_callback="back_to_temp_id")
    await processing_message.edit_text("✅ تم التحقق بنجاح. اختر السنة الدراسية:", reply_markup=reply_markup)
    return TEMP_AWAIT_YEAR

async def filter_and_display_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chosen_year = query.data
    full_marks = context.user_data.get("full_marks", [])
    filtered_marks = [mark for mark in full_marks if chosen_year == 'all' or any(keyword in mark.get('semester', '') for keyword in {"1": ["الأول"], "2": ["الثاني"], "3": ["الثالث"], "4": ["الرابع"], "5": ["الخامس"], "6": ["السادس"]}.get(chosen_year, []))]
    if not filtered_marks:
        await query.edit_message_text("لا توجد نتائج مسجلة لهذه السنة تحديداً.")
        context.user_data.clear()
        return ConversationHandler.END
    context.user_data['marks'] = filtered_marks
    context.user_data['page'] = 0
    await display_page(update, context, message_to_edit=query.message)
    return PAGING_RESULTS

# --- مسار الإعدادات ---
async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_db = load_user_data()
    user_id = str(update.effective_user.id)
    keyboard = []
    if user_id in user_db:
        keyboard.append([InlineKeyboardButton("🔄 تغيير الرقم الجامعي الافتراضي", callback_data="change_default")])
        keyboard.append([InlineKeyboardButton("🗑️ مسح بياناتي المحفوظة", callback_data="delete_data_prompt")])
    else:
        keyboard.append([InlineKeyboardButton("➕ إضافة رقم جامعي افتراضي", callback_data="change_default")])
    keyboard.append([InlineKeyboardButton("ℹ️ حول البوت", callback_data="about_bot")])
    keyboard.append([InlineKeyboardButton("✉️ للتواصل والملاحظات", url="https://t.me/Mhamad_Alabdullah")]) # استبدل بمعرفك
    keyboard.append([InlineKeyboardButton("⬅️ العودة للقائمة الرئيسية", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚙️ الإعدادات", reply_markup=reply_markup)

async def settings_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "change_default":
        await query.message.delete()
        return await start_registration(update.callback_query, context, is_callback=True)
    elif query.data == "about_bot":
        await query.edit_message_text(
            text="ℹ️ **حول البوت**\n\nهذا البوت مصمم لمساعدة طلاب جامعة حماة في الوصول إلى علاماتهم الدراسية بسهولة وسرعة.\n\n**الميزات:**\n- حفظ رقمك الجامعي للوصول السريع.\n- البحث عن نتائج أي طالب آخر.\n- عرض النتائج بشكل مرتب ومنظم.\n\nتم التطوير بواسطة: [Mhamad Alabdullah](https://t.me/Mhamad_Alabdullah)",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع للإعدادات", callback_data="back_to_settings")]])
        )
    elif query.data == "back_to_main":
        await query.edit_message_text("👍 تم العودة للقائمة الرئيسية.")
    elif query.data == "back_to_settings":
        await show_settings_menu(query, context)

async def delete_data_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("✅ نعم، أنا متأكد", callback_data="confirm_delete")],
        [InlineKeyboardButton("❌ لا، تراجع", callback_data="cancel_delete")]
    ]
    await query.edit_message_text("⚠️ **تأكيد الحذف**\n\nهل أنت متأكد من رغبتك في حذف بياناتك المحفوظة (الكلية والرقم الجامعي)؟\nهذا الإجراء لا يمكن التراجع عنه.", 
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return DELETE_CONFIRMATION

async def perform_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_db = load_user_data()
    user_id = str(update.effective_user.id)
    if user_id in user_db:
        del user_db[user_id]
        save_user_data(user_db)
        await query.edit_message_text("🗑️ تم حذف بياناتك بنجاح.")
    else:
        await query.edit_message_text("لم يتم العثور على بيانات محفوظة لحذفها.")
    return ConversationHandler.END

async def cancel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("👍 تم إلغاء عملية الحذف.")
    return ConversationHandler.END

# --- تجميع كل شيء في الدالة الرئيسية ---
def main() -> None:
    if "YOUR_BOT_TOKEN_HERE" in BOT_TOKEN:
        print("خطأ: لم يتم تعيين توكن البوت.")
        return
    application = Application.builder().token(BOT_TOKEN).build()
    
    # معالجات التنقل
    async def back_to_reg_college(u, c): return await start_registration(u, c, is_callback=True)
    async def back_to_temp_college(u, c): return await start_temp_search(u, c, is_callback=True)
    async def back_to_temp_id(u, c): return await temp_college_selected(u, c)
    async def back_to_year_select(u, c):
        is_my_results = c.user_data.get('is_my_results')
        back_cb = "back_to_main" if is_my_results else "back_to_temp_id"
        reply_markup = extract_available_years_and_create_keyboard(c.user_data['full_marks'], back_callback=back_cb)
        await u.callback_query.edit_message_text("اختر سنة أخرى لعرض نتائجها:", reply_markup=reply_markup)
        return TEMP_AWAIT_YEAR if not is_my_results else MY_RESULTS_AWAIT_YEAR

    # تعريف المحادثات
    conv_handlers = {
        "start": ConversationHandler(entry_points=[CommandHandler("start", start)], states={
            REG_AWAIT_COLLEGE: [CallbackQueryHandler(reg_college_selected, pattern="^((?!cancel_op).)*$")],
            REG_AWAIT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_receive_id), CallbackQueryHandler(back_to_reg_college, pattern="^back_to_reg_college$")],
        }, fallbacks=[CallbackQueryHandler(cancel_inline_operation, pattern="^cancel_op$")]),
        
        "registration": ConversationHandler(entry_points=[CallbackQueryHandler(lambda u,c: start_registration(u,c,is_callback=True), pattern="^change_default$")], states={
            REG_AWAIT_COLLEGE: [CallbackQueryHandler(reg_college_selected, pattern="^((?!cancel_op).)*$")],
            REG_AWAIT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_receive_id), CallbackQueryHandler(back_to_reg_college, pattern="^back_to_reg_college$")],
        }, fallbacks=[CallbackQueryHandler(cancel_inline_operation, pattern="^cancel_op$")]),

        "temp_search": ConversationHandler(entry_points=[MessageHandler(filters.Regex("^إظهار نتائج أخرى 🔍$"), start_temp_search)], states={
            TEMP_AWAIT_COLLEGE: [CallbackQueryHandler(temp_college_selected, pattern="^((?!cancel_op).)*$")],
            TEMP_AWAIT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, temp_id_received), CallbackQueryHandler(back_to_temp_college, pattern="^back_to_temp_college$")],
            TEMP_AWAIT_YEAR: [CallbackQueryHandler(filter_and_display_year, pattern="^((?!back_to_temp_id|cancel_op).)*$"), CallbackQueryHandler(back_to_temp_id, pattern="^back_to_temp_id$")],
            PAGING_RESULTS: [CallbackQueryHandler(page_flipper, pattern="^(prev_page|next_page|exit_paging)$"), CallbackQueryHandler(back_to_year_select, pattern="^back_to_temp_year_select$")],
        }, fallbacks=[CallbackQueryHandler(cancel_inline_operation, pattern="^cancel_op$")], conversation_timeout=600),
        
        "my_results": ConversationHandler(entry_points=[MessageHandler(filters.Regex("^إظهار نتائجي 📄$"), show_my_results)], states={
            MY_RESULTS_AWAIT_YEAR: [CallbackQueryHandler(filter_and_display_year, pattern="^((?!cancel_op).)*$")],
            PAGING_RESULTS: [CallbackQueryHandler(page_flipper, pattern="^(prev_page|next_page|exit_paging)$"), CallbackQueryHandler(back_to_year_select, pattern="^back_to_my_results_year_select$")]
        }, fallbacks=[CallbackQueryHandler(cancel_inline_operation, pattern="^cancel_op$")]),
        
        "delete_data": ConversationHandler(entry_points=[CallbackQueryHandler(delete_data_prompt, pattern="^delete_data_prompt$")], states={
            DELETE_CONFIRMATION: [CallbackQueryHandler(perform_delete, pattern="^confirm_delete$"), CallbackQueryHandler(cancel_delete, pattern="^cancel_delete$")]
        }, fallbacks=[])
    }

    application.add_handler(MessageHandler(filters.Regex("^الإعدادات ⚙️$"), show_settings_menu))
    application.add_handler(CallbackQueryHandler(settings_menu_handler, pattern="^(about_bot|back_to_main|back_to_settings)$"))
    for handler in conv_handlers.values():
        application.add_handler(handler)
    
    print("البوت قيد التشغيل... اضغط CTRL+C للإيقاف.")
    application.run_polling()

if __name__ == "__main__":
    main()
