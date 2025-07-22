# main.py

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
)
import json

# --- استيراد الإعدادات والخدمات الأساسية ---
from core.config import BOT_TOKEN, CHECK_INTERVAL_SECONDS, logger
import db.database as db
from services.scraper_service import ScraperService
from utils.formatting import format_new_marks_message, display_results_page

# --- استيراد ثوابت الحالات ---
from handlers.constants import *

# --- استيراد المعالجات من الوحدات المخصصة ---
from handlers.registration import (
    register_start, college_selected, university_id_received, registration_cancel
)
from handlers.main_handlers import (
    start_command, show_main_menu, show_all_my_results, check_new_results,
    toggle_notifications_handler, delete_my_data_confirm, delete_my_data_confirmed,
    help_menu
)
from handlers.temp_search import (
    temp_search_start, temp_search_college_selected, temp_search_id_received
)
from handlers.results_browser import (
    page_flipper, show_sort_menu, sort_results, show_year_filter_menu, filter_by_year,
    filter_by_semester, show_gpa_year_menu, calculate_and_show_gpa
)
from handlers.admin import (
    admin_filter, admin_panel, start_set_marks, target_user_id_received, 
    marks_json_received, admin_cancel
)
from handlers.common import error_handler

# --- مهمة الخلفية لفحص العلامات الجديدة ---
async def check_for_new_marks_job(context):
    logger.info("بدء الفحص الدوري للعلامات الجديدة...")
    users_to_check = db.get_all_users_for_check()
    if not users_to_check:
        logger.info("لا توجد أرقام مفعلة للإشعارات. تخطي الفحص.")
        return

    scraper = ScraperService()
    _, token = scraper.fetch_colleges_and_token()
    if not token:
        logger.warning("فشل في الحصول على token. إلغاء فحص الإشعارات لهذه الدورة.")
        return
        
    for user in users_to_check:
        try:
            result = scraper.fetch_full_student_data(user['college_id'], user['university_id'], token)
            if not result.get('success'): continue

            old_marks = json.loads(user.get('last_known_marks', '[]'))
            newly_found_marks = scraper.find_new_marks(old_marks, result['marks'])

            if newly_found_marks:
                logger.info(f"تم اكتشاف علامات جديدة للمستخدم {user['id']} عبر المهمة الدورية.")
                response_text = format_new_marks_message(newly_found_marks, "🎉 إشعار بنتائج جديدة!")
                await context.bot.send_message(chat_id=user['id'], text=response_text, parse_mode='HTML')
                db.update_user_marks(user['id'], result['marks'])
        except Exception as e:
            logger.error(f"خطأ أثناء فحص العلامات للمستخدم {user['id']}: {e}", exc_info=True)

def main() -> None:
    db.init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    
    if CHECK_INTERVAL_SECONDS > 0:
        application.job_queue.run_repeating(check_for_new_marks_job, interval=CHECK_INTERVAL_SECONDS, first=10)

    # --- تعريف الحالات المشتركة لعرض النتائج ---
    results_browser_states = {
        PAGING_RESULTS: [
            CallbackQueryHandler(page_flipper, pattern=r"^page_(next|prev)$"),
            CallbackQueryHandler(show_sort_menu, pattern=r"^sort_menu_show$"),
            CallbackQueryHandler(sort_results, pattern=r"^sort_(newest|oldest)$"),
            CallbackQueryHandler(show_year_filter_menu, pattern=r"^sort_by_year_show$"),
            CallbackQueryHandler(filter_by_year, pattern=r"^filter_year_"),
            CallbackQueryHandler(show_gpa_year_menu, pattern=r"^gpa_menu_show$"),
            CallbackQueryHandler(lambda u,c: display_results_page(u,c,message_to_edit=u.callback_query.message), pattern="^back_to_results$")
        ],
        AWAIT_SEMESTER_FILTER: [
            CallbackQueryHandler(filter_by_semester, pattern=r"^filter_semester_"),
            CallbackQueryHandler(show_year_filter_menu, pattern=r"^sort_by_year_show$"),
        ],
        AWAIT_GPA_YEAR: [
            CallbackQueryHandler(calculate_and_show_gpa, pattern=r"^gpa_calc_year_"),
            CallbackQueryHandler(show_gpa_year_menu, pattern=r"^gpa_menu_show$"),
        ]
    }

    # --- تعريف المحادثات ---
    registration_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(register_start, pattern=r"^register_start$")],
        states={
            AWAIT_COLLEGE: [CallbackQueryHandler(college_selected, pattern=r"^reg_college_")],
            AWAIT_UNIVERSITY_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, university_id_received)],
        },
        fallbacks=[CallbackQueryHandler(registration_cancel, pattern=r"^cancel_registration$")],
    )

    admin_set_marks_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_set_marks, pattern=r"^admin_set_marks_start$")],
        states={
            ADMIN_AWAIT_TARGET_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, target_user_id_received)],
            ADMIN_AWAIT_MARKS_JSON: [MessageHandler(filters.TEXT & ~filters.COMMAND, marks_json_received)],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
    )

    my_results_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(show_all_my_results, pattern=r"^show_all_my_results$")],
        states={**results_browser_states},
        fallbacks=[CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$")]
    )

    temp_search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(temp_search_start, pattern=r"^temp_search_start$")],
        states={
            AWAIT_TEMP_COLLEGE: [CallbackQueryHandler(temp_search_college_selected, pattern=r"^temp_college_")],
            AWAIT_TEMP_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, temp_search_id_received)],
            **results_browser_states
        },
        fallbacks=[CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$")]
    )
    
    # --- تسجيل المعالجات ---
    application.add_handler(CommandHandler("start", start_command))
    
    # المحادثات
    application.add_handler(registration_conv)
    application.add_handler(admin_set_marks_conv)
    application.add_handler(my_results_conv)
    application.add_handler(temp_search_conv)
    
    # الأزرار المستقلة
    application.add_handler(CallbackQueryHandler(check_new_results, pattern=r"^check_new_results$"))
    application.add_handler(CallbackQueryHandler(toggle_notifications_handler, pattern=r"^toggle_notifications$"))
    application.add_handler(CallbackQueryHandler(delete_my_data_confirm, pattern=r"^delete_my_data$"))
    application.add_handler(CallbackQueryHandler(delete_my_data_confirmed, pattern=r"^delete_my_data_confirmed$"))
    application.add_handler(CallbackQueryHandler(help_menu, pattern=r"^help_menu$"))
    application.add_handler(CallbackQueryHandler(admin_panel, pattern=r"^admin_panel$"))
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$"))
    
    application.add_error_handler(error_handler)

    logger.info("البوت قيد التشغيل بالهيكلية المدمجة الجديدة...")
    application.run_polling()

if __name__ == "__main__":
    main()