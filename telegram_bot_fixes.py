
# تم دمج التعديلات الثلاثة المطلوبة مباشرة في الكود
# ✅ إصلاح زر "إظهار نتائج أخرى"
# ✅ إصلاح أزرار "رجوع"
# ✅ إصلاح الضغط على نتائج "إظهار نتائجي"

# --- selected_number_for_results (المشكلة 3) ---
async def selected_number_for_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        number_id = int(query.data.split('_')[-1])
    except (ValueError, IndexError):
        await query.edit_message_text("⚠️ معرف غير صالح.")
        return ConversationHandler.END

    user_numbers = db.get_user_numbers(query.from_user.id)
    selected_num = next((num for num in user_numbers if num['id'] == number_id), None)

    if selected_num:
        context.user_data['number_info'] = selected_num
        return await fetch_and_show_results(query, context, is_callback=True)

    await query.edit_message_text("⚠️ لم يتم العثور على الرقم المطلوب.")
    return ConversationHandler.END


# --- start_temp_search (المشكلة 1) ---
async def start_temp_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    default_college = db.get_default_search_college(update.effective_user.id)
    context.user_data['temporary_search'] = True  # <-- تأشير المسار المؤقت
    if default_college:
        context.user_data['college_id'] = default_college
        await update.message.reply_text("الكلية الافتراضية محددة. يرجى إرسال الرقم الجامعي مباشرة.",
            reply_markup=InlineKeyboardMarkup([get_nav_buttons()]))
        return AWAIT_ID
    else:
        return await add_or_change_number(update, context)


# --- id_received_for_add (المشكلة 1) ---
async def id_received_for_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    university_id = update.message.text.strip()
    if len(university_id) != 10 or not university_id.isdigit():
        await update.message.reply_text("⚠️ الرقم يجب أن يتكون من 10 أرقام. أعد المحاولة.")
        return AWAIT_ID

    processing_message = await update.message.reply_text("⏳ جارٍ التحقق من الرقم...")
    college_id = context.user_data['college_id']
    token = context.bot_data.get('token') or fetch_colleges_and_token()[1]
    is_valid, student_info, all_marks, error_msg = fetch_full_student_data(college_id, university_id, token)

    if not is_valid or not all_marks:
        error_to_show = error_msg or "لم يتم العثور على أي علامات لهذا الرقم."
        await processing_message.edit_text(f"⚠️ {error_to_show}")
        return AWAIT_ID

    context.user_data.update({
        'student_info': student_info,
        'university_id': university_id,
        'full_marks_unfiltered': all_marks,
        'marks': all_marks,
        'page': 0
    })

    # ⬅️ حالة البحث المؤقت:
    if context.user_data.get('temporary_search'):
        await display_page(update, context, message_to_edit=processing_message)
        return PAGING_RESULTS

    await processing_message.edit_text(f"✅ تم التحقق بنجاح للطالب: {student_info.get('name')}.

الرجاء إعطاء اسم مميز لهذا الرقم (مثلاً: 'رقمي' أو 'رقم أخي').",
        reply_markup=InlineKeyboardMarkup([get_nav_buttons(back_callback="back_to_id_input")]))
    return AWAIT_ALIAS


# --- تعديل add_number_conv handlers (المشكلة 2) ---
add_number_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(lambda u,c: add_or_change_number(u,c,True), pattern="^add_number$")],
    states={
        AWAIT_COLLEGE: [
            CallbackQueryHandler(college_selected_for_add, pattern=r"^\d+$"),
        ],
        AWAIT_ID: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, id_received_for_add),
            CallbackQueryHandler(lambda u,c: add_or_change_number(u,c,True), pattern="^back_to_add_number$")
        ],
        AWAIT_ALIAS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, alias_received_for_add),
            CallbackQueryHandler(lambda u,c: college_selected_for_add(u,c), pattern="^back_to_id_input$")
        ]
    },
    fallbacks=[
        CallbackQueryHandler(manage_numbers_menu, pattern="^back_to_manage_numbers$"),
        CallbackQueryHandler(cancel_inline_operation, pattern="^cancel_op$")
    ]
)

# ⬆️ أضف هذا إلى قسم المعالجات حيث يتم تعريف add_number_conv في ملفك الرئيسي.
