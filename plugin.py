from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ConfigList import ConfigListScreen
from components.config import config, ConfigSubsection, ConfigSelection, getConfigListEntry
import threading
from .translator import EPGGoldEngine

# إعدادات البلجن لحفظ اللغة المختارة
config.plugins.epggold = ConfigSubsection()
config.plugins.epggold.language = ConfigSelection(default="ar", choices=[("ar", "العربية"), ("en", "الإنجليزية")])

class EPGGoldScreen(Screen):
    skin = """
    <screen name="EPGGoldScreen" position="center,center" size="620,320" title="EPG Gold - إعدادات الترجمة">
        <widget name="config" position="20,30" size="580,120" itemHeight="40" font="Regular;20" />
        <widget name="status" position="20,170" size="580,80" font="Regular;18" halign="center" valign="center"/>
    </screen>"""

    def __init__(self, session):
        super().__init__(session)
        self.session = session
        
        self.list = []
        self.list.append(getConfigListEntry("لغة الترجمة المستهدفة:", config.plugins.epggold.language))
        
        self["config"] = ConfigListScreen(self.list)
        self["status"] = Label("اضغط OK لبدء الترجمة أو الزر الأحمر للخروج")
        
        self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
            "ok": self.start_translation_process,
            "cancel": self.close,
            "red": self.close
        }, -2)

    def start_translation_process(self):
        selected_lang = config.plugins.epggold.language.value
        lang_name = "العربية" if selected_lang == "ar" else "الإنجليزية"
        
        self["status"].setText(f"جاري ترجمة ودليل البرامج إلى {lang_name} في الخلفية...")
        
        # تشغيل المحرك باللغة المختارة في Background Thread
        threading.Thread(target=self.run_engine, args=(selected_lang,)).start()

    def run_engine(self, lang):
        try:
            engine = EPGGoldEngine(target_lang=lang)
            target_file = "/media/hdd/epg.xml" # مسار ملف الـ EPG الافتراضي
            engine.process_file(target_file)
            
            self.session.open(MessageBox, f"تمت ترجمة ملف الـ EPG إلى {lang} بنجاح!", MessageBox.TYPE_INFO)
            self.close()
        except Exception as e:
            self.session.open(MessageBox, f"حدث خطأ: {str(e)}", MessageBox.TYPE_ERROR)

def main(session, **kwargs):
    session.open(EPGGoldScreen)

def Plugins(**kwargs):
    return [
        PluginDescriptor(
            name="EPG Gold",
            description="ترجمة دليل البرامج EPG لأي لغة بذكاء",
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon="plugin.png",
            fnc=main
        )
    ]
