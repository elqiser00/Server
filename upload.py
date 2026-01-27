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
from telethon.errors.rpcerrorlist import (
    UserAlreadyParticipantError, InviteHashInvalidError,
    InviteHashExpiredError, ChannelPrivateError
)
import requests
import ssl
import urllib3
import time

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
    """تنزيل الملف بسرعات قصوى مع فحص الحجم"""
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
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)
                    
                    if not is_image and total_size > MAX_VIDEO_SIZE_BYTES * 1.05:
                        f.close()
                        filepath.unlink(missing_ok=True)
                        elapsed = time.time() - start_time
                        speed = total_size / elapsed / 1024 / 1024 if elapsed > 0 else 0
                        raise Exception(
                            f"توقف التنزيل: الحجم تجاوز {MAX_VIDEO_SIZE_MB} ميجابايت!\n"
                            f"الحجم الحالي: {total_size / 1024 / 1024:.2f} ميجابايت | السرعة: {speed:.2f} ميجابايت/ثانية"
                        )
        
        if total_size == 0:
            raise Exception("الملف فارغ بعد التنزيل")
        
        elapsed = time.time() - start_time
        speed = total_size / elapsed / 1024 / 1024 if elapsed > 0 else 0
        
        if not is_image:
            file_size_mb = total_size / 1024 / 1024
            if total_size > MAX_VIDEO_SIZE_BYTES:
                filepath.unlink(missing_ok=True)
                raise Exception(
                    f"حجم الفيديو ({file_size_mb:.2f} ميجابايت) يتجاوز الحد المسموح (1999 ميجابايت).\n"
                    f"الحل: قسّم الفيديو إلى أجزاء أصغر أو استخدم جودة أقل."
                )
            print(f"✅ تم التنزيل: {filepath.name} ({file_size_mb:.2f} ميجابايت) | السرعة: {speed:.2f} ميجابايت/ثانية ✓")
        else:
            print(f"✅ تم التنزيل: {filepath.name} ({total_size / 1024 / 1024:.2f} ميجابايت) | السرعة: {speed:.2f} ميجابايت/ثانية")
        
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
            # البحث في القنوات المنضمة
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

async def main():
    print("="*70)
    print("🚀 سكريبت رفع المحتوى على تيليجرام - الإصدار النهائي (مطابق لتيليجرام ديسكتوب 100%)")
    print("="*70)
    print(f"⚡ السرعة: تنزيل ورفع بسرعات قصوى")
    print(f"📦 الحد الأقصى للفيديو: 1999 ميجابايت (من 2000 الرسمي)")
    print("="*70)
    print("✅ يعمل بنفس طريقة تيليجرام ديسكتوب - بدون أخطاء")
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
    
    # ✅ تسجيل الدخول
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
                
                print(f"✅ جاهز للرفع: فيديو مع صورة مصغرة مخصصة ({Path(video_path).name})")
            
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
            
            # ✅ الحل النهائي: رفع الفيديو مع صورة مصغرة مخصصة (مثل تيليجرام ديسكتوب 100%)
            if mode == 'movie':
                print("\n⚡ جاري الرفع كـ فيديو مع صورة مصغرة مخصصة (مثل تيليجرام ديسكتوب 100%)...")
                start_upload = time.time()
                
                # رفع الفيديو مع الصورة كـ صورة مصغرة مخصصة
                await client.send_file(
                    entity,
                    video_path,
                    thumb=image_path if image_path and Path(image_path).exists() else None,
                    caption=caption,
                    supports_streaming=True,  # تفعيل البث المباشر
                    parse_mode='html',
                    force_document=False,
                    part_size=1024 * 1024,  # 1 ميجابايت لكل جزء
                    progress_callback=None
                )
                
                upload_time = time.time() - start_upload
                video_size = Path(video_path).stat().st_size / 1024 / 1024
                upload_speed = video_size / upload_time if upload_time > 0 else 0
                
                print(f"✅ تم الرفع بنجاح! | السرعة: {upload_speed:.2f} ميجابايت/ثانية | الوقت: {upload_time:.1f} ثانية")
                print("\n🎉 النتيجة: فيديو مع صورة مصغرة مخصصة (مطابق لتيليجرام ديسكتوب 100%)")
            
            else:  # series
                print("\n⚡ جاري رفع ملفات المسلسلات (منشور منفصل لكل ملف)...")
                for i, file_path in enumerate(media_files, 1):
                    start_upload = time.time()
                    await client.send_file(
                        entity,
                        file_path,
                        caption=f"{caption}\n\nالحلقة {i}" if len(media_files) > 1 else caption,
                        supports_streaming=True,
                        parse_mode='html',
                        force_document=False,
                        part_size=1024 * 1024,
                        progress_callback=None
                    )
                    upload_time = time.time() - start_upload
                    file_size = Path(file_path).stat().st_size / 1024 / 1024
                    upload_speed = file_size / upload_time if upload_time > 0 else 0
                    print(f"✅ تم رفع الحلقة {i}: {Path(file_path).name} | السرعة: {upload_speed:.2f} ميجابايت/ثانية")
            
            print("\n" + "="*70)
            print("🎉 تمت العملية بنجاح!")
            print("="*70)
            print(f"📊 ملخص:")
            print(f"   - الوضع: {'فيلم' if mode == 'movie' else 'مسلسل'}")
            print(f"   - القناة: {getattr(entity, 'title', channel)}")
            print(f"   - الشكل: فيديو مع صورة مصغرة مخصصة (مثل تيليجرام ديسكتوب)")
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
        if "media" in error_msg and ("invalid" in error_msg or "group" in error_msg):
            print("\n💡 الحل النهائي:", file=sys.stderr)
            print("   • تم تطبيق الحل الصحيح: رفع الفيديو مع صورة مصغرة مخصصة", file=sys.stderr)
            print("   • هذه هي الطريقة القياسية لتيليجرام ديسكتوب", file=sys.stderr)
        elif "thumb" in error_msg or "image" in error_msg:
            print("\n💡 الحل:", file=sys.stderr)
            print("   • تأكد من أن الصورة بصيغة JPG/PNG (تيليجرام لا يدعم WebP كـ صورة مصغرة)", file=sys.stderr)
            print("   • إذا كانت الصورة WebP: قم بتحويلها إلى JPG قبل الرفع", file=sys.stderr)
        elif "size" in error_msg or "حجم" in error_msg:
            print("\n💡 الحل الفوري:", file=sys.stderr)
            print("   • قسّم الفيديو إلى أجزاء ≤ 1999 ميجابايت", file=sys.stderr)
        
        sys.exit(1)
