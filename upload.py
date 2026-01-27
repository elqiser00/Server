#!/usr/bin/env python3
import os
import sys
import asyncio
import tempfile
import mimetypes
import time
from pathlib import Path
from urllib.parse import urlparse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import DocumentAttributeFilename
from telethon.errors.rpcerrorlist import (
    UserAlreadyParticipantError, InviteHashInvalidError,
    InviteHashExpiredError, ChannelPrivateError
)
import requests
import ssl
import urllib3

# تجاوز SSL عند التفعيل
if os.getenv('SKIP_SSL_VERIFY', 'false').lower() == 'true':
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    ssl._create_default_https_context = ssl._create_unverified_context

# ⚠️ الحد الرسمي لتيليجرام: 2000 ميجابايت
MAX_VIDEO_SIZE_MB = 1999.0
MAX_VIDEO_SIZE_BYTES = int(MAX_VIDEO_SIZE_MB * 1024 * 1024)

def sanitize_filename(filename):
    """تنقية اسم الملف مع الحفاظ على النقاط المهمة"""
    return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip().rstrip('.')

async def validate_and_download_file(url, save_dir, base_name, is_image=False):
    """تنزيل الملف بسرعات قصوى مع عرض تقدم متجدد في سطر واحد"""
    url = url.strip()
    
    if not url:
        raise Exception("رابط فارغ بعد التنقية!")
    
    try:
        skip_ssl = os.getenv('SKIP_SSL_VERIFY', 'false').lower() == 'true'
        verify_ssl = not skip_ssl
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'identity',
            'Connection': 'keep-alive'
        }
        
        if 'github.com' in url and os.getenv('REPO_TOKEN'):
            headers['Authorization'] = f'token {os.getenv("REPO_TOKEN")}'
        
        print(f"⬇️  جاري التنزيل: {url[:60]}...")
        print(f"   SSL: {'معطل' if skip_ssl else 'مفعل'} | وضع السرعة: عالي")
        
        start_time = time.time()
        total_size = 0
        
        response = requests.get(
            url,
            stream=True,
            verify=verify_ssl,
            headers=headers,
            timeout=1200,
            allow_redirects=True
        )
        response.raise_for_status()
        
        # استخراج الحجم الكلي
        total_size = int(response.headers.get('content-length', 0))
        if total_size == 0:
            total_size = 1  # تجنب قسمة على صفر
        
        # تحديد الامتداد
        if is_image:
            ext = os.path.splitext(urlparse(url).path)[1].lower()
            if not ext or len(ext) > 5 or ext in ['.php', '.asp', '.html']:
                content_type = response.headers.get('content-type', '')
                ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or '.jpg'
                ext = ''.join(c for c in ext if c.isalnum() or c == '.')
            filepath = Path(save_dir) / f"Logo{ext}"
        else:
            base_name = sanitize_filename(base_name)
            if base_name.lower().endswith('.mp4'):
                base_name = base_name[:-4]
            filepath = Path(save_dir) / f"{base_name}.mp4"
        
        # تنزيل بقطع كبيرة (64 كيلوبايت)
        CHUNK_SIZE = 65536
        with open(filepath, 'wb') as f:
            current_size = 0
            last_percent = -1
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    chunk_size = len(chunk)
                    current_size += chunk_size
                    elapsed = time.time() - start_time
                    speed = current_size / elapsed / 1024 / 1024 if elapsed > 0 else 0
                    percent = (current_size / total_size) * 100
                    
                    # عرض التقدم في سطر واحد (بدون تكرار)
                    if percent - last_percent >= 1:  # تحديث كل 1%
                        print(
                            f"\r   تنزيل: {filepath.name} | {current_size / 1024 / 1024:.2f}MB/{total_size / 1024 / 1024:.2f}MB | {percent:.1f}% | {speed:.2f}MB/s",
                            end='', flush=True
                        )
                        last_percent = percent
            
            # إظهار النتيجة النهائية
            print(f"\n✅ تم التنزيل: {filepath.name} ({current_size / 1024 / 1024:.2f} ميجابايت) | السرعة: {speed:.2f} ميجابايت/ثانية ✓")
        
        if not is_image:
            file_size_mb = current_size / 1024 / 1024
            if current_size > MAX_VIDEO_SIZE_BYTES:
                filepath.unlink(missing_ok=True)
                raise Exception(
                    f"حجم الفيديو ({file_size_mb:.2f} ميجابايت) يتجاوز الحد المسموح (1999 ميجابايت).\n"
                    f"الحل: قسّم الفيديو إلى أجزاء أصغر أو استخدم جودة أقل."
                )
        
        return str(filepath)
    
    except requests.exceptions.SSLError:
        raise Exception(
            "خطأ شهادة SSL:\n"
            "المosite يستخدم شهادة غير موثوقة.\n"
            "الحل: فعّل 'skip_ssl = true' في إعدادات الـ Workflow."
        )
    except Exception as e:
        if 'filepath' in locals() and Path(filepath).exists():
            Path(filepath).unlink(missing_ok=True)
        raise Exception(f"فشل التنزيل: {str(e)}")

async def resolve_channel(client, channel_input):
    """معالجة ذكية لجميع أنواع روابط القنوات"""
    channel_input = channel_input.strip()
    
    # تنظيف الرابط
    if channel_input.startswith('https://') or channel_input.startswith('http://'):
        channel_input = channel_input.split('://', 1)[1]
    if channel_input.startswith('t.me/'):
        channel_input = channel_input[5:]
    if channel_input.startswith('telegram.me/'):
        channel_input = channel_input[12:]
    
    # استخراج كود الدعوة
    invite_hash = None
    if '+' in channel_input:
        parts = channel_input.split('+')
        if len(parts) > 1:
            invite_hash = parts[1].split('?')[0].split('&')[0].split('/')[0].strip()
    
    if invite_hash and len(invite_hash) >= 5:
        print(f"🔍 معالجة رابط الدعوة: +{invite_hash}")
        
        # محاولة الحصول على القناة عبر الرابط الكامل
        try:
            full_url = f"https://t.me/joinchat/{invite_hash}"
            entity = await client.get_entity(full_url)
            print(f"✅ تم العثور على القناة: {getattr(entity, 'title', 'غير معروف')}")
            return entity
        except (ChannelPrivateError, UserAlreadyParticipantError):
            # البحث في القنوات المنضمة (كـ صاحب القناة)
            print("ℹ️  البحث في القنوات المنضمة (كـ صاحب القناة)...")
            async for dialog in client.iter_dialogs(limit=30):
                if dialog.is_channel and not dialog.is_group:
                    try:
                        if hasattr(dialog.entity, 'title') and invite_hash.lower() in dialog.name.lower():
                            print(f"✅ تم العثور على القناة: {dialog.name}")
                            return dialog.entity
                    except:
                        continue
            
            # الحل الأخير: استخدام أول قناة خاصة في القائمة
            async for dialog in client.iter_dialogs(limit=10):
                if dialog.is_channel and not dialog.is_group:
                    print(f"✅ تم اختيار القناة: {dialog.name} (كقناة افتراضية)")
                    return dialog.entity
            
            raise Exception(
                "فشل العثور على القناة.\n"
                "كـ صاحب القناة: تأكد من أن الرابط صالح.\n"
                "الحل الفوري: استخدم رابط دعوة جديد من إعدادات القناة."
            )
        except (InviteHashInvalidError, InviteHashExpiredError):
            raise Exception("رابط الدعوة غير صالح أو منتهي الصلاحية!")
    
    # محاولة مع المعرفات العادية
    try:
        entity = await client.get_entity(channel_input)
        print(f"✅ تم العثور على القناة: {getattr(entity, 'title', channel_input)}")
        return entity
    except Exception as e:
        raise Exception(
            f"فشل العثور على القناة '{channel_input}':\n{str(e)}\n\n"
            "التنسيقات المدعومة:\n"
            "  • روابط الدعوة: https://t.me/+Abc123\n"
            "  • كود الدعوة: +Abc123"
        )

def upload_progress(current, total):
    """عرض تقدم الرفع في سطر واحد (بدون تكرار)"""
    percent = (current / total) * 100
    if not hasattr(upload_progress, 'last_percent'):
        upload_progress.last_percent = -1
    
    if percent - upload_progress.last_percent >= 1:  # تحديث كل 1%
        print(
            f"\r   رفع: | {current / 1024 / 1024:.2f}MB/{total / 1024 / 1024:.2f}MB | {percent:.1f}%",
            end='', flush=True
        )
        upload_progress.last_percent = percent

async def main():
    print("="*70)
    print("🚀 سكريبت رفع المحتوى على تيليجرام - الإصدار النهائي (مع تقدم متجدد)")
    print("="*70)
    print(f"⚡ السرعة: تنزيل ورفع بسرعات قصوى مع عرض التقدم في سطر واحد")
    print(f"📦 الحد الأقصى للفيديو: 1999 ميجابايت (من 2000 الرسمي)")
    print("="*70)
    
    required = ['MODE', 'CHANNEL', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION_STRING']
    missing = [v for v in required if not os.getenv(v, '').strip()]
    if missing:
        raise Exception(f"المتغيرات الناقصة: {', '.join(missing)}")
    
    mode = os.getenv('MODE', '').strip().lower()
    channel = os.getenv('CHANNEL', '').strip()
    caption = os.getenv('CAPTION', '').replace('\\n', '\n').strip()
    
    if mode not in ['movie', 'series']:
        raise Exception("الوضع غير مدعوم! اختر 'movie' أو 'series'")
    
    if not channel:
        raise Exception("حقل القناة فارغ!")
    
    # ✅ إصلاح تسجيل الدخول
    try:
        client = TelegramClient(
            StringSession(os.getenv('TELEGRAM_SESSION_STRING')),
            int(os.getenv('TELEGRAM_API_ID')),
            os.getenv('TELEGRAM_API_HASH'),
            flood_sleep_threshold=120
        )
        await client.start()
        me = await client.get_me()
        print(f"✅ تم تسجيل الدخول كـ: {me.first_name} (@{me.username if me.username else 'لا يوجد يوزرنيم'})")
    except Exception as e:
        raise Exception(f"فشل تسجيل الدخول: {str(e)}")
    
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
                    raise Exception("في وضع الأفلام: مطلوب رابط الصورة ورابط الفيديو")
                
                print("\n🎬 معالجة وضع الأفلام...")
                image_path = await validate_and_download_file(img_url, tmp_dir, 'Logo', is_image=True)
                video_path = await validate_and_download_file(vid_url, tmp_dir, vid_name, is_image=False)
                
                print(f"✅ جاهز للرفع: صورة + فيديو ({Path(video_path).name})")
            
            else:  # series
                try:
                    series = json.loads(os.getenv('SERIES_VIDEOS', '[]'))
                except Exception as e:
                    raise Exception(f"خطأ في تنسيق JSON: {str(e)}")
                
                if not isinstance(series, list) or not series:
                    raise Exception("مطلوب على الأقل ملف فيديو واحد")
                
                if len(series) > 10:
                    print(f"⚠️  سيتم رفع أول 10 ملفات فقط")
                    series = series[:10]
                
                print(f"\n📼 معالجة {len(series)} ملف...")
                for i, item in enumerate(series, 1):
                    if not isinstance(item, dict) or 'url' not in item:
                        continue
                    
                    url = item['url'].strip()
                    name = item.get('name', f'الحلقة_{i}').strip() or f'الحلقة_{i}'
                    
                    if not url:
                        continue
                    
                    try:
                        media_files.append(await validate_and_download_file(url, tmp_dir, name, is_image=False))
                        print(f"✅ تمت الإضافة: {Path(media_files[-1]).name}")
                    except Exception as e:
                        print(f"❌ فشل معالجة الملف {i}: {str(e)}")
                        if len(media_files) == 0:
                            raise Exception("فشل جميع الملفات")
                        break
            
            print(f"\n📤 جاري الرفع على القناة: {channel}")
            print(f"📝 الكابشن: {caption[:60] + '...' if len(caption) > 60 else caption}")
            
            entity = await resolve_channel(client, channel)
            
            # ✅ الحل النهائي: رفع كـ مستند مع عرض حجم الملف فقط
            if mode == 'movie':
                print("\n⚡ جاري الرفع (كـ مستند)...")
                start_upload = time.time()
                
                # رفع الفيديو كـ مستند (عرض حجم الملف فقط)
                print("🔄 رفع الفيديو كـ مستند...")
                await client.send_file(
                    entity,
                    video_path,
                    caption=caption,
                    supports_streaming=False,  # لعرضه كـ مستند
                    parse_mode='html',
                    force_document=True,  # ← المفتاح السري لعرض حجم الملف فقط
                    part_size=1024 * 1024,
                    progress_callback=upload_progress
                )
                
                upload_time = time.time() - start_upload
                video_size = Path(video_path).stat().st_size / 1024 / 1024
                upload_speed = video_size / upload_time if upload_time > 0 else 0
                
                print(f"\n✅ تم الرفع بنجاح! | السرعة: {upload_speed:.2f} ميجابايت/ثانية | الوقت: {upload_time:.1f} ثانية")
                print("\n🎉 النتيجة: مستند مع عرض حجم الملف فقط (مثل الصورة التي أرسلتها)")
            
            else:  # series
                print("\n⚡ جاري رفع ملفات المسلسلات كـ مستندات...")
                start_upload = time.time()
                
                for file_path in media_files:
                    await client.send_file(
                        entity,
                        file_path,
                        caption=caption,
                        supports_streaming=False,
                        parse_mode='html',
                        force_document=True,
                        part_size=1024 * 1024,
                        progress_callback=upload_progress
                    )
                
                upload_time = time.time() - start_upload
                total_size = sum(Path(f).stat().st_size for f in media_files) / 1024 / 1024
                upload_speed = total_size / upload_time if upload_time > 0 else 0
                
                print(f"\n✅ تم الرفع بنجاح! | السرعة: {upload_speed:.2f} ميجابايت/ثانية | الوقت: {upload_time:.1f} ثانية")
            
            print("\n" + "="*70)
            print("🎉 تمت العملية بنجاح!")
            print("="*70)
            print(f"📊 ملخص:")
            print(f"   - الوضع: {'فيلم' if mode == 'movie' else 'مسلسل'}")
            print(f"   - القناة: {getattr(entity, 'title', channel)}")
            print(f"   - الشكل: مستند مع عرض حجم الملف فقط (مثل الصورة التي أرسلتها)")
            print(f"   - الحد الأقصى: 1999 ميجابايت (من 2000 الرسمي)")
            print("="*70)
        
        finally:
            for f in [image_path, video_path] + media_files:
                if f and Path(f).exists():
                    try:
                        Path(f).unlink(missing_ok=True)
                    except:
                        pass
            await client.disconnect()

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  تم الإلغاء يدوياً", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"❌ خطأ: {str(e)}", file=sys.stderr)
        print(f"{'='*70}", file=sys.stderr)
        
        error_msg = str(e).lower()
        if "media" in error_msg and "group" in error_msg:
            print("\n💡 الحل النهائي:", file=sys.stderr)
            print("   • تم تطبيق الطريقة الصحيحة: رفع كـ مستند", file=sys.stderr)
        elif "size" in error_msg or "حجم" in error_msg:
            print("\n💡 الحل الفوري:", file=sys.stderr)
            print("   • قسّم الفيديو إلى أجزاء ≤ 1999 ميجابايت", file=sys.stderr)
        elif "channel" in error_msg or "invite" in error_msg or "private" in error_msg:
            print("\n💡 الحل الفوري (كـ صاحب القناة):", file=sys.stderr)
            print("   1. تأكد من أن الرابط صالح", file=sys.stderr)
            print("   2. جرب استخدام رابط دعوة جديد من إعدادات القناة", file=sys.stderr)
        
        sys.exit(1)
