
# سأقوم بإنشاء ملف السكربت المحسن
script_content = '''#!/usr/bin/env python3
import os
import sys
import asyncio
import tempfile
import mimetypes
import time
import subprocess
import json
from pathlib import Path
from urllib.parse import urlparse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    DocumentAttributeVideo,
    InputMediaUploadedPhoto,
    InputMediaUploadedDocument,
    InputSingleMedia,
    InputFile
)
from telethon.tl.functions.messages import SendMultiMediaRequest
from telethon.utils import get_input_peer
import requests
import ssl
import urllib3
from PIL import Image

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MAX_VIDEO_SIZE_MB = 1999.0

def sanitize_filename(filename):
    return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip().rstrip('.')

async def download_file(url, save_path, headers=None):
    """تحميل ملف مع إعادة محاولة"""
    try:
        verify_ssl = True
        if not headers:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*'
            }
        
        for attempt in range(2):
            try:
                response = requests.get(
                    url, stream=True, 
                    verify=verify_ssl if attempt == 0 else False, 
                    headers=headers,
                    timeout=1200, allow_redirects=True
                )
                response.raise_for_status()
                break
            except (requests.exceptions.SSLError, ssl.SSLError):
                if attempt == 0:
                    verify_ssl = False
                    continue
                raise
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        return os.path.getsize(save_path) / 1024 / 1024
    except Exception as e:
        if os.path.exists(save_path):
            os.remove(save_path)
        raise Exception(f"فشل التحميل: {str(e)}")

def get_video_info(video_path):
    """استخراج معلومات الفيديو"""
    try:
        cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,duration',
            '-show_entries', 'format=duration',
            '-of', 'json', video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            width = data.get('streams', [{}])[0].get('width', 1280)
            height = data.get('streams', [{}])[0].get('height', 720)
            duration = data.get('streams', [{}])[0].get('duration')
            if not duration:
                duration = data.get('format', {}).get('duration', 0)
            
            return {
                'width': width,
                'height': height,
                'duration': int(float(duration)) if duration else 0
            }
    except Exception as e:
        print(f"⚠️ تعذر استخراج معلومات الفيديو: {e}")
    
    return {'width': 1280, 'height': 720, 'duration': 0}

def prepare_thumbnail(image_path, output_path, max_size=320):
    """تحضير Thumbnail مناسب للفيديو (يجب أن يكون مربع تقريباً)"""
    try:
        img = Image.open(image_path)
        
        # تحويل لـ RGB لو لازم
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        
        # تغيير الحجم للـ thumbnail المربع (Telegram يفضل مربع للفيديو)
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # حفظ كـ JPG
        img.save(output_path, 'JPEG', quality=95)
        return True
    except Exception as e:
        print(f"⚠️ فشل تحضير Thumbnail: {e}")
        return False

async def main():
    print("="*70)
    print("🚀 سكريبت رفع الأفلام مع Album (صورة + فيديو + Thumbnail)")
    print("="*70)
    
    # التحقق من المتغيرات
    required = ['CHANNEL', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION_STRING']
    missing = [var for var in required if not os.getenv(var, '').strip()]
    if missing:
        raise Exception(f"المتغيرات المفقودة: {', '.join(missing)}")
    
    channel = os.getenv('CHANNEL', '').strip()
    caption = os.getenv('CAPTION', '').replace('\\\\n', '\\n').strip()
    img_url = os.getenv('IMAGE_URL', '').strip()
    vid_url = os.getenv('VIDEO_URL', '').strip()
    vid_name = os.getenv('VIDEO_NAME', 'movie').strip() or 'movie'
    
    if not img_url or not vid_url:
        raise Exception("مطلوب IMAGE_URL و VIDEO_URL")
    
    # إعداد العميل
    client = TelegramClient(
        StringSession(os.getenv('TELEGRAM_SESSION_STRING')),
        int(os.getenv('TELEGRAM_API_ID')),
        os.getenv('TELEGRAM_API_HASH'),
        flood_sleep_threshold=120
    )
    
    await client.start()
    me = await client.get_me()
    print(f"✅ تم تسجيل الدخول: {me.first_name}")
    
    # الحصول على الكيان
    try:
        if channel.startswith('@'):
            entity = await client.get_entity(channel)
        elif channel.startswith('-100'):
            entity = await client.get_entity(int(channel))
        else:
            entity = await client.get_entity(channel)
        print(f"📢 القناة: {entity.title if hasattr(entity, 'title') else entity.id}")
    except Exception as e:
        raise Exception(f"تعذر العثور على القناة: {e}")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            print("\\n🎬 جاري تحميل الملفات...")
            
            # 1. تحميل البوستر
            print("📥 تحميل البوستر...")
            img_ext = os.path.splitext(urlparse(img_url).path)[1].lower()
            if not img_ext or len(img_ext) > 5:
                img_ext = '.jpg'
            img_path = os.path.join(tmp_dir, f"poster{img_ext}")
            
            await download_file(img_url, img_path)
            
            # تحويل WebP لـ JPG لو لازم
            if img_path.lower().endswith('.webp'):
                try:
                    jpg_path = img_path.replace('.webp', '.jpg')
                    img = Image.open(img_path).convert('RGB')
                    img.save(jpg_path, 'JPEG', quality=95)
                    img_path = jpg_path
                    print("🔄 تم تحويل WebP إلى JPG")
                except:
                    pass
            
            # 2. تحميل الفيديو
            print(f"📥 تحميل الفيديو ({vid_name})...")
            vid_name_clean = sanitize_filename(vid_name)
            vid_path = os.path.join(tmp_dir, f"{vid_name_clean}.mp4")
            
            vid_size = await download_file(vid_url, vid_path)
            print(f"📦 حجم الفيديو: {vid_size:.2f} MB")
            
            if vid_size > MAX_VIDEO_SIZE_MB:
                raise Exception(f"حجم الفيديو كبير جداً ({vid_size:.1f}MB)")
            
            # 3. استخراج معلومات الفيديو
            print("🔍 استخراج معلومات الفيديو...")
            video_info = get_video_info(vid_path)
            print(f"   📐 الدقة: {video_info['width']}x{video_info['height']}")
            print(f"   ⏱️ المدة: {video_info['duration']} ثانية")
            
            # 4. تحضير Thumbnail للفيديو (من البوستر)
            print("🖼️ تحضير Thumbnail للفيديو من البوستر...")
            thumb_path = os.path.join(tmp_dir, "video_thumb.jpg")
            
            if not prepare_thumbnail(img_path, thumb_path):
                # لو فشل، نحاول نعمل resize بسيط
                try:
                    img = Image.open(img_path).convert('RGB')
                    img = img.resize((320, 320), Image.Resampling.LANCZOS)
                    img.save(thumb_path, 'JPEG', quality=90)
                except Exception as e2:
                    print(f"⚠️ فشل إنشاء Thumbnail: {e2}")
                    thumb_path = None
            
            # 5. رفع Album (الطريقة الصحيحة)
            print("\\n📤 جاري إنشاء Album (صورة + فيديو)...")
            
            # رفع الملفات أولاً
            print("⏳ رفع البوستر...")
            uploaded_photo = await client.upload_file(img_path)
            
            print("⏳ رفع الفيديو...")
            uploaded_video = await client.upload_file(vid_path)
            
            # رفع Thumbnail (مطلوب ليكون InputFile)
            uploaded_thumb = None
            if thumb_path and os.path.exists(thumb_path):
                print("⏳ رفع Thumbnail...")
                uploaded_thumb = await client.upload_file(thumb_path)
            
            # إنشاء InputMedia للصورة (Photo)
            photo_media = InputMediaUploadedPhoto(uploaded_photo)
            
            # إنشاء InputMedia للفيديو مع Thumbnail
            video_attributes = DocumentAttributeVideo(
                duration=video_info['duration'],
                w=video_info['width'],
                h=video_info['height'],
                supports_streaming=True
            )
            
            video_media = InputMediaUploadedDocument(
                file=uploaded_video,
                mime_type='video/mp4',
                attributes=[video_attributes],
                thumb=uploaded_thumb,  # ✅ هنا نضع البوستر كـ Thumbnail للفيديو
                force_file=False
            )
            
            # إنشاء قائمة الـ Album
            media_list = [
                InputSingleMedia(
                    media=photo_media,
                    message=caption,  # الكابشن على الصورة
                    entities=[]
                ),
                InputSingleMedia(
                    media=video_media,
                    message='',  # الفيديو بدون كابشن (الكابشن على الصورة كفاية)
                    entities=[]
                )
            ]
            
            # إرسال Album
            print("📤 إرسال Album...")
            input_peer = get_input_peer(entity)
            
            await client(SendMultiMediaRequest(
                peer=input_peer,
                multi_media=media_list
            ))
            
            print("\\n" + "="*70)
            print("✅ تم الرفع بنجاح!")
            print("🎉 الشكل النهائي:")
            print("   📸 صورة البوستر (ظاهرة كصورة عالية الجودة)")
            print("   🎬 الفيديو (مع البوستر كـ Thumbnail/غلاف)")
            print("="*70)
            
        finally:
            await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\\n⚠️ تم الإلغاء")
        sys.exit(130)
    except Exception as e:
        print(f"\\n❌ خطأ: {str(e)}", file=sys.stderr)
        sys.exit(1)
'''

# حفظ الملف
with open('/mnt/kimi/output/upload_fixed.py', 'w', encoding='utf-8') as f:
    f.write(script_content)

print("✅ تم إنشاء السكربت المحسن")
print("📁 المسار: upload_fixed.py")
