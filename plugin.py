from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ConfigList import ConfigListScreen
from Components.config import config, ConfigSubsection, ConfigSelection, getConfigListEntry
import threading
from .translator import EPGGoldEngine

# إعدادات البلجن لحفظ اللغة المختارة
config.plugins.epggold = ConfigSubsection()
config.plugins.epggold.language = ConfigSelection(default="ar", choices=[("ar", "العربية"), ("en", "الإنجليزية")])

class EPGGoldScreen(Screen, ConfigListScreen):
    skin = """
    <screen name="EPGGoldScreen" position="center,center" size="620,320" title="EPG Gold - الترجمة الذكية للدليل">
        <widget name="config" position="20,30" size="580,120" itemHeight="40" font="Regular;20" />
        <widget name="status" position="20,170" size="580,80" font="Regular;18" halign="center" valign="center"/>
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        
        self.list = []
        self.list.append(getConfigListEntry("لغة الترجمة المستهدفة:", config.plugins.epggold.language))
        
        ConfigListScreen.__init__(self, self.list)
        
        self["status"] = Label("اضغط OK لبدء الترجمة في الخلفية أو Exit للخروج")
        
        self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
            "ok": self.start_translation_process,
            "cancel": self.close,
            "red": self.close
        }, -2)

    def start_translation_process(self):
        selected_lang = config.plugins.epggold.language.value
        lang_name = "العربية" if selected_lang == "ar" else "الإنجليزية"
        
        self["status"].setText(f"جاري ترجمة دليل البرامج إلى {lang_name}...\nبرجاء الانتظار وعدم إغلاق الرسيفر.")
        
        # تشغيل المحرك في الخلفية لمنع تهنيج واجهة Enigma2
        threading.Thread(target=self.run_engine, args=(selected_lang, lang_name,)).start()

    def run_engine(self, lang, lang_name):
        try:
            engine = EPGGoldEngine(target_lang=lang)
            # مسار ملف الـ EPG الافتراضي (يمكنك تغييره حسب مسار ملفك)
            target_file = "/media/hdd/epg.xml" 
            engine.process_file(target_file)
            
            self.session.open(MessageBox, f"تمت ترجمة ملف الـ EPG إلى {lang_name} وحفظه بنجاح!", MessageBox.TYPE_INFO)
            self.close()
        except Exception as e:
            self.session.open(MessageBox, f"حدث خطأ أثناء الترجمة: {str(e)}", MessageBox.TYPE_ERROR)

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
