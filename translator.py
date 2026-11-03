# -*- coding: utf-8 -*-
import os
import gzip
import json
import time
import sqlite3
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr, escape

LOG_FILE = "/tmp/epggold.log"


def log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def default_db_path():
    # الهارد أفضل من الفلاش لتقليل الكتابة على الذاكرة الداخلية
    if os.path.isdir("/media/hdd"):
        return "/media/hdd/epggold_cache.db"
    return "/etc/enigma2/epggold_cache.db"


def write_epgimport_source(output_path, channels_path, lang):
    """يكتب ملف مصدر لـ EPGImport يشير للملف المترجم."""
    src_dir = "/etc/epgimport"
    if not os.path.isdir(src_dir):
        os.makedirs(src_dir)
    src_file = os.path.join(src_dir, "epggold.sources.xml")
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<sources>\n'
        '  <sourcecat sourcecatname="EPG Gold">\n'
        '    <source type="gen_xmltv" channels=%s>\n'
        '      <description>EPG Gold (%s)</description>\n'
        '      <url>%s</url>\n'
        '    </source>\n'
        '  </sourcecat>\n'
        '</sources>\n'
    ) % (quoteattr(channels_path), escape(lang), escape("file://" + output_path))
    with open(src_file, "w", encoding="utf-8") as f:
        f.write(content)
    return src_file


class EPGGoldEngine:
    CHUNK = 1500          # أقصى طول للنص في الطلب الواحد
    MAX_FAILS = 5         # عدد الأخطاء المتتالية قبل إيقاف العملية
    COMMIT_EVERY = 50

    def __init__(self, target_lang="ar", db_path=None):
        self.target_lang = target_lang
        self.db_path = db_path or default_db_path()
        self.conn = None
        self.pending = 0
        self.stop = False
        self.fails = 0
        # عدّادات للعرض في الواجهة
        self.programmes = 0
        self.translated = 0
        self.from_cache = 0
        self.skipped = 0

    # ---------- الكاش ----------
    def _open_db(self):
        # لازم يتفتح في نفس الـ thread اللي بيستخدمه
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS translations ("
            "original TEXT, lang TEXT, translated TEXT, "
            "PRIMARY KEY (original, lang))")
        self.conn.commit()

    def _cache_get(self, text):
        row = self.conn.execute(
            "SELECT translated FROM translations WHERE original=? AND lang=?",
            (text, self.target_lang)).fetchone()
        return row[0] if row else None

    def _cache_put(self, original, translated):
        self.conn.execute(
            "INSERT OR REPLACE INTO translations VALUES (?,?,?)",
            (original, self.target_lang, translated))
        self.pending += 1
        if self.pending >= self.COMMIT_EVERY:
            self.conn.commit()
            self.pending = 0

    # ---------- الترجمة ----------
    def _already_target(self, text):
        letters = [c for c in text if c.isalpha()]
        if not letters:
            return True
        if self.target_lang == "ar":
            n = sum(1 for c in letters if "\u0600" <= c <= "\u06FF")
            return n / float(len(letters)) > 0.6
        n = sum(1 for c in letters if ord(c) < 128)
        return n / float(len(letters)) > 0.9

    def _split(self, text):
        parts = []
        while len(text) > self.CHUNK:
            cut = max(text.rfind("\n", 0, self.CHUNK), text.rfind(". ", 0, self.CHUNK))
            if cut < self.CHUNK // 2:
                cut = self.CHUNK
            else:
                cut += 1
            parts.append(text[:cut])
            text = text[cut:]
        if text:
            parts.append(text)
        return parts

    def _google(self, text):
        url = ("https://translate.googleapis.com/translate_a/single"
               "?client=gtx&sl=auto&tl=%s&dt=t&q=%s"
               % (self.target_lang, urllib.parse.quote(text)))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            result = json.loads(r.read().decode("utf-8"))
        return "".join(item[0] for item in result[0] if item[0])

    def translate_text(self, text):
        if not text or not text.strip():
            return text
        if self._already_target(text):
            self.skipped += 1
            return text
        cached = self._cache_get(text)
        if cached:
            self.from_cache += 1
            return cached
        try:
            translated = "".join(self._google(c) for c in self._split(text))
            self.fails = 0
            time.sleep(0.2)  # تخفيف الضغط على جوجل
        except Exception as e:
            self.fails += 1
            log("translate error: %r" % (e,))
            if self.fails >= self.MAX_FAILS:
                raise RuntimeError(
                    "فشلت الترجمة %d مرات متتالية. تأكد من الإنترنت (التفاصيل في %s)"
                    % (self.MAX_FAILS, LOG_FILE))
            return text  # فشل: نرجع الأصل ومنحفظوش في الكاش
        self._cache_put(text, translated)
        self.translated += 1
        return translated

    # ---------- معالجة الملف ----------
    def make_output_path(self, file_path):
        is_gz = file_path.endswith(".gz")
        base = file_path[:-3] if is_gz else file_path
        name, ext = os.path.splitext(base)
        out = "%s_gold_%s%s" % (name, self.target_lang, ext or ".xml")
        return out + ".gz" if is_gz else out

    def process_file(self, file_path):
        if not os.path.exists(file_path):
            raise FileNotFoundError("الملف غير موجود: %s" % file_path)

        output_path = self.make_output_path(file_path)
        tmp_path = output_path + ".tmp"
        in_open = gzip.open if file_path.endswith(".gz") else open
        out_open = gzip.open if output_path.endswith(".gz") else open

        self._open_db()
        ok = False
        try:
            with in_open(file_path, "rb") as fin, \
                    out_open(tmp_path, "wt", encoding="utf-8") as out:
                out.write("<?xml version='1.0' encoding='utf-8'?>\n")
                depth = 0
                root = None
                # قراءة متدفقة: الملف مش بيتحمّل كله في الرام
                for event, elem in ET.iterparse(fin, events=("start", "end")):
                    if event == "start":
                        depth += 1
                        if depth == 1:
                            root = elem
                            attrs = "".join(" %s=%s" % (k, quoteattr(v))
                                            for k, v in elem.attrib.items())
                            out.write("<%s%s>\n" % (elem.tag, attrs))
                        continue
                    if depth == 2:
                        if self.stop:
                            raise RuntimeError("تم إيقاف العملية")
                        if elem.tag == "programme":
                            self.programmes += 1
                            for tag in ("title", "desc", "sub-title"):
                                for el in elem.findall(tag):
                                    if el.text:
                                        el.text = self.translate_text(el.text)
                        out.write(ET.tostring(elem, encoding="unicode"))
                        root.clear()  # تفريغ الذاكرة
                    elif depth == 1:
                        out.write("</%s>\n" % elem.tag)
                    depth -= 1
            ok = True
        finally:
            try:
                self.conn.commit()
                self.conn.close()
            except Exception:
                pass
            if not ok and os.path.exists(tmp_path):
                os.remove(tmp_path)

        os.replace(tmp_path, output_path)
        return output_path


# =====================================================================
#  قراءة الدليل من الرسيفر مباشرة (بدل تحليل ملف epg.dat الثنائي)
# =====================================================================
import re

_BAD_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x86\x87]")


def clean_text(s):
    """يشيل رموز التحكم اللي بتبوظ XML ويحوّل رمز السطر الجديد بتاع DVB."""
    if not s:
        return ""
    return _BAD_CHARS.sub("", s.replace("\ue08a", "\n"))


def get_epg_services():
    """قائمة (service_ref, name) من كل الباقات بدون تكرار وبدون الفواصل."""
    from enigma import eServiceCenter, eServiceReference
    sc = eServiceCenter.getInstance()
    root = eServiceReference('1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.tv" ORDER BY bouquet')
    bouquets = sc.list(root)
    result, seen = [], set()
    if bouquets is None:
        return result
    for bref, _bname in bouquets.getContent("SN", True):
        slist = sc.list(eServiceReference(bref))
        if slist is None:
            continue
        for sref, name in slist.getContent("SN", True):
            parts = sref.split(":")
            # قنوات عادية فقط (تخطي الفواصل والمجلدات والـ IPTV)
            if len(parts) < 3 or parts[0] != "1" or parts[1] != "0":
                continue
            if sref in seen:
                continue
            seen.add(sref)
            result.append((sref, name))
    return result


class EPGDatExporter:
    """
    بيقرا الأحداث من كاش الـ EPG الشغال في الرسيفر (نفس بيانات epg.dat)
    ويكتبها كملف XMLTV + ملف channels جاهز لـ EPGImport.
    لازم يشتغل في الـ thread الرئيسي، على دفعات (step) عشان الواجهة متهنجش.
    """

    def __init__(self, export_path, channels_path):
        self.export_path = export_path
        self.channels_path = channels_path
        self.services = []
        self.idx = 0
        self.events = 0
        self.channels = []   # (id, service_ref)
        self.fh = None
        self.epg = None
        self.finished = False

    @property
    def total(self):
        return len(self.services)

    def start(self):
        from enigma import eEPGCache
        self.epg = eEPGCache.getInstance()
        self.services = get_epg_services()
        if not self.services:
            raise RuntimeError("لم يتم العثور على قنوات في الباقات")
        self.fh = open(self.export_path + ".tmp", "w", encoding="utf-8")
        self.fh.write("<?xml version='1.0' encoding='utf-8'?>\n"
                      "<tv generator-info-name=\"EPG Gold\">\n")

    def step(self, n=25):
        """يعالج n قناة. بيرجّع True لما يخلص كل القنوات."""
        end = min(self.idx + n, len(self.services))
        for sref, name in self.services[self.idx:end]:
            try:
                events = self.epg.lookupEvent(["IBDTSE", (sref, 0, -1, -1)]) or []
            except Exception as e:
                log("lookupEvent error %s: %r" % (sref, e))
                events = []
            rows = []
            for ev in events:
                try:
                    _eid, begin, dur, title, short, ext = ev
                except Exception:
                    continue
                if not begin or dur is None or not title:
                    continue
                rows.append((begin, dur, clean_text(title),
                             clean_text(ext) or clean_text(short)))
            if not rows:
                continue
            cid = sref.replace(":", "_").rstrip("_")
            self.channels.append((cid, sref))
            self.fh.write("<channel id=%s><display-name>%s</display-name></channel>\n"
                          % (quoteattr(cid), escape(clean_text(name))))
            for begin, dur, title, desc in rows:
                start = time.strftime("%Y%m%d%H%M%S +0000", time.gmtime(begin))
                stop = time.strftime("%Y%m%d%H%M%S +0000", time.gmtime(begin + dur))
                self.fh.write("<programme start=%s stop=%s channel=%s><title>%s</title>"
                              % (quoteattr(start), quoteattr(stop), quoteattr(cid), escape(title)))
                if desc:
                    self.fh.write("<desc>%s</desc>" % escape(desc))
                self.fh.write("</programme>\n")
                self.events += 1
        self.idx = end
        return self.idx >= len(self.services)

    def finish(self):
        self.fh.write("</tv>\n")
        self.fh.close()
        self.fh = None
        os.replace(self.export_path + ".tmp", self.export_path)
        with open(self.channels_path, "w", encoding="utf-8") as f:
            f.write("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<channels>\n")
            for cid, sref in self.channels:
                f.write("  <channel id=%s>%s</channel>\n" % (quoteattr(cid), escape(sref)))
            f.write("</channels>\n")
        self.finished = True

    def abort(self):
        if self.finished:
            return
        try:
            if self.fh:
                self.fh.close()
                self.fh = None
            if os.path.exists(self.export_path + ".tmp"):
                os.remove(self.export_path + ".tmp")
        except Exception:
            pass
