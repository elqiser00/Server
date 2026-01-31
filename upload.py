#!/usr/bin/env python3
import os
import sys
import asyncio
import tempfile
import subprocess
import json
from pathlib import Path
from urllib.parse import urlparse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeVideo
import requests
import ssl
import urllib3
from PIL import Image

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def sanitize_filename(filename):
    return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip().rstrip('.')

async def download_file(url, save_path):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        for attempt in range(2):
            try:
                response = requests.get(url, stream=True, verify=(attempt == 0), headers=headers, timeout=1200)
                response.raise_for_status()
                break
            except (requests.exceptions.SSLError, ssl.SSLError):
                if attempt == 0:
                    continue
                raise
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        size_mb = os.path.getsize(save_path) / 1024 / 1024
        return size_mb
    except Exception as e:
        if os.path.exists(save_path):
            os.remove(save_path)
        raise Exception(f"فشل التحميل: {str(e)}")

def get_video_info(video_path):
    try:
        cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-show_entries', 'format=duration', '-of', 'json', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            width = data.get('streams', [{}])[0].get('width', 1280)
            height = data.get('streams', [{}])[0].get('height', 720)
            duration = data.get('streams', [{}])[0].get('duration')
            if not duration:
                duration = data.get('format', {}).get('duration', 0)
            return {'width': width, 'height': height, 'duration': int(float(duration)) if duration else 0}
    except:
        pass
    return {'width': 1280, 'height': 720, 'duration': 0}

def prepare_thumbnail(image_path, output_path):
    try:
        img = Image.open(image_path)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        img.thumbnail((320, 320), Image.Resampling.LANCZOS)
        img.save(output_path, 'JPEG', quality=90)
        return True
    except:
        return False

async def main():
    print("="*60)
    print("🚀 سكريبت رفع الأفلام على تيليجرام")
    print("="*60)
    
    required = ['CHANNEL', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION_STRING']
    missing = [var for var in required if not os.getenv(var, '').strip()]
    if missing:
        raise Exception(f"المتغيرات المفقودة: {', '.join(missing)}")
    
    channel = os.getenv('CHANNEL', '').strip()
    caption = os.getenv('CAPTION', '').replace('\\n', '\n').strip()
    img_url = os.getenv('IMAGE_URL', '').strip()
    vid_url = os.getenv('VIDEO_URL', '').strip()
    vid_name = os.getenv('VIDEO_NAME', 'movie').strip() or 'movie'
    
    if not img_url or not vid_url:
        raise Exception("مطلوب IMAGE_URL و VIDEO_URL")
    
    client = TelegramClient(
        StringSession(os.getenv('TELEGRAM_SESSION_STRING')),
        int(os.getenv('TELEGRAM_API_ID')),
        os.getenv('TELEGRAM_API_HASH')
    )
    
    await client.start()
    me = await client.get_me()
    print(f"✅ تم تسجيل الدخول: {me.first_name}")
    
    try:
        if channel.startswith('@'):
            entity = await client.get_entity(channel)
        elif channel.startswith('-100'):
            entity = await client.get_entity(int(channel))
        else:
            entity = await client.get_entity(channel)
        print(f"📢 القناة: {entity.title if hasattr(entity, 'title') else channel}")
    except Exception as e:
        raise Exception(f"تعذر الوصول للقناة: {e}")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            print("\n📥 جاري تحميل البوستر...", end=" ")
            img_ext = os.path.splitext(urlparse(img_url).path)[1].lower()
            if not img_ext or len(img_ext) > 5:
                img_ext = '.jpg'
            img_path = os.path.join(tmp_dir, f"poster{img_ext}")
            
            img_size = await download_file(img_url, img_path)
            
            if img_path.lower().endswith('.webp'):
                try:
                    jpg_path = img_path.replace('.webp', '.jpg')
                    Image.open(img_path).convert('RGB').save(jpg_path, 'JPEG', quality=95)
                    img_path = jpg_path
                except:
                    pass
            
            print(f"✅ تم تحميل الصورة ({img_size:.1f} MB)")
            
            print("📥 جاري تحميل الفيديو...", end=" ")
            vid_name_clean = sanitize_filename(vid_name)
            vid_path = os.path.join(tmp_dir, f"{vid_name_clean}.mp4")
            
            vid_size = await download_file(vid_url, vid_path)
            print(f"✅ تم تحميل الفيديو ({vid_size:.1f} MB)")
            
            print("🔍 جاري استخراج معلومات الفيديو...", end=" ")
            video_info = get_video_info(vid_path)
            print(f"✅ ({video_info['width']}x{video_info['height']}, {video_info['duration']}s)")
            
            print("🖼️ جاري تحضير Thumbnail...", end=" ")
            thumb_path = os.path.join(tmp_dir, "thumb.jpg")
            if not prepare_thumbnail(img_path, thumb_path):
                thumb_path = img_path
            print("✅")
            
            print("\n📤 جاري رفع Album...")
            
            video_attributes = DocumentAttributeVideo(
                duration=video_info['duration'],
                w=video_info['width'],
                h=video_info['height'],
                supports_streaming=True
            )
            
            await client.send_file(
                entity,
                file=[img_path, vid_path],
                caption=caption,
                force_document=False,
                supports_streaming=True,
                attributes={1: [video_attributes]},
                thumb=thumb_path
            )
            
            print("\n" + "="*60)
            print("✅ تم رفع Album بنجاح!")
            print("="*60)
            
        finally:
            await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ تم الإلغاء")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ خطأ: {str(e)}", file=sys.stderr)
        sys.exit(1)
