#!/bin/sh
# EPG Gold - تثبيت/تحديث مباشر من GitHub
# التثبيت أو التحديث:  sh install.sh
# الحذف:               sh install.sh remove
#
# أمر واحد من الرسيفر:
# wget -q --no-check-certificate -O - https://raw.githubusercontent.com/anow2008/EPG-Gold/main/install.sh | sh

REPO="anow2008/EPG-Gold"
BRANCH="main"
RAW="https://raw.githubusercontent.com/$REPO/$BRANCH"
NAME="EPGGold"
DEST="/usr/lib/enigma2/python/Plugins/Extensions/$NAME"
TMP="/tmp/${NAME}_install"
FILES_REQUIRED="plugin.py translator.py __init__.py"
FILES_OPTIONAL="plugin.png"

restart_gui() {
    echo ">> إعادة تشغيل الواجهة..."
    sync
    if command -v systemctl >/dev/null 2>&1; then
        systemctl restart enigma2
    else
        killall -9 enigma2
    fi
}

download() {  # $1 = اسم الملف
    url="$RAW/$1"
    out="$TMP/$1"
    if command -v wget >/dev/null 2>&1; then
        wget -q -O "$out" "$url" 2>/dev/null || wget -q --no-check-certificate -O "$out" "$url" 2>/dev/null
    elif command -v curl >/dev/null 2>&1; then
        curl -s -f -L -o "$out" "$url" || curl -s -f -k -L -o "$out" "$url"
    else
        echo "لا يوجد wget ولا curl"; return 1
    fi
    [ -s "$out" ]
}

if [ "$1" = "remove" ]; then
    echo ">> حذف $NAME ..."
    rm -rf "$DEST"
    rm -f /etc/epgimport/epggold.sources.xml
    echo "تم الحذف (ملف الكاش epggold_cache.db ما اتمسحش)"
    restart_gui
    exit 0
fi

echo "=== تثبيت EPG Gold من GitHub ($REPO) ==="

if ! command -v python3 >/dev/null 2>&1; then
    echo "خطأ: python3 غير موجود. البلجن يعمل على صور بايثون 3 فقط."
    exit 1
fi

rm -rf "$TMP"; mkdir -p "$TMP"

# تحميل الملفات المطلوبة
for f in $FILES_REQUIRED; do
    printf ">> تحميل %s ... " "$f"
    if download "$f"; then
        echo "تم"
    else
        echo "فشل"
        echo "خطأ: تعذر تحميل $f. تأكد من الإنترنت ومن وجود الملف في الريبو."
        rm -rf "$TMP"; exit 1
    fi
done

for f in $FILES_OPTIONAL; do
    printf ">> تحميل %s ... " "$f"
    if download "$f"; then echo "تم"; else echo "تخطي"; rm -f "$TMP/$f"; fi
done

# التأكد إن ملفات بايثون سليمة (مش صفحة خطأ HTML)
for f in plugin.py translator.py; do
    if ! python3 -m py_compile "$TMP/$f" 2>/dev/null; then
        echo "خطأ: الملف $f غير صالح (فيه خطأ صياغة أو التحميل ناقص)."
        rm -rf "$TMP"; exit 1
    fi
done
rm -rf "$TMP/__pycache__"

# النسخ
rm -rf "$DEST"
mkdir -p "$DEST"
cp "$TMP"/* "$DEST"/
chmod -R 755 "$DEST"
rm -rf "$TMP"

if [ ! -d /usr/lib/enigma2/python/Plugins/Extensions/EPGImport ]; then
    echo "تنبيه: EPGImport غير مثبت. الترجمة ستعمل لكن لن تستطيع استيراد الملف للدليل."
fi

echo "=== تم التثبيت في: $DEST ==="
restart_gui
