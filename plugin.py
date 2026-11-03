# -*- coding: utf-8 -*-
import os
from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.FileList import FileList
from Components.ConfigList import ConfigListScreen
from Components.config import (config, ConfigSubsection, ConfigSelection,
                               ConfigText, ConfigYesNo, getConfigListEntry)
from enigma import eTimer
from twisted.internet import reactor
from twisted.internet.threads import deferToThread

from .translator import EPGGoldEngine, EPGDatExporter, write_epgimport_source

EPGIMPORT_DIR = "/etc/epgimport"
GEN_CHANNELS = EPGIMPORT_DIR + "/epggold.channels.xml"

config.plugins.epggold = ConfigSubsection()
config.plugins.epggold.source_mode = ConfigSelection(
    default="dat", choices=[("dat", "epg.dat (دليل الرسيفر مباشرة)"), ("xml", "ملف XMLTV")])
config.plugins.epggold.language = ConfigSelection(
    default="ar", choices=[("ar", "العربية"), ("en", "الإنجليزية")])
config.plugins.epggold.input_file = ConfigText(
    default="/media/hdd/epg.xml", fixed_size=False)
config.plugins.epggold.make_source = ConfigYesNo(default=True)
config.plugins.epggold.channels_file = ConfigText(
    default="/etc/epgimport/custom.channels.xml", fixed_size=False)


class EPGGoldFileBrowser(Screen):
    """شاشة اختيار ملف من الرسيفر."""
    skin = """
    <screen name="EPGGoldFileBrowser" position="center,center" size="700,460" title="EPG Gold - اختيار ملف">
        <widget name="path" position="20,10" size="660,35" font="Regular;20" valign="center" />
        <widget name="filelist" position="20,55" size="660,345" itemHeight="42" scrollbarMode="showOnDemand" />
        <widget name="hint" position="20,415" size="660,30" font="Regular;18" halign="center" />
    </screen>"""

    def __init__(self, session, start_dir, pattern):
        Screen.__init__(self, session)
        if not os.path.isdir(start_dir):
            start_dir = "/"
        self["filelist"] = FileList(start_dir, showDirectories=True,
                                    showFiles=True, matchingPattern=pattern)
        self["path"] = Label(start_dir)
        self["hint"] = Label("OK: اختيار / دخول مجلد   |   الأحمر: إلغاء")
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "ok": self.ok,
            "cancel": self.cancel,
            "red": self.cancel,
        }, -1)

    def ok(self):
        fl = self["filelist"]
        if fl.canDescent():
            fl.descent()
            self["path"].setText(fl.getCurrentDirectory() or "/")
        else:
            self.close(fl.getFilename())

    def cancel(self):
        self.close(None)


class EPGGoldScreen(Screen, ConfigListScreen):
    skin = """
    <screen name="EPGGoldScreen" position="center,center" size="700,440" title="EPG Gold">
        <widget name="config" position="20,20" size="660,210" itemHeight="40" font="Regular;20" />
        <widget name="status" position="20,240" size="660,110" font="Regular;18" halign="center" valign="center"/>
        <widget name="hint" position="20,375" size="660,50" font="Regular;18" halign="center" valign="center"/>
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.busy = False
        self.closed = False
        self.engine = None
        self.exporter = None
        self.temp_input = None

        self.list = [
            getConfigListEntry("مصدر الدليل:", config.plugins.epggold.source_mode),
            getConfigListEntry("لغة الترجمة:", config.plugins.epggold.language),
            getConfigListEntry("ملف XMLTV (لوضع XMLTV فقط):", config.plugins.epggold.input_file),
            getConfigListEntry("إنشاء مصدر EPGImport:", config.plugins.epggold.make_source),
            getConfigListEntry("ملف القنوات (لوضع XMLTV فقط):", config.plugins.epggold.channels_file),
        ]
        ConfigListScreen.__init__(self, self.list, session=session)

        self["status"] = Label("جاهز.")
        self["hint"] = Label("الأصفر: اختيار ملف   |   الأخضر: بدء الترجمة   |   الأحمر: خروج")
        self["actions"] = ActionMap(["ColorActions", "SetupActions"], {
            "green": self.start_translation_process,
            "yellow": self.browse,
            "red": self.exit_screen,
            "cancel": self.exit_screen,
        }, -2)

        self.timer = eTimer()
        try:
            self.timer.callback.append(self.update_progress)
        except AttributeError:
            self.timer_conn = self.timer.timeout.connect(self.update_progress)

    # ---------- اختيار الملفات ----------
    def browse(self):
        if self.busy:
            return
        current = self["config"].getCurrent()
        element = current[1] if current else None
        if element is config.plugins.epggold.input_file:
            pattern = r"(?i)^.*\.(xml|gz)$"
        elif element is config.plugins.epggold.channels_file:
            pattern = r"(?i)^.*\.xml$"
        else:
            self.session.open(
                MessageBox,
                "اختار سطر (ملف XMLTV) أو (ملف القنوات) الأول، وبعدين اضغط الأصفر.",
                MessageBox.TYPE_INFO, timeout=5)
            return
        start = os.path.dirname(element.value) if element.value else "/media/hdd"
        if not os.path.isdir(start):
            start = "/media/hdd" if os.path.isdir("/media/hdd") else "/"
        self.session.openWithCallback(
            lambda path, el=element: self.file_selected(el, path),
            EPGGoldFileBrowser, start, pattern)

    def file_selected(self, element, path):
        if not path:
            return
        element.value = path
        try:
            self["config"].invalidateCurrent()
        except Exception:
            self["config"].l.invalidate()

    # ---------- الواجهة ----------
    def exit_screen(self):
        self.closed = True
        if self.engine:
            self.engine.stop = True
        if self.exporter:
            self.exporter.abort()
        self.timer.stop()
        self.close()

    def update_progress(self):
        e = self.engine
        if e and self.busy:
            self["status"].setText(
                "جاري الترجمة...\nبرامج تمت معالجتها: %d\nترجمات جديدة: %d | من الكاش: %d"
                % (e.programmes, e.translated, e.from_cache))

    def fail(self, msg):
        self.busy = False
        self.timer.stop()
        if self.closed:
            return
        self["status"].setText("حدث خطأ.")
        self.session.open(MessageBox, msg, MessageBox.TYPE_ERROR)

    # ---------- البداية ----------
    def start_translation_process(self):
        if self.busy:
            return
        for item in (config.plugins.epggold.source_mode,
                     config.plugins.epggold.language,
                     config.plugins.epggold.input_file,
                     config.plugins.epggold.make_source,
                     config.plugins.epggold.channels_file):
            item.save()

        if config.plugins.epggold.source_mode.value == "dat":
            self.start_export()
        else:
            input_file = config.plugins.epggold.input_file.value
            if not os.path.isfile(input_file):
                self.session.open(
                    MessageBox,
                    "الملف غير موجود:\n%s\nاختاره بالزرار الأصفر أو غيّر المصدر إلى epg.dat." % input_file,
                    MessageBox.TYPE_ERROR)
                return
            self.busy = True
            self.begin_translation(input_file, config.plugins.epggold.channels_file.value)

    # ---------- وضع epg.dat: قراءة الدليل من الرسيفر على دفعات ----------
    def start_export(self):
        self.busy = True
        base = "/media/hdd" if os.path.isdir("/media/hdd") else "/tmp"
        export_path = os.path.join(base, "epggold_export.xml")
        try:
            if not os.path.isdir(EPGIMPORT_DIR):
                os.makedirs(EPGIMPORT_DIR)
            self.exporter = EPGDatExporter(export_path, GEN_CHANNELS)
            self.exporter.start()
        except Exception as e:
            self.fail("تعذر قراءة الدليل: %s" % e)
            return
        self["status"].setText("جاري قراءة الدليل من الرسيفر...")
        reactor.callLater(0.05, self.export_step)

    def export_step(self):
        ex = self.exporter
        if self.closed or not self.busy:
            if ex:
                ex.abort()
            return
        try:
            done = ex.step()
        except Exception as e:
            ex.abort()
            self.fail("خطأ أثناء قراءة الدليل: %s" % e)
            return
        self["status"].setText("جاري قراءة الدليل من الرسيفر...\nالقنوات: %d / %d\nالبرامج: %d"
                               % (ex.idx, ex.total, ex.events))
        if not done:
            reactor.callLater(0.02, self.export_step)
            return
        try:
            ex.finish()
        except Exception as e:
            ex.abort()
            self.fail("تعذر حفظ الدليل: %s" % e)
            return
        if ex.events == 0:
            self.fail("الدليل فاضي في الرسيفر.\nتأكد إن الـ EPG اتحمّل (مثلاً اعمل EPGImport أو انتظر شوية).")
            return
        self.temp_input = ex.export_path
        self.begin_translation(ex.export_path, ex.channels_path)

    # ---------- الترجمة في الخلفية ----------
    def begin_translation(self, input_file, channels_file):
        lang = config.plugins.epggold.language.value
        self.engine = EPGGoldEngine(target_lang=lang)
        self["status"].setText("جاري البدء...")
        self.timer.start(1000, False)
        d = deferToThread(self.run_engine, self.engine, input_file)
        d.addCallback(self.on_done, lang, channels_file)
        d.addErrback(self.on_error)

    def run_engine(self, engine, input_file):  # ممنوع لمس الواجهة هنا
        return engine.process_file(input_file)

    # ---------- الرجوع للـ thread الرئيسي ----------
    def on_done(self, output_path, lang, channels_file):
        self.busy = False
        self.timer.stop()
        if self.temp_input and os.path.exists(self.temp_input):
            try:
                os.remove(self.temp_input)  # ملف التصدير المؤقت (غير المترجم)
            except Exception:
                pass
        self.temp_input = None
        e = self.engine
        msg = "انتهت المعالجة.\nالملف: %s" % output_path
        if e:
            msg += ("\n\nالملخص:\nبرامج: %d\nترجمات جديدة: %d | من الكاش: %d | متخطاة (بلغة الهدف): %d"
                    % (e.programmes, e.translated, e.from_cache, e.skipped))
            if e.sample:
                msg += "\nمثال: %s  ->  %s" % e.sample
            if e.translated == 0 and e.from_cache == 0:
                msg += "\n\nتنبيه: لم تتم أي ترجمة فعلية! راجع الإنترنت و /tmp/epggold.log"
        if config.plugins.epggold.make_source.value:
            try:
                src = write_epgimport_source(output_path, channels_file, lang)
                msg += ("\n\nتم إنشاء مصدر EPGImport:\n%s\n"
                        "افتح EPGImport > Sources وفعّل (EPG Gold) ثم اعمل Import." % src)
            except Exception as e:
                msg += "\n\nتعذر إنشاء مصدر EPGImport: %s" % e
        if not self.closed:
            self["status"].setText("تم.")
            self.session.open(MessageBox, msg, MessageBox.TYPE_INFO)

    def on_error(self, failure):
        self.fail("خطأ: %s" % failure.getErrorMessage())


def main(session, **kwargs):
    session.open(EPGGoldScreen)


def Plugins(**kwargs):
    return [
        PluginDescriptor(
            name="EPG Gold",
            description="ترجمة دليل البرامج EPG بذكاء وفي الخلفية",
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon="plugin.png",
            fnc=main
        )
    ]
