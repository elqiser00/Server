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
from telethon.tl.types import InputMediaPhoto, InputMediaDocument, DocumentAttributeFilename
from telethon.errors.rpcerrorlist import (
    UserAlreadyParticipantError, InviteHashInvalidError,
    InviteHashExpiredError, ChannelPrivateError
)
import requests
import ssl
import urllib3

# تجاوز تحذيرات SSL (للاستخدام الآمن عند الحاجة)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ⚠️ الحد الرسمي لتيليجرام: 2000 ميجابايت
MAX_VIDEO_SIZE_MB = 1999.0
MAX_VIDEO_SIZE_BYTES = int(MAX_VIDEO_SIZE_MB * 1024 * 1024)

def sanitize_filename(filename):
    """تنقية اسم الملف مع الحفاظ على النقاط المهمة"""
    return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip().rstrip('.')

async def validate_and_download_file(url, save_dir, base_name, is_image=False):
    """تنزيل الملف مع تخطي SSL تلقائياً عند الحاجة + عرض تقدم في سطر واحد"""
    url = url.strip()
    if not url:
        raise Exception("رابط فارغ بعد التنقية!")
    
    # محاولة التنزيل مع تخطي SSL تلقائي عند الفشل
    for attempt in range(2):
        try:
            verify_ssl = (attempt == 0)  # المحاولة الأولى: تفعيل التحقق، الثانية: تعطيله
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'identity',
                'Connection': 'keep-alive'
            }
            
            if 'github.com' in url and os.getenv('REPO_TOKEN'):
                headers['Authorization'] = f'token {os.getenv("REPO_TOKEN")}'
            
            # عرض حالة المحاولة
            if attempt == 0:
                print(f"⬇️  جاري التنزيل: {url[:60]}...")
                print(f"   SSL: مُفعّل (المحاولة الأولى)")
            else:
                print(f"   ⚠️  إعادة المحاولة مع تعطيل تحقق SSL...")
                print(f"   SSL: معطّل (المحاولة الثانية)")
            
            start_time = time.time()
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
            total_size = int(response.headers.get('content-length', 0)) or 1
            
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
            
            # التنزيل مع عرض التقدم
            CHUNK_SIZE = 65536
            with open(filepath, 'wb') as f:
                current_size = 0
                last_percent = -1
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        current_size += len(chunk)
                        elapsed = time.time() - start_time
                        speed = current_size / elapsed / 1024 / 1024 if elapsed > 0 else 0
                        percent = (current_size / total_size) * 100
                        
                        # تحديث كل 5% فقط لتجنب التكرار
                        if percent - last_percent >= 5:
                            print(
                                f"\r   تنزيل: {filepath.name} | {current_size/1024/1024:.2f}MB/{total_size/1024/1024:.2f}MB | {percent:.1f}% | {speed:.2f}MB/s",
                                end='', flush=True
                            )
                            last_percent = percent
                
                print(f"\n✅ تم التنزيل: {filepath.name} ({current_size/1024/1024:.2f}MB) | السرعة: {speed:.2f}MB/s")
            
            # فحص الحجم
            if not is_image and current_size > MAX_VIDEO_SIZE_BYTES:
                filepath.unlink(missing_ok=True)
                raise Exception(f"الحجم ({current_size/1024/1024:.1f}MB) يتجاوز 1999MB")
            
            return str(filepath)
        
        except (requests.exceptions.SSLError, ssl.SSLError, ssl.CertificateError) as e:
            if attempt == 0:
                print(f"   ❌ خطأ SSL: {str(e)[:50]}")
                continue  # إعادة المحاولة مع تعطيل SSL
            else:
                raise Exception(f"فشل التنزيل حتى بعد تعطيل SSL: {str(e)}")
        except Exception as e:
            if 'filepath' in locals() and Path(filepath).exists():
                Path(filepath).unlink(missing_ok=True)
            raise Exception(f"فشل التنزيل: {str(e)}")

async def resolve_channel(client, channel_input):
    """معالجة ذكية لجميع أنواع روابط القنوات"""
    channel_input = channel_input.strip()
    
    # تنظيف الرابط
    for prefix in ['https://', 'http://', 't.me/', 'telegram.me/']:
        if channel_input.startswith(prefix):
            channel_input = channel_input[len(prefix):]
    
    # استخراج كود الدعوة
    invite_hash = None
    if '+' in channel_input:
        parts = channel_input.split('+')
        if len(parts) > 1:
            invite_hash = parts[1].split('?')[0].split('&')[0].split('/')[0].strip()
    
    if invite_hash and len(invite_hash) >= 5:
        try:
            full_url = f"https://t.me/joinchat/{invite_hash}"
            entity = await client.get_entity(full_url)
            return entity
        except:
            # البحث في القنوات المنضمة (كـ صاحب القناة)
            async for dialog in client.iter_dialogs(limit=10):
                if dialog.is_channel and not dialog.is_group:
                    return dialog.entity
    
    return await client.get_entity(channel_input)

async def main():
    print("="*70)
    print("🚀 سكريبت رفع المحتوى على تيليجرام - الإصدار النهائي")
    print("="*70)
    print("✅ تخطي SSL تلقائياً | ✅ بوست مدمج (صورة + فيديو) | ✅ تقدم في سطر واحد")
    print("="*70)
    
    # التحقق من المتغيرات الأساسية
    required = ['MODE', 'CHANNEL', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION_STRING']
    for var in required:
        if not os.getenv(var, '').strip():
            raise Exception(f"المتغير {var} مطلوب")
    
    mode = os.getenv('MODE', '').strip().lower()
    channel = os.getenv('CHANNEL', '').strip()
    caption = os.getenv('CAPTION', '').replace('\\n', '\n').strip()
    
    if mode not in ['movie', 'series']:
        raise Exception("الوضع غير مدعوم! اختر 'movie' أو 'series'")
    
    if not channel:
        raise Exception("حقل القناة فارغ!")
    
    # تسجيل الدخول
    client = TelegramClient(
        StringSession(os.getenv('TELEGRAM_SESSION_STRING')),
        int(os.getenv('TELEGRAM_API_ID')),
        os.getenv('TELEGRAM_API_HASH'),
        flood_sleep_threshold=120
    )
    await client.start()
    me = await client.get_me()
    print(f"✅ تم تسجيل الدخول كـ: {me.first_name}")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            if mode == 'movie':
                img_url = os.getenv('IMAGE_URL', '').strip()
                vid_url = os.getenv('VIDEO_URL', '').strip()
                vid_name = os.getenv('VIDEO_NAME', 'movie').strip() or 'movie'
                
                if not img_url or not vid_url:
                    raise Exception("مطلوب رابط الصورة ورابط الفيديو")
                
                print("\n🎬 جاري تنزيل الملفات...")
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
                
                media_files = []
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
                        if not media_files:
                            raise Exception("فشل جميع الملفات")
                        break
            
            print(f"\n📤 جاري الرفع على القناة: {channel}")
            entity = await resolve_channel(client, channel)
            
            # ✅ الحل النهائي: رفع كـ مجموعة وسائط (الصورة على اليسار + الفيديو على اليمين)
            if mode == 'movie':
                print("⚡ جاري الرفع كـ بوست مدمج (صورة على اليسار + فيديو على اليمين)...")
                
                # رفع الملفات أولاً
                print("🔄 رفع الصورة إلى تيليجرام...")
                image_file = await client.upload_file(image_path)
                
                print("🔄 رفع الفيديو إلى تيليجرام...")
                video_file = await client.upload_file(video_path)
                
                # إنشاء مجموعة وسائط
                media = [
                    InputMediaPhoto(media=image_file),
                    InputMediaDocument(
                        media=video_file,
                        attributes=[DocumentAttributeFilename(file_name=Path(video_path).name)]
                    )
                ]
                
                # إرسال المجموعة
                await client.send_media_group(
                    entity,
                    media,
                    caption=caption,
                    parse_mode='html',
                    supports_streaming=True
                )
                
                print("\n✅ تم الرفع بنجاح!")
                print("🎉 الشكل: صورة على اليسار + فيديو على اليمين في منشور واحد")
            
            else:  # series
                print("⚡ جاري رفع ملفات المسلسلات كـ مجموعة وسائط...")
                media = []
                for file_path in media_files:
                    file = await client.upload_file(file_path)
                    media.append(InputMediaDocument(media=file))
                
                await client.send_media_group(
                    entity,
                    media,
                    caption=caption,
                    parse_mode='html',
                    supports_streaming=True
                )
                
                print("\n✅ تم الرفع بنجاح!")
            
            print("\n" + "="*70)
            print("🎉 تمت العملية بنجاح!")
            print("="*70)
        
        finally:
            await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  تم الإلغاء يدوياً", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"❌ خطأ: {str(e)}", file=sys.stderr)
        print(f"{'='*70}", file=sys.stderr)
        sys.exit(1)
