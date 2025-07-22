# services/scraper_service.py

import requests
import json
from pathlib import Path
from bs4 import BeautifulSoup
from cachetools import cached, TTLCache

from core.config import (
    BASE_URL,
    RESULT_URL,
    REQUEST_TIMEOUT,
    logger,
)

class ScraperService:
    """
    خدمة مستقلة مسؤولة عن كل عمليات استخلاص البيانات من موقع الجامعة.
    """
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': BASE_URL
        })
        selectors_path = Path(__file__).parent / 'selectors.json'
        try:
            with open(selectors_path, 'r', encoding='utf-8') as f:
                self.selectors = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"فشل حاسم: لا يمكن تحميل ملف المحددات 'selectors.json'. الخطأ: {e}")
            raise RuntimeError("Scraper cannot operate without selectors.") from e

    @cached(cache=TTLCache(maxsize=1, ttl=3600))
    def fetch_colleges_and_token(self):
        """
        تجلب قائمة الكليات ورمز التحقق.
        يتم تخزين النتائج مؤقتًا لمدة ساعة لتقليل الضغط على الخادم.
        """
        try:
            response = self.session.get(BASE_URL, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            
            token_input = soup.select_one(self.selectors['request_verification_token'])
            if not token_input or 'value' not in token_input.attrs:
                raise ValueError("لم يتم العثور على رمز التحقق (__RequestVerificationToken).")
            token = token_input["value"]
            
            college_select = soup.select_one(self.selectors['college_select_dropdown'])
            if not college_select:
                raise ValueError("لم يتم العثور على قائمة الكليات المنسدلة.")

            college_emojis = { "البشري": "👨‍⚕️", "الصيدلة": "💊", "الأسنان": "🦷", "الآداب": "📚", "المدنية": "🏗️", "المعمارية": "🏛️","الزراعي": "🧑‍🌾", "البيطري": "🐾", "العلوم": "🔬", "التربية": "🧑‍🏫", "الاقتصاد": "📈", "الرياضية": "🏁", "الميكانيك": "⚙️", "حاسوب": "🖥️"}
            
            colleges = []
            for opt in college_select.select(self.selectors['college_option']):
                value = opt.get("value")
                if not value: continue
                
                name = opt.text.strip()
                emoji = next((emoji for keyword, emoji in college_emojis.items() if keyword in name), "🎓")
                colleges.append({"name": f"{emoji} {name}", "id": value})

            return colleges, token
        
        except (requests.RequestException, ValueError, AttributeError) as e:
            logger.error(f"فشل جلب الكليات ورمز التحقق: {e}", exc_info=True)
            return None, None

    def fetch_full_student_data(self, college_id: str, university_id: str, token: str):
        """
        تجلب كامل بيانات الطالب ونتائجه من الموقع.
        """
        payload = {
            "UniversityId": university_id,
            "CollegeId": college_id,
            "__RequestVerificationToken": token,
            "Year": ""
        }
        try:
            response = self.session.post(RESULT_URL, data=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            if error_div := soup.select_one(self.selectors['validation_error_summary']):
                return {"success": False, "error": error_div.text.strip()}

            student_info = self._parse_student_info(soup)
            all_marks = self._parse_student_marks(soup)

            if not student_info and not all_marks:
                return {"success": False, "error": "الرقم الجامعي غير موجود أو لا توجد له نتائج في هذه الكلية."}

            # فرز النتائج دائما حسب التاريخ لضمان التناسق عند المقارنة
            sorted_marks = sorted(all_marks, key=lambda x: (x.get('date', ''), x.get('subject', '')))
            
            return {"success": True, "info": student_info, "marks": sorted_marks}

        except requests.RequestException as e:
            logger.error(f"فشل التحقق والجلب للرقم {university_id}: {e}", exc_info=True)
            return {"success": False, "error": "حدث خطأ أثناء الاتصال بالخادم. يرجى المحاولة لاحقًا."}

    def _parse_student_info(self, soup: BeautifulSoup) -> dict:
        """دالة مساعدة لتحليل معلومات الطالب الشخصية."""
        student_info = {}
        info_card = soup.select_one(self.selectors['student_info_card'])
        if not info_card: return student_info

        spans = info_card.select(f"{self.selectors['info_key_span']}, {self.selectors['info_value_span']}")
        i = 0
        while i < len(spans) - 1:
            key_span = spans[i]
            value_span = spans[i+1]
            if 'head' in key_span.get('class', []) and 'bottom' in value_span.get('class', []):
                key_text = key_span.text.strip()
                value_text = value_span.text.strip()
                if "الاسم" in key_text and "الأب" not in key_text: student_info['name'] = value_text
                elif "اسم الأب" in key_text: student_info['father_name'] = value_text
                elif "الكلية" in key_text: student_info['college_name'] = value_text
                i += 2
            else:
                i += 1
        return student_info

    def _parse_student_marks(self, soup: BeautifulSoup) -> list:
        """دالة مساعدة لتحليل جدول العلامات."""
        all_marks = []
        result_panels = soup.select(self.selectors['result_panels'])
        for panel in result_panels:
            heading_tag = panel.select_one(self.selectors['panel_heading'])
            heading = heading_tag.text.strip() if heading_tag else "فصل غير محدد"
            
            table = panel.select_one(self.selectors['results_table'])
            if table and (tbody := table.select_one(self.selectors['table_body'])):
                for row in tbody.select(self.selectors['table_row']):
                    cols = [td.text.strip() for td in row.select(self.selectors['table_cell'])]
                    if len(cols) >= 5:
                        all_marks.append({
                            "subject": cols[0], "session": cols[1], "mark": cols[2], 
                            "status": cols[3], "date": cols[4], "semester": heading
                        })
        return all_marks

    @staticmethod
    def find_new_marks(old_marks: list, new_marks: list) -> list:
        """
        تقارن بين قائمتي علامات وتُرجع فقط العلامات الجديدة.
        تعتمد على أن القائمتين مرتبتين.
        """
        # استخدام set لعملية مقارنة سريعة وفعالة
        old_marks_set = {json.dumps(mark, sort_keys=True) for mark in old_marks}
        new_marks_list = []
        for mark in new_marks:
            if json.dumps(mark, sort_keys=True) not in old_marks_set:
                new_marks_list.append(mark)
        return new_marks_list