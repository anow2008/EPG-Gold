# -*- coding: utf-8 -*-
from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
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


class EPGGoldScreen(Screen, ConfigListScreen):
    skin = """
    <screen name="EPGGoldScreen" position="center,center" size="700,400" title="EPG Gold">
        <widget name="config" position="20,20" size="660,170" itemHeight="40" font="Regular;20" />
        <widget name="status" position="20,210" size="660,110" font="Regular;18" halign="center" valign="center"/>
        <widget name="hint" position="20,340" size="660,40" font="Regular;18" halign="center" valign="center"/>
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
        self["hint"] = Label("الأخضر: بدء الترجمة   |   الأحمر: خروج")
        self["actions"] = ActionMap(["ColorActions", "SetupActions"], {
            "green": self.start_translation_process,
            "red": self.exit_screen,
            "cancel": self.exit_screen,
        }, -2)

        self.timer = eTimer()
        try:
            self.timer.callback.append(self.update_progress)
        except AttributeError:
            self.timer_conn = self.timer.timeout.connect(self.update_progress)

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

        d = deferToThread(self.run_engine, self.engine,
                          config.plugins.epggold.input_file.value)
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
