import xml.etree.ElementTree as ET
import sqlite3
import os
import gzip

class EPGGoldEngine:
    def __init__(self):
        self.db_path = "/etc/enigma2/epggold_cache.db"
        self.init_db()

    def init_db(self):
        # إنشاء قاعدة بيانات محلية لحفظ الكلمات المترجمة مسبقاً (Caching)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS translations (
                original TEXT PRIMARY KEY,
                translated TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def get_translation_from_cache(self, text):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT translated FROM translations WHERE original = ?", (text,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def save_to_cache(self, original, translated):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO translations (original, translated) VALUES (?, ?)", (original, translated))
        conn.commit()
        conn.close()

    def translate_text(self, text):
        if not text or not text.strip():
            return text

        # 1. فحص الكاش المحلي أولاً لتوفير الوقت
        cached = self.get_translation_from_cache(text)
        if cached:
            return cached

        # 2. لو مش موجودة في الكاش، بنترجمها (هنا بيتم ربطها بـ API أو قاموس)
        translated = text  # مؤقتاً لحين ربط الـ API
        
        # حفظها في الكاش للمرات القادمة
        self.save_to_cache(text, translated)
        return translated

    def process_file(self, file_path):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"الملف غير موجود: {file_path}")

        # قراءة الملف (سواء XML عادي أو مضغوط GZ)
        if file_path.endswith('.gz'):
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                tree = ET.parse(f)
        else:
            tree = ET.parse(file_path)

        root = tree.getroot()

        # التعديل على وسوم البرامج
        for programme in root.findall('programme'):
            title = programme.find('title')
            desc = programme.find('desc')

            if title is not None and title.text:
                title.text = self.translate_text(title.text)
            
            if desc is not None and desc.text:
                desc.text = self.translate_text(desc.text)

        # حفظ الملف الناتج
        output_path = file_path.replace('.xml', '_gold.xml')
        tree.write(output_path, encoding='utf-8', xml_declaration=True)
        return output_path
