# core/config.py

import os
import logging
from dotenv import load_dotenv

# تحميل متغيرات البيئة من ملف .env
load_dotenv()

# --- إعدادات البوت الأساسية ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise ValueError("خطأ: لم يتم العثور على متغير BOT_TOKEN. يرجى إضافته إلى ملف .env")
if ADMIN_ID == 0:
    print("تحذير: لم يتم تعيين ADMIN_ID في ملف .env. ميزات المشرف ستكون معطلة.")


# --- إعدادات قاعدة البيانات ---
DATABASE_PATH = os.getenv("DATABASE_PATH", "hama_bot.sqlite")

# --- إعدادات خدمة استخلاص البيانات ---
BASE_URL = "http://app.hama-univ.edu.sy/StdMark/"
RESULT_URL = f"{BASE_URL}Home/Result"
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", 3600))
REQUEST_TIMEOUT = 20 

# --- إعدادات التسجيل (Logging) ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# --- إعدادات أخرى ---
RESULTS_PER_PAGE = 5 # يمكن زيادة عدد النتائج المعروضة الآن