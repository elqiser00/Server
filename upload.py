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
from telethon.tl.types import InputMediaPhoto, InputMediaDocument
from telethon.tl.types import DocumentAttributeFilename
import requests
import ssl
import urllib3

# تجاوز أخطاء SSL عند التفعيل
if os.getenv('SKIP_SSL_VERIFY', 'false').lower() == 'true':
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    ssl._create_default_https_context = ssl._create_unverified_context

def sanitize_filename(filename, allow_dots=True):
    """تنقية اسم الملف مع السماح بالنقط (للاحترافية)"""
    if allow_dots:
        return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip().strip()
    return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_')).rstrip().strip()

async def validate_and_download_file(url, save_dir, base_name, is_image=False, force_ext=None):
    """تنزيل الملف مع معالجة الامتدادات بشكل ذكي"""
    try:
        verify_ssl = os.getenv('SKIP_SSL_VERIFY', 'false').lower() != 'true'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        if 'github.com' in url and os.getenv('REPO_TOKEN'):
            headers['Authorization'] = f'token {os.getenv("REPO_TOKEN")}'
        
        response = requests.get(url, stream=True, verify=verify_ssl, headers=headers, timeout=600)
        response.raise_for_status()
        
        # تحديد الامتداد تلقائياً
        if is_image:
            # للصور: نستخدم الامتداد الأصلي من الرابط أو الـ Content-Type
            parsed_url = urlparse(url)
            ext = os.path.splitext(parsed_url.path)[1].lower()
            if not ext or len(ext) > 5 or ext == '.php':
                content_type = response.headers.get('content-type', '')
                ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or '.jpg'
            filename = f"Logo{ext}"
        else:
            # للفيديو: نفرض .mp4 مع تجنب التكرار
            if force_ext:
                base_name = base_name.rstrip('.').rstrip()
                if base_name.lower().endswith('.mp4'):
                    base_name = base_name[:-4]
                filename = f"{base_name}.mp4"
            else:
                filename = f"{base_name}.mp4"
        
        safe_filename = sanitize_filename(filename, allow_dots=True)
        filepath = Path(save_dir) / safe_filename
        
        # تنزيل بتتابع لتجنب استهلاك الذاكرة
        total_size = 0
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)
        
        if total_size == 0:
            raise Exception("الملف فارغ بعد التنزيل")
        
        print(f"✓ تم تنزيل {safe_filename} بنجاح ({total_size / 1024 / 1024:.2f} MB)")
        return str(filepath)
    
    except Exception as e:
        raise Exception(f"فشل تنزيل {url}: {str(e)}")

async def resolve_channel_entity(client, channel_input):
    """معالجة جميع أنواع معرفات القنوات (بما فيها روابط الدعوة)"""
    channel_input = channel_input.strip()
    
    # الحالة 1: رابط دعوة خاص (يبدأ بـ + أو يحتوي t.me/+)
    if channel_input.startswith('+') or 't.me/+' in channel_input or 'telegram.me/+' in channel_input:
        try:
            # استخراج كود الدعوة
            if 't.me/+' in channel_input or 'telegram.me/+' in channel_input:
                hash_part = channel_input.split('+')[-1].split('?')[0].split('&')[0].strip('/')
            else:
                hash_part = channel_input.lstrip('+')
            
            print(f"🔄 محاولة الانضمام للقناة عبر رابط الدعوة (الكود: {hash_part})...")
            result = await client(ImportChatInviteRequest(hash_part))
            
            if hasattr(result, 'chats') and result.chats:
                chat = result.chats[0]
                print(f"✅ تم الانضمام للقناة: {getattr(chat, 'title', 'بدون اسم')}")
                return chat
            else:
                raise Exception("فشل استخراج معلومات القناة من رابط الدعوة")
        except Exception as e:
            raise Exception(f"فشل معالجة رابط الدعوة: {str(e)}. تأكد من أن الحساب انضم للقناة مسبقاً أو أن الرابط صالح.")
    
    # الحالة 2: معرف عادي (@channel) أو ID رقمي
    try:
        entity = await client.get_entity(channel_input)
        print(f"✅ تم العثور على القناة: {getattr(entity, 'title', channel_input)}")
        return entity
    except Exception as e:
        raise Exception(f"فشل العثور على القناة '{channel_input}': {str(e)}. "
                        f"استخدم معرف القناة الصحيح (مثل @yourchannel) أو تأكد من انضمام الحساب للقناة.")

async def upload_to_telegram():
    print("="*70)
    print("🚀 سكريبت رفع المحتوى على تيليجرام - الإصدار المحسن")
    print("="*70)
    
    # ============ التحقق من المتغيرات ============
    required_vars = ['MODE', 'CHANNEL', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION_STRING']
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise Exception(f"❌ المتغيرات الناقصة: {', '.join(missing)}\n"
                        "تأكد من إعداد الأسرار في GitHub Secrets")
    
    mode = os.getenv('MODE', '').lower()
    channel_input = os.getenv('CHANNEL', '').strip()
    caption = os.getenv('CAPTION', '').replace('\\n', '\n')
    
    if mode not in ['movie', 'series']:
        raise Exception("❌ الوضع غير مدعوم! اختر 'movie' للأفلام أو 'series' للمسلسلات")
    
    if not channel_input:
        raise Exception("❌ معرف القناة فارغ! أدخل معرف القناة الصحيح (@channel) أو رابط دعوة صالح")
    
    # ============ إعداد العميل ============
    try:
        api_id = int(os.getenv('TELEGRAM_API_ID', '0'))
        api_hash = os.getenv('TELEGRAM_API_HASH', '')
        session_str = os.getenv('TELEGRAM_SESSION_STRING', '')
        
        client = TelegramClient(StringSession(session_str), api_id, api_hash)
        await client.start()
        print(f"✅ تم تسجيل الدخول بنجاح (حساب شخصي)")
    except Exception as e:
        raise Exception(f"❌ فشل تسجيل الدخول: {str(e)}\n"
                        "تأكد من صحة TELEGRAM_API_ID و TELEGRAM_API_HASH و TELEGRAM_SESSION_STRING")
    
    # ============ معالجة الملفات ============
    with tempfile.TemporaryDirectory() as tmp_dir:
        media_files = []
        try:
            if mode == 'movie':
                # ============ وضع الأفلام ============
                image_url = os.getenv('IMAGE_URL', '').strip()
                video_url = os.getenv('VIDEO_URL', '').strip()
                video_name = os.getenv('VIDEO_NAME', 'movie').strip() or 'movie'
                
                if not image_url or not video_url:
                    raise Exception("❌ في وضع الأفلام: مطلوب رابط الصورة ورابط الفيديو")
                
                # تنزيل الصورة باسم ثابت "Logo" مع الامتداد الأصلي
                image_path = await validate_and_download_file(
                    image_url, 
                    tmp_dir, 
                    'Logo', 
                    is_image=True
                )
                media_files.append(image_path)
                
                # تنزيل الفيديو مع تجنب تكرار الامتداد
                video_path = await validate_and_download_file(
                    video_url, 
                    tmp_dir, 
                    video_name,
                    is_image=False,
                    force_ext='mp4'
                )
                media_files.append(video_path)
                
                print(f"\n🎬 وضع الأفلام جاهز:")
                print(f"   - الصورة: {Path(image_path).name}")
                print(f"   - الفيديو: {Path(video_path).name}")
            
            else:  # series
                # ============ وضع المسلسلات ============
                try:
                    series_data = json.loads(os.getenv('SERIES_VIDEOS', '[]'))
                except json.JSONDecodeError as e:
                    raise Exception(f"❌ خطأ في تنسيق JSON للمسلسلات: {str(e)}")
                
                if not isinstance(series_data, list) or len(series_data) == 0:
                    raise Exception("❌ مطلوب على الأقل ملف فيديو واحد للمسلسلات")
                
                if len(series_data) > 10:
                    print(f"⚠️  تم اكتشاف {len(series_data)} ملفات - سيتم رفع أول 10 ملفات فقط")
                    series_data = series_data[:10]
                
                for idx, item in enumerate(series_data, 1):
                    if not isinstance(item, dict) or 'url' not in item:
                        print(f"⚠️  تخطي العنصر {idx}: تنسيق غير صالح")
                        continue
                    
                    url = item['url'].strip()
                    name = item.get('name', f'Episode_{idx}').strip() or f'Episode_{idx}'
                    
                    if not url:
                        print(f"⚠️  تخطي العنصر {idx}: رابط فارغ")
                        continue
                    
                    video_path = await validate_and_download_file(
                        url, 
                        tmp_dir, 
                        name,
                        is_image=False,
                        force_ext='mp4'
                    )
                    media_files.append(video_path)
                    print(f"📺 تمت إضافة: {Path(video_path).name}")
                
                print(f"\n📼 وضع المسلسلات جاهز: {len(media_files)} ملفات")
            
            # ============ رفع المحتوى ============
            print(f"\n📤 جاري الرفع على القناة...")
            print(f"   - القناة: {channel_input}")
            print(f"   - عدد الملفات: {len(media_files)}")
            print(f"   - الكابشن: {caption[:60] + '...' if len(caption) > 60 else caption}")
            
            # حل معرف القناة (يدعم روابط الدعوة الآن)
            entity = await resolve_channel_entity(client, channel_input)
            
            # رفع كـ Media Group
            await client.send_file(
                entity,
                media_files,
                caption=caption,
                supports_streaming=True,
                force_document=False,
                parse_mode='html',
                silent=False
            )
            
            print("\n" + "="*70)
            print("✅ تم الرفع بنجاح!")
            print("="*70)
            print(f"📊 ملخص:")
            print(f"   - الوضع: {'فيلم' if mode == 'movie' else 'مسلسل'}")
            print(f"   - الملفات المرفوعة: {len(media_files)}")
            print(f"   - القناة: {getattr(entity, 'title', channel_input)}")
            print("="*70)
        
        except Exception as e:
            print(f"\n❌ فشل الرفع: {str(e)}", file=sys.stderr)
            raise
        finally:
            # تنظيف الملفات المؤقتة
            for file in media_files:
                try:
                    Path(file).unlink(missing_ok=True)
                except Exception as e:
                    print(f"⚠️  فشل حذف {file}: {str(e)}", file=sys.stderr)
            await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(upload_to_telegram())
    except KeyboardInterrupt:
        print("\n⚠️  تم الإلغاء يدوياً", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 خطأ فادح: {str(e)}", file=sys.stderr)
        sys.exit(1)
