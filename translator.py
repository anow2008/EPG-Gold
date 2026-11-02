import xml.etree.ElementTree as ET
import sqlite3
import os
import gzip
import urllib.request
import urllib.parse
import json

class EPGGoldEngine:
    def __init__(self, target_lang="ar"):
        self.db_path = "/etc/enigma2/epggold_cache.db"
        self.target_lang = target_lang # لغة الهدف (ar أو en)
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS translations (
                original TEXT,
                lang TEXT,
                translated TEXT,
                PRIMARY KEY (original, lang)
            )
        ''')
        conn.commit()
        conn.close()

    def get_translation_from_cache(self, text):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT translated FROM translations WHERE original = ? AND lang = ?", (text, self.target_lang))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def save_to_cache(self, original, translated):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO translations (original, lang, translated) VALUES (?, ?, ?)", 
                       (original, self.target_lang, translated))
        conn.commit()
        conn.close()

    def translate_text(self, text):
        if not text or not text.strip():
            return text

        # 1. البحث في الكاش المحلي أولاً لتوفير الوقت والإنترنت
        cached = self.get_translation_from_cache(text)
        if cached:
            return cached

        # 2. الترجمة عبر محرك جوجل (اكتشاف تلقائي للغة المصدر -> للغة المستهدفة)
        try:
            base_url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={self.target_lang}&dt=t&q="
            encoded_text = urllib.parse.quote(text)
            url = base_url + encoded_text

            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                result = json.loads(response.read().decode('utf-8'))
                translated = "".join([item[0] for item in result[0] if item[0]])
        except Exception:
            # في حال عدم وجود انترنت أو حدوث خطأ، يرجع النص الأصلي بدون تهنيج
            translated = text

        # 3. حفظ الترجمة الجديدة في الكاش
        self.save_to_cache(text, translated)
        return translated

    def process_file(self, file_path):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"الملف غير موجود: {file_path}")

        # قراءة الملف (سواء كان XML عادي أو مضغوط GZ)
        if file_path.endswith('.gz'):
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                tree = ET.parse(f)
        else:
            tree = ET.parse(file_path)

        root = tree.getroot()

        # معالجة وسوم البرامج (العنوان والوصف)
        for programme in root.findall('programme'):
            title = programme.find('title')
            desc = programme.find('desc')

            if title is not None and title.text:
                title.text = self.translate_text(title.text)
            
            if desc is not None and desc.text:
                desc.text = self.translate_text(desc.text)

        # حفظ الملف الناتج بنسخة جديدة مع تحديد لغة الترجمة في الاسم
        output_path = file_path.replace('.xml', f'_gold_{self.target_lang}.xml')
        tree.write(output_path, encoding='utf-8', xml_declaration=True)
        return output_path
