import urllib.request
import urllib.parse
import json

def translate_text(self, text):
    if not text or not text.strip():
        return text

    # 1. فحص الكاش المحلي أولاً (توفيراً للوقت والإنترنت)
    cached = self.get_translation_from_cache(text)
    if cached:
        return cached

    # 2. الترجمة عبر محرك مجاني (Google Translate Web API خفيف)
    try:
        # تجهيز رابط الترجمة (من الإنجليزية إلى العربية كمثال)
        base_url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ar&dt=t&q="
        encoded_text = urllib.parse.quote(text)
        url = base_url + encoded_text

        # إرسال الطلب
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode('utf-8'))
            # تجميع أجزاء الترجمة المرتجعة
            translated = "".join([item[0] for item in result[0] if item[0]])
            
    except Exception as e:
        # لو حصلت مشكلة في النت، يرجع النص الأصلي زي ما هو عشان البلجن مايهنجش
        translated = text

    # 3. حفظ النتيجة في الكاش للمرات القادمة
    self.save_to_cache(text, translated)
    return translated
