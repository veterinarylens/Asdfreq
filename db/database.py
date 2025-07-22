# db/database.py

import sqlite3
import threading
import json
from core.config import DATABASE_PATH, logger

# استخدام lock لضمان عدم حدوث تضارب في الوصول إلى قاعدة البيانات
db_lock = threading.Lock()

def get_db_connection():
    """إنشاء اتصال آمن بقاعدة البيانات."""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """تهيئة جدول قاعدة البيانات بالهيكلية الجديدة."""
    with db_lock:
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY,                -- Telegram User ID
                        college_id TEXT,                       -- معرف الكلية
                        university_id TEXT,                    -- الرقم الجامعي
                        student_info TEXT,                     -- معلومات الطالب (JSON)
                        last_known_marks TEXT,                 -- آخر علامات معروفة (JSON)
                        notifications_enabled INTEGER DEFAULT 1 -- تفعيل/تعطيل الإشعارات
                    );
                """)
            logger.info("قاعدة البيانات تم تهيئتها بالهيكلية الجديدة.")
        finally:
            conn.close()

def get_user_data(user_id):
    """جلب كامل بيانات المستخدم من قاعدة البيانات."""
    with db_lock:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            user_data = cursor.fetchone()
            if not user_data:
                # إذا لم يكن المستخدم موجودًا، قم بإنشائه
                cursor.execute("INSERT INTO users (id) VALUES (?)", (user_id,))
                conn.commit()
                # ثم أعد جلبه مرة أخرى
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                user_data = cursor.fetchone()
            return dict(user_data) if user_data else None
        finally:
            conn.close()

def save_user_number_and_results(user_id, college_id, university_id, student_info, marks):
    """حفظ أو تحديث رقم المستخدم ونتائجه الأولية."""
    student_info_json = json.dumps(student_info, ensure_ascii=False)
    marks_json = json.dumps(marks, ensure_ascii=False)
    with db_lock:
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("""
                    UPDATE users
                    SET college_id = ?, university_id = ?, student_info = ?, last_known_marks = ?
                    WHERE id = ?
                """, (college_id, university_id, student_info_json, marks_json, user_id))
            logger.info(f"تم حفظ بيانات ونتائج المستخدم {user_id} بنجاح.")
        finally:
            conn.close()

def update_user_marks(user_id, new_marks):
    """تحديث قائمة العلامات للمستخدم."""
    new_marks_json = json.dumps(new_marks, ensure_ascii=False)
    with db_lock:
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("UPDATE users SET last_known_marks = ? WHERE id = ?", (new_marks_json, user_id))
            logger.info(f"تم تحديث علامات المستخدم {user_id}.")
        finally:
            conn.close()

def get_all_users_for_check():
    """جلب كل المستخدمين الذين لديهم أرقام محفوظة ومفعلين الإشعارات."""
    with db_lock:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # جلب المستخدمين الذين لديهم رقم جامعي مسجل فقط
            cursor.execute("SELECT * FROM users WHERE university_id IS NOT NULL AND notifications_enabled = 1")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

def toggle_notifications(user_id):
    """تبديل حالة الإشعارات للمستخدم."""
    with db_lock:
        conn = get_db_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT notifications_enabled FROM users WHERE id = ?", (user_id,))
                current_status = cursor.fetchone()[0]
                new_status = 0 if current_status == 1 else 1
                cursor.execute("UPDATE users SET notifications_enabled = ? WHERE id = ?", (new_status, user_id))
                return new_status
        finally:
            conn.close()

# --- Admin Feature ---
def admin_get_last_marks(user_id):
    """(للمشرف) جلب العلامات الأخيرة لمستخدم معين كـ JSON string."""
    with db_lock:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT last_known_marks FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            conn.close()

def admin_set_last_marks(user_id, marks_json_string):
    """(للمشرف) تعيين العلامات الأخيرة لمستخدم معين باستخدام JSON string."""
    with db_lock:
        conn = get_db_connection()
        try:
            # التحقق من أن النص هو JSON صالح قبل الحفظ
            json.loads(marks_json_string) 
            with conn:
                conn.execute("UPDATE users SET last_known_marks = ? WHERE id = ?", (marks_json_string, user_id))
            return True
        except (json.JSONDecodeError, sqlite3.Error) as e:
            logger.error(f"Admin failed to set marks for {user_id}: {e}")
            return False
        finally:
            conn.close()