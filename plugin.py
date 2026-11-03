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
from twisted.internet.threads import deferToThread

from .translator import EPGGoldEngine, write_epgimport_source

config.plugins.epggold = ConfigSubsection()
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
        <widget name="path" position="20,10" size="660,30" font="Regular;18" />
        <widget name="filelist" position="20,50" size="660,350" itemHeight="30" scrollbarMode="showOnDemand" />
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
    <screen name="EPGGoldScreen" position="center,center" size="700,420" title="EPG Gold">
        <widget name="config" position="20,20" size="660,170" itemHeight="40" font="Regular;20" />
        <widget name="status" position="20,210" size="660,110" font="Regular;18" halign="center" valign="center"/>
        <widget name="hint" position="20,350" size="660,50" font="Regular;18" halign="center" valign="center"/>
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.busy = False
        self.engine = None

        self.list = [
            getConfigListEntry("لغة الترجمة:", config.plugins.epggold.language),
            getConfigListEntry("ملف EPG الأصلي:", config.plugins.epggold.input_file),
            getConfigListEntry("إنشاء مصدر EPGImport:", config.plugins.epggold.make_source),
            getConfigListEntry("ملف القنوات (channels):", config.plugins.epggold.channels_file),
        ]
        ConfigListScreen.__init__(self, self.list, session=session)

        self["status"] = Label("جاهز.")
        self["hint"] = Label("الأصفر: اختيار ملف من القائمة   |   الأخضر: بدء الترجمة   |   الأحمر: خروج")
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
                "اختار سطر (ملف EPG الأصلي) أو (ملف القنوات) الأول، وبعدين اضغط الأصفر.",
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
        if self.engine:
            self.engine.stop = True
        self.timer.stop()
        self.close()

    def update_progress(self):
        e = self.engine
        if e and self.busy:
            self["status"].setText(
                "جاري الترجمة...\nبرامج تمت معالجتها: %d\nترجمات جديدة: %d | من الكاش: %d"
                % (e.programmes, e.translated, e.from_cache))

    def start_translation_process(self):
        if self.busy:
            return
        input_file = config.plugins.epggold.input_file.value
        if not os.path.isfile(input_file):
            self.session.open(MessageBox, "الملف غير موجود:\n%s\nاختاره بالزرار الأصفر." % input_file,
                              MessageBox.TYPE_ERROR)
            return
        for item in (config.plugins.epggold.language,
                     config.plugins.epggold.input_file,
                     config.plugins.epggold.make_source,
                     config.plugins.epggold.channels_file):
            item.save()
        self.busy = True
        lang = config.plugins.epggold.language.value
        self.engine = EPGGoldEngine(target_lang=lang)
        self["status"].setText("جاري البدء...")
        self.timer.start(1000, False)

        d = deferToThread(self.run_engine, self.engine, input_file)
        d.addCallback(self.on_done, lang)
        d.addErrback(self.on_error)

    # ---------- الخلفية (ممنوع لمس الواجهة هنا) ----------
    def run_engine(self, engine, input_file):
        return engine.process_file(input_file)

    # ---------- الرجوع للـ thread الرئيسي ----------
    def on_done(self, output_path, lang):
        self.busy = False
        self.timer.stop()
        msg = "تمت الترجمة بنجاح.\nالملف: %s" % output_path
        if config.plugins.epggold.make_source.value:
            try:
                src = write_epgimport_source(
                    output_path, config.plugins.epggold.channels_file.value, lang)
                msg += ("\n\nتم إنشاء مصدر EPGImport:\n%s\n"
                        "افتح EPGImport > Sources وفعّل (EPG Gold) ثم اعمل Import."
                        % src)
            except Exception as e:
                msg += "\n\nتعذر إنشاء مصدر EPGImport: %s" % e
        self["status"].setText("تم.")
        self.session.open(MessageBox, msg, MessageBox.TYPE_INFO)

    def on_error(self, failure):
        self.busy = False
        self.timer.stop()
        self["status"].setText("حدث خطأ.")
        self.session.open(MessageBox, "خطأ: %s" % failure.getErrorMessage(),
                          MessageBox.TYPE_ERROR)


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
