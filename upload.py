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
    InputMediaUploadedPhoto,
    InputMediaUploadedDocument,
    DocumentAttributeVideo,
    DocumentAttributeFilename
)
import requests
import ssl
import urllib3
from PIL import Image

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MAX_VIDEO_SIZE_MB = 1999.0

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
        # Thumbnail
        thumb_path = video_path + "_thumb.jpg"
        subprocess.run([
            'ffmpeg', '-i', video_path, '-ss', '00:00:03',
            '-vframes', '1', '-q:v', '2', '-y', thumb_path
        ], capture_output=True, timeout=30)
        
        # معلومات
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,duration',
            '-show_entries', 'format=duration',
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
            'duration': duration, 'width': width, 'height': height
        }
    except:
        return {'thumb': None, 'duration': 0, 'width': 1280, 'height': 720}

async def resolve_channel(client, channel_input):
    channel_input = channel_input.strip()
    for prefix in ['https://', 'http://', 't.me/', 'telegram.me/']:
        if channel_input.startswith(prefix):
            channel_input = channel_input[len(prefix):]
    
    if '+' in channel_input:
        parts = channel_input.split('+')
        if len(parts) > 1:
            invite_hash = parts[1].split('?')[0].split('/')[0].strip()
            try:
                return await client.get_entity(f"https://t.me/joinchat/{invite_hash}")
            except:
                pass
    
    return await client.get_entity(channel_input)

async def main():
    print("="*70)
    print("🚀 سكريبت رفع Album (صورة + فيديو) - نفس البوست")
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
    
    client = TelegramClient(
        StringSession(os.getenv('TELEGRAM_SESSION_STRING')),
        int(os.getenv('TELEGRAM_API_ID')),
        os.getenv('TELEGRAM_API_HASH'),
        flood_sleep_threshold=120
    )
    await client.start()
    me = await client.get_me()
    print(f"✅ تم تسجيل الدخول: {me.first_name}")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
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
                
                # معلومات الفيديو
                print("تحليل الفيديو...", end='', flush=True)
                vinfo = get_video_info(vid_path)
                print(f" ✅ ({vinfo['duration']}s)")
                
                print(f"\n📤 جاري رفع Album...")
                entity = await resolve_channel(client, channel)
                
                # ✅ الحل: نجهز الملفات كـ قائمة ونرفعهم album=True
                # الصورة أولاً، الفيديو تاني
                
                # نجهز الصورة كـ InputMediaUploadedPhoto
                # والفيديو كـ InputMediaUploadedDocument
                
                from telethon.utils import get_input_photo, get_input_document
                
                # ✅ الطريقة الصحيحة لـ Album
                # نستخدم send_file مع قائمة ملفات
                
                files = [
                    img_path,  # الصورة الأولى (البوستر الكبير)
                    vid_path   # الفيديو تحتها
                ]
                
                # ✅ نرفع Album حقيقي
                await client.send_file(
                    entity,
                    files,
                    caption=caption,
                    parse_mode='html',
                    album=True,              # ✅ Album = Grouped
                    supports_streaming=True,  # ✅ الفيديو يشتغل
                    force_document=False,     # ✅ فيديو عادي مش ملف
                    # للفيديو بس: نضيف attributes
                    attributes=[              # ✅ معلومات الفيديو
                        DocumentAttributeVideo(
                            duration=vinfo['duration'],
                            w=vinfo['width'],
                            h=vinfo['height'],
                            supports_streaming=True
                        ),
                        DocumentAttributeFilename(file_name=f"{vid_name}.mp4")
                    ]
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
                
                print(f"\n📤 جاري رفع {len(media_files)} حلقات...")
                entity = await resolve_channel(client, channel)
                
                # رفع المسلسل كـ Album
                files = [m['file'] for m in media_files]
                
                await client.send_file(
                    entity,
                    files,
                    caption=caption,
                    parse_mode='html',
                    album=True,
                    supports_streaming=True,
                    force_document=False
                )
                
                print(" ✅ تم الرفع!")
            
            print("\n" + "="*70)
            print("✅ تم بنجاح!")
            print("="*70)
            
        finally:
            await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ تم الإلغاء")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ خطأ: {e}")
        sys.exit(1)
