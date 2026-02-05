#!/usr/bin/env python3
import os
import sys
import asyncio
import tempfile
import mimetypes
import time
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    DocumentAttributeVideo, 
    DocumentAttributeFilename
)
import requests
import ssl
import urllib3
from PIL import Image

# تجاوز تحذيرات SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MAX_VIDEO_SIZE_MB = 1999.0
MAX_VIDEO_SIZE_BYTES = int(MAX_VIDEO_SIZE_MB * 1024 * 1024)

def sanitize_filename(filename):
    return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip().rstrip('.')

async def validate_and_download_file(url, save_dir, base_name, is_image=False):
    """تنزيل الملف مع تخطي SSL تلقائياً"""
    url = url.strip()
    if not url:
        raise Exception("رابط فارغ!")
    
    for attempt in range(2):
        try:
            verify_ssl = (attempt == 0)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'identity',
                'Connection': 'keep-alive'
            }
            
            if 'github.com' in url and os.getenv('REPO_TOKEN'):
                headers['Authorization'] = f'token {os.getenv("REPO_TOKEN")}'
            
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
            
            total_size = int(response.headers.get('content-length', 0)) or 1
            
            if is_image:
                ext = os.path.splitext(urlparse(url).path)[1].lower()
                if not ext or len(ext) > 5 or ext in ['.php', '.asp', '.html']:
                    content_type = response.headers.get('content-type', '')
                    ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or '.jpg'
                    ext = ''.join(c for c in ext if c.isalnum() or c == '.')
                filepath = Path(save_dir) / f"poster{ext}"
            else:
                base_name = sanitize_filename(base_name)
                if base_name.lower().endswith('.mp4'):
                    base_name = base_name[:-4]
                filepath = Path(save_dir) / f"{base_name}.mp4"
            
            CHUNK_SIZE = 65536
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
            
            elapsed = time.time() - start_time
            speed = total_size / elapsed / 1024 / 1024 if elapsed > 0 else 0
            
            return str(filepath), total_size / 1024 / 1024, speed
        
        except (requests.exceptions.SSLError, ssl.SSLError, ssl.CertificateError) as e:
            if attempt == 0:
                continue
            else:
                raise Exception(f"فشل التنزيل حتى بعد تعطيل SSL")
        except Exception as e:
            if 'filepath' in locals() and Path(filepath).exists():
                Path(filepath).unlink(missing_ok=True)
            raise Exception(f"فشل التنزيل: {str(e)}")

def extract_video_info(video_path):
    """استخراج Thumbnail + المدة + الأبعاد من الفيديو"""
    try:
        # استخراج Thumbnail من ثانية 5 (أحسن من الأولى)
        thumb_path = video_path + "_thumb.jpg"
        cmd_thumb = [
            'ffmpeg',
            '-i', video_path,
            '-ss', '00:00:05',        # ثانية 5 عشان تكون مش سودة
            '-vframes', '1',
            '-q:v', '2',              # جودة عالية
            '-y',
            thumb_path
        ]
        
        result = subprocess.run(cmd_thumb, capture_output=True, text=True, timeout=30)
        thumb_success = result.returncode == 0 and os.path.exists(thumb_path)
        
        # استخراج المدة والأبعاد
        cmd_info = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,duration',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1'
        ]
        
        # نجرب نجيب المدة
        duration = 0
        width = 1280
        height = 720
        
        try:
            result = subprocess.run(
                cmd_info + [video_path],
                capture_output=True, text=True, timeout=10
            )
            
            for line in result.stdout.split('\n'):
                if 'duration=' in line:
                    try:
                        duration = float(line.split('=')[1])
                    except:
                        pass
                elif 'width=' in line:
                    try:
                        width = int(line.split('=')[1])
                    except:
                        pass
                elif 'height=' in line:
                    try:
                        height = int(line.split('=')[1])
                    except:
                        pass
        except:
            pass
        
        # لو مفيش ثمبنيل، نرجع None
        if not thumb_success:
            thumb_path = None
            
        return {
            'thumb_path': thumb_path,
            'duration': int(duration),
            'width': width,
            'height': height
        }
        
    except Exception as e:
        return {
            'thumb_path': None,
            'duration': 0,
            'width': 1280,
            'height': 720
        }

async def resolve_channel(client, channel_input):
    """معالجة ذكية لجميع أنواع روابط القنوات"""
    channel_input = channel_input.strip()
    
    for prefix in ['https://', 'http://', 't.me/', 'telegram.me/']:
        if channel_input.startswith(prefix):
            channel_input = channel_input[len(prefix):]
    
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
            async for dialog in client.iter_dialogs(limit=10):
                if dialog.is_channel and not dialog.is_group:
                    return dialog.entity
    
    return await client.get_entity(channel_input)

async def main():
    print("="*70)
    print("🚀 سكريبت رفع الفيديو على تيليجرام - مع Thumbnail ومدة الفيديو")
    print("="*70)
    print("✅ فيديو واحد ببوستر | ✅ مدة الفيديو ظاهرة | ✅ قابل للتشغيل")
    print("="*70)
    
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
                
                # تنزيل البوستر (للاستخدام كـ Thumb)
                print("جاري تحميل البوستر...", end='', flush=True)
                poster_path, img_size, img_speed = await validate_and_download_file(img_url, tmp_dir, 'poster', is_image=True)
                print(f" ✅ ({img_size:.2f}MB)")
                
                # تحويل WebP إلى JPG لو لازم
                if poster_path.lower().endswith('.webp'):
                    try:
                        jpg_path = str(Path(poster_path).with_suffix('.jpg'))
                        img = Image.open(poster_path).convert('RGB')
                        img.save(jpg_path, 'JPEG', quality=95)
                        poster_path = jpg_path
                        print(f"   تم تحويل WebP إلى JPG")
                    except:
                        pass
                
                # تنزيل الفيديو
                print("جاري تحميل الفيديو...", end='', flush=True)
                video_path, vid_size, vid_speed = await validate_and_download_file(vid_url, tmp_dir, vid_name, is_image=False)
                print(f" ✅ ({vid_size:.2f}MB)")
                
                # استخراج معلومات الفيديو (Thumbnail + مدة + أبعاد)
                print("جاري تحليل الفيديو...", end='', flush=True)
                video_info = extract_video_info(video_path)
                
                # نستخدم البوستر كـ Thumb للفيديو
                thumb_to_use = poster_path if os.path.exists(poster_path) else video_info['thumb_path']
                print(f" ✅ (المدة: {video_info['duration']} ثانية)")
                
                print(f"\n📤 جاري الرفع على القناة: {channel}")
                entity = await resolve_channel(client, channel)
                
                print("جاري رفع الفيديو مع البوستر...", end='', flush=True)
                
                # ✅ الحل الصحيح: رفع فيديو واحد بـ attributes
                # نستخدم thumb=poster_path عشان يظهر البوستر كخلفية
                # ونضيف DocumentAttributeVideo عشان تظهر المدة والأبعاد
                
                attributes = [
                    DocumentAttributeVideo(
                        duration=video_info['duration'],
                        w=video_info['width'],
                        h=video_info['height'],
                        supports_streaming=True
                    ),
                    DocumentAttributeFilename(file_name=f"{vid_name}.mp4")
                ]
                
                # ✅ الرفع: فيديو واحد بـ thumb = البوستر
                await client.send_file(
                    entity,
                    file=video_path,
                    caption=caption,
                    parse_mode='html',
                    thumb=thumb_to_use,           # ✅ البوستر هيظهر كخلفية
                    attributes=attributes,        # ✅ المدة والأبعاد
                    supports_streaming=True,      # ✅ قابل للتشغيل
                    force_document=False          # ✅ يظهر كـ فيديو مش ملف
                )
                
                print(" ✅")
                print("\n✅ تم الرفع بنجاح!")
                print("🎉 الشكل: فيديو واحد ببوستر + مدة ظاهرة + قابل للتشغيل")
            
            else:  # series
                try:
                    import json
                    series = json.loads(os.getenv('SERIES_VIDEOS', '[]'))
                except Exception as e:
                    raise Exception(f"خطأ في تنسيق JSON: {str(e)}")
                
                if not isinstance(series, list) or not series:
                    raise Exception("مطلوب على الأقل ملف فيديو واحد")
                
                if len(series) > 10:
                    print(f"⚠️  سيتم رفع أول 10 ملفات فقط")
                    series = series[:10]
                
                media_files = []
                thumbs = []
                
                for i, item in enumerate(series, 1):
                    if not isinstance(item, dict) or 'url' not in item:
                        continue
                    
                    url = item['url'].strip()
                    name = item.get('name', f'الحلقة_{i}').strip() or f'الحلقة_{i}'
                    
                    if not url:
                        continue
                    
                    try:
                        print(f"جاري تحميل الحلقة {i}...", end='', flush=True)
                        file_path, file_size, file_speed = await validate_and_download_file(url, tmp_dir, name, is_image=False)
                        
                        # استخراج معلومات كل فيديو
                        vid_info = extract_video_info(file_path)
                        
                        # نجهز attributes لكل فيديو
                        attrs = [
                            DocumentAttributeVideo(
                                duration=vid_info['duration'],
                                w=vid_info['width'],
                                h=vid_info['height'],
                                supports_streaming=True
                            ),
                            DocumentAttributeFilename(file_name=f"{name}.mp4")
                        ]
                        
                        media_files.append((file_path, attrs, vid_info['thumb_path']))
                        print(f" ✅ ({file_size:.2f}MB)")
                    except Exception as e:
                        print(f" ❌")
                        continue
                
                if not media_files:
                    raise Exception("فشل تحميل جميع الملفات")
                
                print(f"\n📤 جاري رفع {len(media_files)} حلقات...")
                entity = await resolve_channel(client, channel)
                
                # رفع المسلسلات كـ Album (كل فيديو بـ thumb)
                files_to_send = []
                for file_path, attrs, thumb in media_files:
                    files_to_send.append({
                        'file': file_path,
                        'thumb': thumb,
                        'attributes': attrs
                    })
                
                await client.send_file(
                    entity,
                    files_to_send,
                    caption=caption,
                    parse_mode='html',
                    supports_streaming=True,
                    force_document=False
                )
                
                print(" ✅")
                print(f"\n✅ تم رفع {len(media_files)} حلقات بنجاح!")
            
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
