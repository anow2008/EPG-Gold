from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
import threading
from .translator import EPGGoldEngine

class EPGGoldScreen(Screen):
    skin = """
    <screen name="EPGGoldScreen" position="center,center" size="600,300" title="EPG Gold - الترجمة الذكية">
        <widget name="status" position="20,30" size="560,100" font="Regular;20" halign="center" valign="center"/>
        <widget name="info" position="20,150" size="560,80" font="Regular;16" halign="center" />
    </screen>"""

    def __init__(self, session):
        super().__init__(session)
        self.session = session
        self["status"] = Label("جاهز للبدء في ترجمة دليل البرامج...")
        self["info"] = Label("اضغط OK لبدء معالجة وترجمة ملفات الـ EPG")
        
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.start_translation_process,
            "cancel": self.close
        }, -2)

    def start_translation_process(self):
        self["status"].setText("جاري العمل في الخلفية... برجاء الانتظار")
        # تشغيل المحرك في Background Thread لمنع تهنيج الرسيفر
        threading.Thread(target=self.run_engine).start()

    def run_engine(self):
        try:
            engine = EPGGoldEngine()
            # مسار ملف الـ XML افتراضياً (مثلاً الناتج من EPGImport)
            target_file = "/media/hdd/epg.xml" 
            engine.process_file(target_file)
            
            # تحديث الواجهة عند الانتهاء
            self.session.open(MessageBox, "تمت ترجمة ملف الـ EPG وحفظه بنجاح!", MessageBox.TYPE_INFO)
            self.close()
        except Exception as e:
            self.session.open(MessageBox, f"حدث خطأ: {str(e)}", MessageBox.TYPE_ERROR)

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
