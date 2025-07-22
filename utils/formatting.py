# utils/formatting.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import json

from core.config import RESULTS_PER_PAGE, ADMIN_ID

def build_keyboard(rows: list, add_main_menu: bool = True, back_callback: str = None) -> InlineKeyboardMarkup:
    """
    دالة مركزية لبناء لوحات المفاتيح.
    تضيف تلقائيًا زر القائمة الرئيسية وزر الرجوع إذا تم توفيرهما.
    """
    if add_main_menu:
        nav_row = []
        if back_callback:
            nav_row.append(InlineKeyboardButton("⬅️ رجوع", callback_data=back_callback))
        nav_row.append(InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))
        rows.append(nav_row)
        
    return InlineKeyboardMarkup(rows)

def build_main_menu(user_data: dict) -> tuple[str, InlineKeyboardMarkup]:
    """
    يبني القائمة الرئيسية بناءً على حالة المستخدم وميزاته.
    """
    user_id = user_data.get('id')
    university_id = user_data.get('university_id')
    notifications_enabled = user_data.get('notifications_enabled', 1)
    
    student_info_str = user_data.get('student_info')
    student_info = json.loads(student_info_str) if student_info_str else {}

    rows = []
    if university_id:
        name = student_info.get('name', 'N/A')
        college = student_info.get('college_name', 'N/A')
        text = (
            f"أهلاً بك، <b>{name}</b>.\n"
            f"<b>الرقم الجامعي:</b> <code>{university_id}</code>\n"
            f"<b>الكلية:</b> {college}\n\n"
            "اختر أحد الخيارات:"
        )
        rows.append([InlineKeyboardButton("📄 عرض كل نتائجي", callback_data="show_all_my_results")])
        rows.append([InlineKeyboardButton("🔄 التحقق من وجود نتائج جديدة", callback_data="check_new_results")])
        rows.append([InlineKeyboardButton("🔍 بحث مؤقت عن نتائج أخرى", callback_data="temp_search_start")])
        
        notif_emoji = "🔔" if notifications_enabled else "🔕"
        notif_text = f"{notif_emoji} الإشعارات"
        rows.append([
            InlineKeyboardButton(notif_text, callback_data="toggle_notifications"),
            InlineKeyboardButton("🗑️ حذف بياناتي", callback_data="delete_my_data")
        ])
        
        # إضافة زر المشرف إذا كان المستخدم هو المشرف
        if user_id == ADMIN_ID:
            rows.append([InlineKeyboardButton("🛠️ لوحة تحكم المشرف", callback_data="admin_panel")])
    else:
        text = (
            "أهلاً بك في بوت نتائج جامعة حماة!\n\n"
            "يبدو أنك لم تقم بتسجيل رقمك الجامعي بعد. "
            "اضغط على الزر أدناه للبدء."
        )
        rows.append([InlineKeyboardButton("➕ تسجيل رقمي الجامعي", callback_data="register_start")])
    
    rows.append([InlineKeyboardButton("❓ مساعدة", callback_data="help_menu")])
    return text, InlineKeyboardMarkup(rows)

def format_new_marks_message(marks: list, title: str) -> str:
    """تنسق رسالة النتائج الجديدة فقط."""
    if not marks:
        return f"✅ {title}"

    text = f"<b>{title}</b>\n" + "--------------------------------------\n"
    for mark in marks:
        status_emoji = "✅" if "ناجح" in mark.get('status', '') else "⛔" if "راسب" in mark.get('status', '') else "⚪"
        text += (
            f"📖 <b>{mark.get('subject', 'N/A')}</b>: {mark.get('mark', 'N/A')} {status_emoji}\n"
            f"📅 <i>{mark.get('date', 'N/A')}</i>\n"
            "--------------------------------------\n"
        )
    return text

async def display_results_page(update: Update, context: ContextTypes.DEFAULT_TYPE, message_to_edit=None):
    """
    دالة مركزية لعرض صفحة من النتائج مع تصفح وفرز.
    """
    query = update.callback_query
    if query:
        await query.answer()

    user_data = context.user_data
    page = user_data.get('page', 0)
    marks = user_data.get('marks_to_display', [])
    student_info = user_data.get('student_info', {})
    
    total_marks = len(marks)
    start_index = page * RESULTS_PER_PAGE
    end_index = (page + 1) * RESULTS_PER_PAGE
    page_marks = marks[start_index:end_index]

    text = (f"👤 <b>{student_info.get('name', 'N/A')}</b>\n"
            f"🎓 {student_info.get('college_name', 'N/A')} | 🆔 {user_data.get('university_id', 'N/A')}\n"
            f"--------------------------------------\n"
            f"📄 النتائج {start_index + 1}-{min(end_index, total_marks)} من {total_marks}")

    for mark in page_marks:
        status = mark.get('status', '')
        status_emoji = "✅" if "ناجح" in status else "⛔" if "راسب" in status else "⚪"
        text += (f"\n--------------------------------------\n"
                 f"🔹 <i>{mark.get('semester', 'N/A')}</i>\n"
                 f"📖 <b>المادة:</b> {mark.get('subject', 'N/A')}\n"
                 f"{status_emoji} <b>الحالة:</b> {status} | 📝 <b>العلامة:</b> {mark.get('mark', 'N/A')}\n"
                 f"🔄 <b>الدورة:</b> {mark.get('session', 'N/A')} | 📅 <b>التاريخ:</b> {mark.get('date', 'N/A')}")

    rows, nav_row = [], []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ السابق", callback_data="page_prev"))
    if end_index < total_marks:
        nav_row.append(InlineKeyboardButton("التالي ➡️", callback_data="page_next"))
    
    if nav_row:
        rows.append(nav_row)

    rows.append([
        InlineKeyboardButton("📊 فرز وتصنيف", callback_data="sort_menu_show"),
        InlineKeyboardButton("🧮 حساب المعدل", callback_data="gpa_menu_show")
    ])

    reply_markup = build_keyboard(rows, back_callback="main_menu")

    target_message = message_to_edit or (query.message if query else None)
    
    if target_message:
        try:
            await target_message.edit_text(text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        except Exception: pass
    elif update.message:
        await update.message.reply_text(text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)