#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import tempfile
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
import requests
import ssl
import urllib3

# تجاوز SSL عالمياً عند التفعيل (لدعم جميع المكتبات)
if os.getenv('SKIP_SSL_VERIFY', 'false').lower() == 'true':
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    ssl._create_default_https_context = ssl._create_unverified_context

def sanitize_filename(filename):
    """تنقية اسم الملف مع الحفاظ على النقاط المهمة"""
    return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip().rstrip('.')

async def validate_and_download_file(url, save_dir, base_name, is_image=False):
    """تنزيل الملف مع معالجة ذكية للـ SSL والامتدادات"""
    url = url.strip()  # ← تنقية الرابط من المسافات (السبب الرئيسي للخطأ!)
    
    if not url:
        raise Exception("رابط فارغ بعد التنقية!")
    
    try:
        # تحديد إعدادات SSL
        skip_ssl = os.getenv('SKIP_SSL_VERIFY', 'false').lower() == 'true'
        verify_ssl = not skip_ssl
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        # إضافة توكن جيتهاب للمصادر الخاصة
        if 'github.com' in url and os.getenv('REPO_TOKEN'):
            headers['Authorization'] = f'token {os.getenv("REPO_TOKEN")}'
        
        print(f"⬇️  جاري تنزيل: {url[:60]}...")
        print(f"   وضع SSL: {'معطل (تم التجاوز)' if skip_ssl else 'مفعل'}")
        
        # تنزيل بتتابع مع معالجة الأخطاء
        response = requests.get(
            url, 
            stream=True, 
            verify=verify_ssl,  # ← التحكم الفعلي في التحقق من SSL
            headers=headers, 
            timeout=900  # 15 دقيقة للملفات الكبيرة
        )
        response.raise_for_status()
        
        # تحديد الامتداد
        if is_image:
            ext = os.path.splitext(urlparse(url).path)[1].lower()
            if not ext or len(ext) > 5 or ext in ['.php', '.asp']:
                content_type = response.headers.get('content-type', '')
                ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or '.jpg'
            filepath = Path(save_dir) / f"Logo{ext}"
        else:
            base_name = sanitize_filename(base_name)
            if base_name.lower().endswith('.mp4'):
                base_name = base_name[:-4]
            filepath = Path(save_dir) / f"{base_name}.mp4"
        
        # كتابة الملف
        total_size = 0
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)
        
        if total_size == 0:
            raise Exception("الملف فارغ بعد التنزيل")
        
        print(f"✅ تم التنزيل: {filepath.name} ({total_size / 1024 / 1024:.2f} MB)")
        return str(filepath)
    
    except requests.exceptions.SSLError as e:
        raise Exception(
            f"فشل التحقق من SSL للموقع {url[:50]}...\n"
            f"الحل: شغّل الـ Workflow مع تفعيل 'skip_ssl = true'\n"
            f"التفاصيل: {str(e)}"
        )
    except Exception as e:
        raise Exception(f"فشل تنزيل {url[:50]}...: {str(e)}")

async def resolve_channel(client, channel_input):
    """معالجة جميع أنواع معرفات القنوات (يدعم روابط الدعوة + والـ @)"""
    channel_input = channel_input.strip()
    
    # معالجة روابط الدعوة (مثل +Abc123)
    if channel_input.startswith('+') or ('t.me/+' in channel_input) or ('telegram.me/+' in channel_input):
        try:
            hash_part = channel_input.split('+')[-1].split('?')[0].split('&')[0].strip('/')
            print(f"🔗 محاولة الانضمام عبر رابط الدعوة (الكود: {hash_part})...")
            result = await client(ImportChatInviteRequest(hash_part))
            chat = result.chats[0] if result.chats else None
            if not chat:
                raise Exception("فشل استخراج معلومات القناة")
            print(f"✅ تم الانضمام للقناة: {getattr(chat, 'title', 'غير معروف')}")
            return chat
        except Exception as e:
            raise Exception(
                f"فشل معالجة رابط الدعوة '{channel_input}': {str(e)}\n"
                "تأكد من:\n"
                "  1. أن الحساب منضم للقناة مسبقاً\n"
                "  2. أن رابط الدعوة صالح وغير منتهي الصلاحية"
            )
    
    # معالجة المعرفات العادية (@channel) أو الأرقام
    try:
        entity = await client.get_entity(channel_input)
        print(f"✅ تم العثور على القناة: {getattr(entity, 'title', channel_input)}")
        return entity
    except Exception as e:
        raise Exception(
            f"فشل العثور على القناة '{channel_input}': {str(e)}\n"
            "استخدم معرف صحيح مثل:\n"
            "  - @yourchannel  ← للقنوات العامة\n"
            "  - +Abc123        ← لكود دعوة القناة الخاصة"
        )

async def main():
    print("="*70)
    print("🚀 سكريبت رفع المحتوى على تيليجرام - الإصدار النهائي")
    print("="*70)
    
    # التحقق من المتغيرات الأساسية
    required = ['MODE', 'CHANNEL', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION_STRING']
    missing = [v for v in required if not os.getenv(v, '').strip()]
    if missing:
        raise Exception(f"❌ المتغيرات الناقصة: {', '.join(missing)}")
    
    mode = os.getenv('MODE', '').strip().lower()
    channel = os.getenv('CHANNEL', '').strip()
    caption = os.getenv('CAPTION', '').replace('\\n', '\n').strip()
    
    if mode not in ['movie', 'series']:
        raise Exception("❌ الوضع غير مدعوم! اختر 'movie' أو 'series'")
    
    if not channel:
        raise Exception("❌ حقل القناة فارغ! أدخل معرف القناة الصحيح")
    
    # إعداد العميل
    try:
        client = TelegramClient(
            StringSession(os.getenv('TELEGRAM_SESSION_STRING')),
            int(os.getenv('TELEGRAM_API_ID')),
            os.getenv('TELEGRAM_API_HASH')
        )
        await client.start()
        print("✅ تم تسجيل الدخول بنجاح (حساب شخصي)")
    except Exception as e:
        raise Exception(f"❌ فشل تسجيل الدخول: {str(e)}")
    
    # معالجة الملفات
    with tempfile.TemporaryDirectory() as tmp_dir:
        media = []
        try:
            if mode == 'movie':
                img_url = os.getenv('IMAGE_URL', '').strip()
                vid_url = os.getenv('VIDEO_URL', '').strip()
                vid_name = os.getenv('VIDEO_NAME', 'movie').strip() or 'movie'
                
                if not img_url or not vid_url:
                    raise Exception("❌ في وضع الأفلام: مطلوب رابط الصورة ورابط الفيديو")
                
                media.append(await validate_and_download_file(img_url, tmp_dir, 'Logo', is_image=True))
                media.append(await validate_and_download_file(vid_url, tmp_dir, vid_name, is_image=False))
                print(f"\n🎬 جاهز للرفع: صورة + فيديو ({Path(media[1]).name})")
            
            else:  # series
                try:
                    series = json.loads(os.getenv('SERIES_VIDEOS', '[]'))
                except Exception as e:
                    raise Exception(f"❌ خطأ في تنسيق JSON: {str(e)}")
                
                if not isinstance(series, list) or not series:
                    raise Exception("❌ مطلوب على الأقل ملف فيديو واحد")
                
                if len(series) > 10:
                    print(f"⚠️  سيتم رفع أول 10 ملفات فقط (تم اكتشاف {len(series)})")
                    series = series[:10]
                
                for i, item in enumerate(series, 1):
                    if not isinstance(item, dict) or 'url' not in item:
                        continue
                    url = item['url'].strip()
                    name = item.get('name', f'Episode_{i}').strip() or f'Episode_{i}'
                    if url:
                        media.append(await validate_and_download_file(url, tmp_dir, name, is_image=False))
                        print(f"📺 تمت إضافة: {Path(media[-1]).name}")
                
                print(f"\n📼 جاهز للرفع: {len(media)} ملفات")
            
            # الرفع
            print(f"\n📤 جاري الرفع على القناة: {channel}")
            print(f"📝 الكابشن: {caption[:60] + '...' if len(caption) > 60 else caption}")
            
            entity = await resolve_channel(client, channel)
            
            await client.send_file(
                entity,
                media,
                caption=caption,
                supports_streaming=True,
                force_document=False,
                parse_mode='html'
            )
            
            print("\n" + "="*70)
            print("✅ تم الرفع بنجاح!")
            print("="*70)
            print(f"📊 ملخص العملية:")
            print(f"   - الوضع: {'فيلم' if mode == 'movie' else 'مسلسل'}")
            print(f"   - الملفات: {len(media)}")
            print(f"   - القناة: {getattr(entity, 'title', channel)}")
            print("="*70)
        
        finally:
            for f in media:
                try:
                    Path(f).unlink(missing_ok=True)
                except:
                    pass
            await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  تم الإلغاء يدوياً", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ خطأ فادح: {str(e)}", file=sys.stderr)
        print("\n💡 اقتراحات الحل:")
        if "SSL" in str(e) or "certificate verify failed" in str(e):
            print("   1. شغّل الـ Workflow مع تفعيل 'skip_ssl = true'")
            print("   2. تأكد من عدم وجود مسافات زائدة في روابط الملفات")
        if "channel" in str(e).lower() or "invite" in str(e).lower():
            print("   1. تأكد أن الحساب منضم للقناة مسبقاً")
            print("   2. استخدم كود الدعوة بدون https:// (مثل: +Abc123)")
        sys.exit(1)
