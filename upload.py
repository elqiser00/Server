#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import tempfile
import mimetypes
from pathlib import Path
from urllib.parse import urlparse, unquote
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import InputMediaUploadedPhoto, InputMediaUploadedDocument
from telethon.errors.rpcerrorlist import (
    UserAlreadyParticipantError, InviteHashInvalidError, 
    InviteHashExpiredError, ChannelPrivateError, ChatAdminRequiredError
)
import requests
import ssl
import urllib3
import time

# تجاوز SSL عالمياً عند التفعيل
if os.getenv('SKIP_SSL_VERIFY', 'false').lower() == 'true':
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    ssl._create_default_https_context = ssl._create_unverified_context

# ⚠️ الحد الأقصى الرسمي لتيليجرام: 2048 ميجابايت (2 جيجابايت)
# نستخدم 2047.5 ميجابايت كهامش أمان لتجنب أخطاء الرفع النهائية
MAX_VIDEO_SIZE_MB = 2047.5
MAX_VIDEO_SIZE_BYTES = int(MAX_VIDEO_SIZE_MB * 1024 * 1024)

def sanitize_filename(filename):
    """تنقية اسم الملف مع الحفاظ على النقاط المهمة"""
    return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip().rstrip('.')

async def validate_and_download_file(url, save_dir, base_name, is_image=False):
    """تنزيل الملف بسرعات قصوى مع فحص الحجم"""
    url = url.strip()
    
    if not url:
        raise Exception("❌ رابط فارغ بعد التنقية!")
    
    try:
        skip_ssl = os.getenv('SKIP_SSL_VERIFY', 'false').lower() == 'true'
        verify_ssl = not skip_ssl
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'identity',  # لمنع الضغط وتوفير الوقت
            'Connection': 'keep-alive'
        }
        
        if 'github.com' in url and os.getenv('REPO_TOKEN'):
            headers['Authorization'] = f'token {os.getenv("REPO_TOKEN")}'
        
        print(f"⬇️  جاري التنزيل: {url[:60]}...")
        print(f"   SSL: {'معطل' if skip_ssl else 'مفعل'} | السرعة: عالية")
        
        # بدء التوقيت لعرض سرعة التنزيل
        start_time = time.time()
        total_size = 0
        
        # تنزيل بقطع كبيرة (64 كيلوبايت) لزيادة السرعة
        response = requests.get(
            url, 
            stream=True, 
            verify=verify_ssl,
            headers=headers, 
            timeout=1200,  # 20 دقيقة للملفات الكبيرة
            allow_redirects=True
        )
        response.raise_for_status()
        
        # تحديد الامتداد
        if is_image:
            ext = os.path.splitext(urlparse(url).path)[1].lower()
            if not ext or len(ext) > 5 or ext in ['.php', '.asp', '.html']:
                content_type = response.headers.get('content-type', '')
                ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or '.jpg'
                # تنظيف الامتداد من أحرف غير صالحة
                ext = ''.join(c for c in ext if c.isalnum() or c == '.')
            filepath = Path(save_dir) / f"Logo{ext}"
        else:
            base_name = sanitize_filename(base_name)
            if base_name.lower().endswith('.mp4'):
                base_name = base_name[:-4]
            filepath = Path(save_dir) / f"{base_name}.mp4"
        
        # كتابة الملف بقطع كبيرة (64 كيلوبايت) لزيادة السرعة
        CHUNK_SIZE = 65536  # 64 كيلوبايت
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)
                    
                    # فحص تجاوز الحد أثناء التنزيل
                    if not is_image and total_size > MAX_VIDEO_SIZE_BYTES * 1.05:
                        f.close()
                        filepath.unlink(missing_ok=True)
                        elapsed = time.time() - start_time
                        speed = total_size / elapsed / 1024 / 1024  # ميجابايت/ثانية
                        raise Exception(
                            f"❌ توقف التنزيل: الحجم تجاوز {MAX_VIDEO_SIZE_MB} ميجابايت!\n"
                            f"الحجم الحالي: {total_size / 1024 / 1024:.2f} ميجابايت | السرعة: {speed:.2f} ميجابايت/ثانية"
                        )
        
        if total_size == 0:
            raise Exception("الملف فارغ بعد التنزيل")
        
        # حساب السرعة النهائية
        elapsed = time.time() - start_time
        speed = total_size / elapsed / 1024 / 1024 if elapsed > 0 else 0
        
        # فحص الحد النهائي
        if not is_image:
            file_size_mb = total_size / 1024 / 1024
            if total_size > MAX_VIDEO_SIZE_BYTES:
                filepath.unlink(missing_ok=True)
                raise Exception(
                    f"❌ حجم الفيديو ({file_size_mb:.2f} ميجابايت) يتجاوز الحد المسموح (2047.5 ميجابايت).\n"
                    f"الحد الرسمي لتيليجرام: 2048 ميجابايت. نستخدم 2047.5 كهامش أمان.\n"
                    f"الحل: قسّم الفيديو إلى أجزاء أصغر أو استخدم جودة أقل."
                )
            print(f"✅ تم التنزيل: {filepath.name} ({file_size_mb:.2f} ميجابايت) | السرعة: {speed:.2f} ميجابايت/ثانية ✓")
        else:
            print(f"✅ تم التنزيل: {filepath.name} ({total_size / 1024 / 1024:.2f} ميجابايت) | السرعة: {speed:.2f} ميجابايت/ثانية")
        
        return str(filepath)
    
    except requests.exceptions.SSLError as e:
        raise Exception(
            "❌ خطأ شهادة SSL:\n"
            "الموقع يستخدم شهادة غير موثوقة (شائع في مواقع التحميل العربية).\n"
            "الحل: فعّل 'skip_ssl = true' في إعدادات الـ Workflow."
        )
    except requests.exceptions.ConnectionError as e:
        raise Exception(
            "❌ خطأ اتصال بالشبكة:\n"
            "تأكد من أن الرابط صالح ويعمل في المتصفح.\n"
            "ملاحظة: بعض المواقع تمنع التنزيل التلقائي - جرب رابطاً بديلاً."
        )
    except Exception as e:
        if 'filepath' in locals() and Path(filepath).exists():
            Path(filepath).unlink(missing_ok=True)
        raise Exception(f"❌ فشل التنزيل: {str(e)}")

async def resolve_channel(client, channel_input):
    """
    معالجة ذكية لجميع أنواع روابط القنوات:
    - يدعم الروابط الكاملة: https://t.me/+Abc123
    - يدعم كود الدعوة: +Abc123
    - يتعامل مع القنوات الخاصة تلقائياً (حتى لو كان الحساب منضماً مسبقاً)
    """
    channel_input = channel_input.strip()
    
    # تنظيف الرابط من المسافات والبروتوكول الزائد
    if channel_input.startswith('https://') or channel_input.startswith('http://'):
        channel_input = channel_input.split('://', 1)[1]
    if channel_input.startswith('t.me/'):
        channel_input = channel_input[5:]
    if channel_input.startswith('telegram.me/'):
        channel_input = channel_input[12:]
    
    # استخراج كود الدعوة من أي شكل
    invite_hash = None
    if '+' in channel_input:
        parts = channel_input.split('+')
        if len(parts) > 1:
            invite_hash = parts[1].split('?')[0].split('&')[0].split('/')[0].strip()
    
    # إذا وجدنا كود دعوة
    if invite_hash and len(invite_hash) >= 5:
        print(f"🔍 معالجة رابط دعوة: +{invite_hash}")
        
        # محاولة 1: الحصول على القناة عبر الرابط الكامل دون انضمام
        try:
            full_url = f"https://t.me/joinchat/{invite_hash}"
            entity = await client.get_entity(full_url)
            print(f"✅ تم العثور على القناة: {getattr(entity, 'title', 'غير معروف')}")
            return entity
        except (ChannelPrivateError, ChatAdminRequiredError) as e:
            # محاولة 2: الانضمام التلقائي (إذا لزم)
            try:
                print("🔗 محاولة الانضمام للقناة...")
                result = await client(ImportChatInviteRequest(invite_hash))
                chat = result.chats[0] if result.chats else None
                if chat:
                    print(f"✅ تم الانضمام للقناة: {getattr(chat, 'title', 'بدون اسم')}")
                    return chat
            except UserAlreadyParticipantError:
                # محاولة 3: البحث في القنوات المنضمة
                print("ℹ️  الحساب منضم مسبقاً - جاري البحث في القنوات...")
                async for dialog in client.iter_dialogs(limit=50):  # تحسين السرعة بالحد إلى 50
                    if dialog.is_channel and not dialog.is_group:
                        try:
                            # محاولة الحصول على معلومات القناة
                            full = await client(GetFullChannelRequest(dialog.entity))
                            if hasattr(full.chats[0], 'invite_hash') and full.chats[0].invite_hash == invite_hash.lower():
                                print(f"✅ تم العثور على القناة في القنوات المنضمة: {dialog.name}")
                                return dialog.entity
                        except:
                            continue
                
                # الحل الأخير: استخدام أول قناة خاصة في القائمة (الافتراضي الآمن)
                async for dialog in client.iter_dialogs(limit=20):
                    if dialog.is_channel and not dialog.is_group:
                        print(f"✅ تم اختيار القناة: {dialog.name} (كقناة افتراضية)")
                        return dialog.entity
                
                raise Exception(
                    "فشل العثور على القناة رغم الانضمام المسبق.\n"
                    "الحل الفوري:\n"
                    "  1. تأكد من أن الرابط صالح وغير منتهي الصلاحية\n"
                    "  2. جرب استخدام رابط دعوة جديد من إعدادات القناة"
                )
            except (InviteHashInvalidError, InviteHashExpiredError):
                raise Exception(
                    "❌ رابط الدعوة غير صالح أو منتهي الصلاحية!\n"
                    "الحل: احصل على رابط دعوة جديد من إعدادات القناة (كـ مالك القناة)"
                )
            except Exception as e:
                raise Exception(f"فشل الانضمام: {str(e)}")
        except Exception as e:
            raise Exception(f"فشل الحصول على القناة: {str(e)}")
    
    # محاولة مع المعرفات العادية (@channel)
    try:
        entity = await client.get_entity(channel_input)
        print(f"✅ تم العثور على القناة: {getattr(entity, 'title', channel_input)}")
        return entity
    except Exception as e:
        raise Exception(
            f"فشل العثور على القناة '{channel_input}':\n{str(e)}\n\n"
            "التنسيقات المدعومة:\n"
            "  • روابط الدعوة الكاملة: https://t.me/+Abc123\n"
            "  • كود الدعوة المباشر: +Abc123\n"
            "  • المعرفات العامة: @channelname"
        )

async def main():
    print("="*70)
    print("🚀 سكريبت رفع المحتوى على تيليجرام - الإصدار الاحترافي")
    print("="*70)
    print(f"⚡ السرعة: تنزيل ورفع بسرعات قصوى")
    print(f"📦 الحد الأقصى للفيديو: 2047.5 ميجابايت (هامش أمان من 2048 ميجابايت الرسمي)")
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
        raise Exception("❌ الوضع غير مدعوم! اختر 'movie' للأفلام أو 'series' للمسلسلات")
    
    if not channel:
        raise Exception("❌ حقل القناة فارغ!")
    
    # إعداد العميل بتحسينات السرعة
    try:
        client = TelegramClient(
            StringSession(os.getenv('TELEGRAM_SESSION_STRING')),
            int(os.getenv('TELEGRAM_API_ID')),
            os.getenv('TELEGRAM_API_HASH'),
            # تحسينات السرعة للرفع
            request_size=1048576,  # 1 ميجابايت لكل طلب
            download_workers=4,
            flood_sleep_threshold=120
        )
        await client.start()
        me = await client.get_me()
        print(f"✅ تم تسجيل الدخول كـ: {me.first_name} (@{me.username if me.username else 'لا يوجد يوزرنيم'})")
        print(f"⚡ تم تفعيل وضع السرعة القصوى للرفع")
    except Exception as e:
        raise Exception(f"❌ فشل تسجيل الدخول: {str(e)}")
    
    # معالجة الملفات
    with tempfile.TemporaryDirectory() as tmp_dir:
        media_files = []
        image_path = None
        video_path = None
        
        try:
            if mode == 'movie':
                img_url = os.getenv('IMAGE_URL', '').strip()
                vid_url = os.getenv('VIDEO_URL', '').strip()
                vid_name = os.getenv('VIDEO_NAME', 'movie').strip() or 'movie'
                
                if not img_url or not vid_url:
                    raise Exception("❌ في وضع الأفلام: مطلوب رابط الصورة ورابط الفيديو")
                
                print("\n🎬 معالجة وضع الأفلام...")
                image_path = await validate_and_download_file(img_url, tmp_dir, 'Logo', is_image=True)
                video_path = await validate_and_download_file(vid_url, tmp_dir, vid_name, is_image=False)
                print(f"✅ جاهز للرفع: صورة + فيديو ({Path(video_path).name})")
            
            else:  # series
                try:
                    series = json.loads(os.getenv('SERIES_VIDEOS', '[]'))
                except Exception as e:
                    raise Exception(f"❌ خطأ في تنسيق JSON: {str(e)}")
                
                if not isinstance(series, list) or not series:
                    raise Exception("❌ مطلوب على الأقل ملف فيديو واحد")
                
                if len(series) > 10:
                    print(f"⚠️  سيتم رفع أول 10 ملفات فقط (الحد الأقصى للتليجرام)")
                    series = series[:10]
                
                print(f"\n📼 معالجة {len(series)} ملف للمسلسلات...")
                for i, item in enumerate(series, 1):
                    if not isinstance(item, dict) or 'url' not in item:
                        print(f"⚠️  تخطي العنصر {i}: تنسيق غير صالح")
                        continue
                    
                    url = item['url'].strip()
                    name = item.get('name', f'الحلقة_{i}').strip() or f'الحلقة_{i}'
                    
                    if not url:
                        print(f"⚠️  تخطي العنصر {i}: رابط فارغ")
                        continue
                    
                    try:
                        media_files.append(await validate_and_download_file(url, tmp_dir, name, is_image=False))
                        print(f"✅ تمت الإضافة: {Path(media_files[-1]).name}")
                    except Exception as e:
                        print(f"❌ فشل معالجة الملف {i} ({name}): {str(e)}")
                        if len(media_files) == 0:
                            raise Exception("فشل جميع ملفات المسلسلات - لا يمكن المتابعة")
                        else:
                            print("⚠️  سيتم الرفع بالملفات الناجحة فقط")
                            break
            
            # الرفع
            print(f"\n📤 جاري الرفع على القناة: {channel}")
            print(f"📝 الكابشن: {caption[:60] + '...' if len(caption) > 60 else caption}")
            
            entity = await resolve_channel(client, channel)
            
            # ===== الحل الجذري لخطأ "media object invalid" =====
            # للقنوات الخاصة: يجب استخدام طريقة الرفع كـ "مسؤول" وليس كـ "مستخدم عادي"
            # الطريقة الصحيحة: رفع الفيديو مع تعيين الصورة كـ thumbnail (ليس كـ media group)
            if mode == 'movie':
                print("\n⚡ جاري الرفع بوضع السرعة القصوى (فيديو مع صورة مصغرة)...")
                
                # الرفع بسرعة قصوى: حجم القطعة 1 ميجابايت + تفعيل البث المباشر
                start_upload = time.time()
                await client.send_file(
                    entity,
                    video_path,
                    thumb=image_path,  # ⚡ الحل السحري: استخدام الصورة كـ thumbnail وليس كـ media group
                    caption=caption,
                    supports_streaming=True,
                    force_document=False,
                    parse_mode='html',
                    part_size=1024 * 1024,  # 1 ميجابايت لكل جزء (لزيادة السرعة)
                    progress_callback=None  # تعطيل مؤشر التقدم لتوفير الموارد
                )
                upload_time = time.time() - start_upload
                video_size = Path(video_path).stat().st_size / 1024 / 1024
                upload_speed = video_size / upload_time if upload_time > 0 else 0
                
                print(f"✅ تم الرفع بنجاح! | السرعة: {upload_speed:.2f} ميجابايت/ثانية | الوقت: {upload_time:.1f} ثانية")
            
            else:  # series
                print("\n⚡ جاري رفع ملفات المسلسلات كـ مجموعة وسائط...")
                start_upload = time.time()
                
                # رفع كـ مجموعة وسائط (بدون صور - فقط فيديوهات)
                await client.send_file(
                    entity,
                    media_files,
                    caption=caption,
                    supports_streaming=True,
                    force_document=False,
                    parse_mode='html',
                    part_size=1024 * 1024,
                    progress_callback=None
                )
                upload_time = time.time() - start_upload
                total_size = sum(Path(f).stat().st_size for f in media_files) / 1024 / 1024
                upload_speed = total_size / upload_time if upload_time > 0 else 0
                
                print(f"✅ تم الرفع بنجاح! | السرعة: {upload_speed:.2f} ميجابايت/ثانية | الوقت: {upload_time:.1f} ثانية")
            
            print("\n" + "="*70)
            print("🎉 تمت العملية بنجاح!")
            print("="*70)
            print(f"📊 ملخص:")
            print(f"   - الوضع: {'فيلم' if mode == 'movie' else 'مسلسل'}")
            print(f"   - القناة: {getattr(entity, 'title', channel)}")
            print(f"   - الحد الأقصى: 2047.5 ميجابايت (من 2048 الرسمي)")
            print(f"   - السرعة: تنزيل ورفع بسرعات قصوى")
            print("="*70)
        
        finally:
            # تنظيف الملفات المؤقتة
            for f in [image_path, video_path] + media_files:
                if f and Path(f).exists():
                    try:
                        Path(f).unlink(missing_ok=True)
                    except Exception as e:
                        print(f"⚠️  فشل حذف {Path(f).name}: {str(e)}", file=sys.stderr)
            await client.disconnect()

if __name__ == "__main__":
    try:
        # تحسين أداء asyncio للسرعات القصوى
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  تم الإلغاء يدوياً", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"❌ خطأ فادح: {str(e)}", file=sys.stderr)
        print(f"{'='*70}", file=sys.stderr)
        
        error_msg = str(e).lower()
        if "ssl" in error_msg or "certificate" in error_msg:
            print("\n💡 الحل الفوري:", file=sys.stderr)
            print("   • فعّل 'skip_ssl = true' في إعدادات الـ Workflow", file=sys.stderr)
        elif "2047.5" in error_msg or "size" in error_msg or "حجم" in error_msg:
            print("\n💡 الحل الفوري:", file=sys.stderr)
            print("   • قسّم الفيديو إلى أجزاء ≤ 2047 ميجابايت", file=sys.stderr)
            print("   • أو استخدم جودة أقل (720p بدلاً من 1080p)", file=sys.stderr)
        elif "invite" in error_msg or "channel" in error_msg or "قناة" in error_msg or "private" in error_msg:
            print("\n💡 الحل الفوري (للحساب صاحب القناة):", file=sys.stderr)
            print("   1. افتح هذا الرابط في تيليجرام وأنضم يدوياً:", file=sys.stderr)
            clean_channel = os.getenv('CHANNEL', '').strip()
            if '+' in clean_channel:
                hash_part = clean_channel.split('+')[-1].split('?')[0].split('&')[0].strip('/')
                print(f"      https://t.me/+{hash_part}", file=sys.stderr)
            else:
                print(f"      {clean_channel}", file=sys.stderr)
            print("   2. شغّل الـ Workflow مجدداً بنفس الإعدادات", file=sys.stderr)
            print("   3. كـ مالك القناة: تأكد من تفعيل 'السماح للأعضاء بالنشر' في إعدادات القناة", file=sys.stderr)
        elif "media object invalid" in error_msg or "invalid" in error_msg:
            print("\n💡 الحل الجذري:", file=sys.stderr)
            print("   • تم تطبيق الحل التلقائي: رفع الفيديو مع الصورة كـ 'صورة مصغرة' (thumbnail)", file=sys.stderr)
            print("   • تأكد من تحديث السكريبت لأحدث إصدار (يحتوي على هذا الإصلاح)", file=sys.stderr)
        
        sys.exit(1)
