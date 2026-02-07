#!/usr/bin/env python3
import os
import sys
import asyncio
import tempfile
import mimetypes
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from pyrogram import Client
from pyrogram.types import InputMediaPhoto, InputMediaVideo
import requests
import ssl
import urllib3
from PIL import Image

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def sanitize_filename(filename):
    return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip().rstrip('.')

async def download_file(url, save_dir, base_name, is_image=False):
    """تنزيل الملف"""
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
            
            response = requests.get(
                url, stream=True, verify=verify_ssl, headers=headers,
                timeout=1200, allow_redirects=True
            )
            response.raise_for_status()
            
            if is_image:
                ext = os.path.splitext(urlparse(url).path)[1].lower()
                if not ext or len(ext) > 5:
                    content_type = response.headers.get('content-type', '')
                    ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or '.jpg'
                filepath = Path(save_dir) / f"poster{ext}"
            else:
                base_name = sanitize_filename(base_name)
                if base_name.lower().endswith('.mp4'):
                    base_name = base_name[:-4]
                filepath = Path(save_dir) / f"{base_name}.mp4"
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            
            file_size = os.path.getsize(filepath) / 1024 / 1024
            return str(filepath), file_size
        
        except (requests.exceptions.SSLError, ssl.SSLError):
            if attempt == 0:
                continue
            raise Exception("فشل التنزيل حتى بعد تعطيل SSL")
        except Exception as e:
            raise Exception(f"فشل التنزيل: {str(e)}")

def get_video_info(video_path):
    """استخراج معلومات الفيديو"""
    try:
        # Thumbnail من الثانية 3
        thumb_path = video_path + "_thumb.jpg"
        subprocess.run([
            'ffmpeg', '-i', video_path, '-ss', '00:00:03',
            '-vframes', '1', '-q:v', '2', '-y', thumb_path
        ], capture_output=True, timeout=30)
        
        # معلومات الفيديو
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,duration',
            '-of', 'default=noprint_wrappers=1', video_path
        ], capture_output=True, text=True, timeout=10)
        
        duration, width, height = 0, 1280, 720
        for line in result.stdout.split('\n'):
            if 'duration=' in line:
                try: duration = int(float(line.split('=')[1]))
                except: pass
            elif 'width=' in line:
                try: width = int(line.split('=')[1])
                except: pass
            elif 'height=' in line:
                try: height = int(line.split('=')[1])
                except: pass
        
        return {
            'thumb': thumb_path if os.path.exists(thumb_path) else None,
            'duration': duration,
            'width': width,
            'height': height
        }
    except Exception as e:
        print(f"خطأ في تحليل الفيديو: {e}")
        return {'thumb': None, 'duration': 0, 'width': 1280, 'height': 720}

def get_image_info(image_path):
    """استخراج أبعاد الصورة"""
    try:
        with Image.open(image_path) as img:
            return img.width, img.height
    except:
        return 1280, 720

def resolve_channel_id(channel_input):
    """تحويل رابط القناة لـ ID"""
    channel_input = channel_input.strip()
    
    # تنظيف الرابط
    for prefix in ['https://', 'http://', 't.me/', 'telegram.me/']:
        if channel_input.startswith(prefix):
            channel_input = channel_input[len(prefix):]
            break
    
    # إزالة @
    if channel_input.startswith('@'):
        channel_input = channel_input[1:]
    
    # رابط دعوة خاص
    if '+' in channel_input:
        # Pyrogram بيتعامل مع روابط الدعوة بشكل مختلف
        # هنرجع الـ link كامل وهو هيتعامل معاه
        return channel_input
    
    # قناة عامة
    return f"@{channel_input}"

async def main():
    print("="*70)
    print("🚀 سكريبت رفع Album (Pyrogram) - صورة + فيديو")
    print("="*70)
    
    required = ['MODE', 'CHANNEL', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION_STRING']
    for var in required:
        if not os.getenv(var, '').strip():
            raise Exception(f"المتغير {var} مطلوب")
    
    mode = os.getenv('MODE', '').strip().lower()
    channel = os.getenv('CHANNEL', '').strip()
    caption = os.getenv('CAPTION', '').replace('\\n', '\n').strip()
    
    if mode not in ['movie', 'series']:
        raise Exception("اختر 'movie' أو 'series'")
    
    # ✅ Pyrogram Client
    app = Client(
        "my_account",
        api_id=int(os.getenv('TELEGRAM_API_ID')),
        api_hash=os.getenv('TELEGRAM_API_HASH'),
        session_string=os.getenv('TELEGRAM_SESSION_STRING'),
        flood_sleep_threshold=120
    )
    
    async with app:
        me = await app.get_me()
        print(f"✅ تم تسجيل الدخول: {me.first_name}")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            if mode == 'movie':
                img_url = os.getenv('IMAGE_URL', '').strip()
                vid_url = os.getenv('VIDEO_URL', '').strip()
                vid_name = os.getenv('VIDEO_NAME', 'movie').strip() or 'movie'
                
                if not img_url or not vid_url:
                    raise Exception("مطلوب رابط الصورة والفيديو")
                
                print("\n📥 جاري التحميل...")
                
                # تحميل الصورة
                print("تحميل البوستر...", end='', flush=True)
                img_path, img_size = await download_file(img_url, tmp_dir, 'poster', is_image=True)
                print(f" ✅ ({img_size:.1f}MB)")
                
                # تحويل WebP لـ JPG
                if img_path.lower().endswith('.webp'):
                    try:
                        jpg_path = str(Path(img_path).with_suffix('.jpg'))
                        img = Image.open(img_path).convert('RGB')
                        img.save(jpg_path, 'JPEG', quality=95)
                        img_path = jpg_path
                    except: pass
                
                # تحميل الفيديو
                print("تحميل الفيديو...", end='', flush=True)
                vid_path, vid_size = await download_file(vid_url, tmp_dir, vid_name, is_image=False)
                print(f" ✅ ({vid_size:.1f}MB)")
                
                # معلومات الفيديو والصورة
                print("تحليل الملفات...", end='', flush=True)
                vinfo = get_video_info(vid_path)
                img_w, img_h = get_image_info(img_path)
                print(f" ✅")
                
                print(f"📐 أبعاد الصورة: {img_w}x{img_h}")
                print(f"📐 أبعاد الفيديو: {vinfo['width']}x{vinfo['height']}")
                
                # تحديد القناة
                chat_id = resolve_channel_id(channel)
                print(f"\n📤 جاري رفع Album على: {chat_id}")
                
                # ✅ إعداد الـ media group
                media_group = []
                
                # 1. الصورة
                media_group.append(
                    InputMediaPhoto(
                        media=img_path,
                        caption=caption
                    )
                )
                
                # 2. الفيديو مع thumbnail
                video_kwargs = {
                    'media': vid_path,
                    'supports_streaming': True
                }
                
                # إضافة thumbnail لو موجود
                if vinfo['thumb'] and os.path.exists(vinfo['thumb']):
                    video_kwargs['thumb'] = vinfo['thumb']
                
                media_group.append(InputMediaVideo(**video_kwargs))
                
                print("إرسال الألبوم...", end='', flush=True)
                
                # ✅ إرسال الـ album
                await app.send_media_group(
                    chat_id=chat_id,
                    media=media_group
                )
                
                print(" ✅ تم الرفع!")
                print("\n🎉 Album: صورة فوق + فيديو تحت في نفس البوست")
            
            else:  # series
                try:
                    import json
                    series = json.loads(os.getenv('SERIES_VIDEOS', '[]'))
                except:
                    raise Exception("JSON غير صالح")
                
                if not series:
                    raise Exception("مطلوب ملف واحد على الأقل")
                
                print(f"\n📥 جاري تحميل {len(series)} حلقات...")
                
                media_files = []
                for i, item in enumerate(series[:10], 1):
                    url = item.get('url', '').strip()
                    name = item.get('name', f'الحلقة_{i}').strip()
                    
                    if not url:
                        continue
                    
                    print(f"تحميل الحلقة {i}...", end='', flush=True)
                    try:
                        fpath, fsize = await download_file(url, tmp_dir, name, is_image=False)
                        vinfo = get_video_info(fpath)
                        
                        media_files.append({
                            'file': fpath,
                            'name': name,
                            'info': vinfo
                        })
                        print(f" ✅")
                    except Exception as e:
                        print(f" ❌ ({e})")
                
                if not media_files:
                    raise Exception("فشل تحميل جميع الملفات")
                
                chat_id = resolve_channel_id(channel)
                print(f"\n📤 جاري رفع {len(media_files)} حلقات...")
                
                # إعداد media group للمسلسل
                media_group = []
                
                for i, m in enumerate(media_files):
                    video_kwargs = {
                        'media': m['file'],
                        'supports_streaming': True,
                        'caption': caption if i == 0 else None
                    }
                    
                    if m['info']['thumb'] and os.path.exists(m['info']['thumb']):
                        video_kwargs['thumb'] = m['info']['thumb']
                    
                    media_group.append(InputMediaVideo(**video_kwargs))
                
                print("إرسال الألبوم...", end='', flush=True)
                await app.send_media_group(
                    chat_id=chat_id,
                    media=media_group
                )
                print(" ✅")
            
            print("\n" + "="*70)
            print("✅ تم بنجاح!")
            print("="*70)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ تم الإلغاء")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ خطأ: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
