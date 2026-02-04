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
from telethon.tl.types import DocumentAttributeVideo, InputMediaUploadedPhoto, InputMediaUploadedDocument
from telethon.tl.functions.messages import SendMultiMediaRequest
import requests
import ssl
import urllib3
from PIL import Image

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def sanitize_filename(filename):
    return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip().rstrip('.')

async def download_file(url, save_path):
    """تحميل ملف مع طباعة حالة واضحة"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        for attempt in range(2):
            try:
                response = requests.get(url, stream=True, verify=(attempt == 0), headers=headers, timeout=1200)
                response.raise_for_status()
                break
            except (requests.exceptions.SSLError, ssl.SSLError):
                if attempt == 0:
                    print("⚠️ مشكلة SSL، إعادة المحاولة...")
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

def prepare_thumbnail_for_video(image_path, output_path):
    """
    تحضير Thumbnail للفيديو - نفس أبعاد الصورة الأصلية
    """
    try:
        print("🔧 تحضير Thumbnail للفيديو...", end=" ")
        
        with Image.open(image_path) as img:
            # نحافظ على نفس الأبعاد بالظبط
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (0, 0, 0))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                if img.mode in ('RGBA', 'LA'):
                    background.paste(img, mask=img.split()[-1])
                    img = background
                else:
                    img = img.convert('RGB')
            
            # نحفظ بنفس الأبعاد
            img.save(output_path, 'JPEG', quality=95, optimize=True)
            
            size_kb = os.path.getsize(output_path) / 1024
            print(f"✅ ({img.size[0]}x{img.size[1]}, {size_kb:.1f} KB)")
            return True
            
    except Exception as e:
        print(f"❌ فشل: {e}")
        return False

async def main():
    print("="*70)
    print("🚀 سكريبت رفع Album (صورة + فيديو) في نفس البوست")
    print("="*70)
    
    # التحقق من المتغيرات
    required = ['CHANNEL', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION_STRING']
    missing = [var for var in required if not os.getenv(var, '').strip()]
    if missing:
        raise Exception(f"المتغيرات المفقودة: {', '.join(missing)}")
    
    channel = os.getenv('CHANNEL', '').strip()
    caption = os.getenv('CAPTION', '').replace('\\\\n', '\n').strip()
    img_url = os.getenv('IMAGE_URL', '').strip()
    vid_url = os.getenv('VIDEO_URL', '').strip()
    vid_name = os.getenv('VIDEO_NAME', 'movie').strip() or 'movie'
    
    if not img_url or not vid_url:
        raise Exception("مطلوب IMAGE_URL و VIDEO_URL")
    
    print(f"📝 الكابشن: {caption[:50]}...")
    print(f"🎬 اسم الفيديو: {vid_name}")
    
    # إعداد العميل
    print("\n🔌 جاري الاتصال بتيليجرام...", end=" ")
    client = TelegramClient(
        StringSession(os.getenv('TELEGRAM_SESSION_STRING')),
        int(os.getenv('TELEGRAM_API_ID')),
        os.getenv('TELEGRAM_API_HASH')
    )
    
    await client.start()
    me = await client.get_me()
    print(f"✅ متصل كـ: {me.first_name}")
    
    # الحصول على الكيان
    try:
        if channel.startswith('@'):
            entity = await client.get_entity(channel)
        elif channel.startswith('-100'):
            entity = await client.get_entity(int(channel))
        else:
            entity = await client.get_entity(channel)
        print(f"📢 القناة المستهدفة: {entity.title if hasattr(entity, 'title') else channel}")
    except Exception as e:
        raise Exception(f"تعذر الوصول للقناة: {e}")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            # 1. تحميل البوستر
            print("\n" + "-"*70)
            print("📥 [1/3] جاري تحميل البوستر...")
            print("-"*70)
            
            img_ext = os.path.splitext(urlparse(img_url).path)[1].lower()
            if not img_ext or len(img_ext) > 5:
                img_ext = '.jpg'
            img_path = os.path.join(tmp_dir, f"poster{img_ext}")
            
            img_size = await download_file(img_url, img_path)
            
            # التحقق من أبعاد الصورة
            with Image.open(img_path) as img:
                orig_width, orig_height = img.size
                aspect_ratio = orig_height / orig_width
                print(f"✅ تم تحميل البوستر: {img_size:.2f} MB ({orig_width}x{orig_height}, ratio: {aspect_ratio:.2f})")
            
            # تحويل WebP لـ JPG لو لازم
            if img_path.lower().endswith('.webp'):
                try:
                    print("🔄 تحويل WebP إلى JPG...", end=" ")
                    jpg_path = img_path.replace('.webp', '.jpg')
                    with Image.open(img_path) as img:
                        if img.mode in ('RGBA', 'LA', 'P'):
                            background = Image.new('RGB', img.size, (0, 0, 0))
                            if img.mode == 'P':
                                img = img.convert('RGBA')
                            if img.mode in ('RGBA', 'LA'):
                                background.paste(img, mask=img.split()[-1])
                                img = background
                            else:
                                img = img.convert('RGB')
                        img.save(jpg_path, 'JPEG', quality=95, optimize=True)
                    img_path = jpg_path
                    print("✅")
                except Exception as e:
                    print(f"⚠️ فشل التحويل: {e}")
            
            # 2. تحميل الفيديو
            print("\n" + "-"*70)
            print(f"📥 [2/3] جاري تحميل الفيديو ({vid_name})...")
            print("-"*70)
            
            vid_name_clean = sanitize_filename(vid_name)
            vid_path = os.path.join(tmp_dir, f"{vid_name_clean}.mp4")
            
            vid_size = await download_file(vid_url, vid_path)
            print(f"✅ تم تحميل الفيديو: {vid_size:.2f} MB")
            
            # 3. معلومات الفيديو
            print("\n" + "-"*70)
            print("🔍 [3/3] جاري استخراج معلومات الفيديو...")
            print("-"*70)
            
            video_info = get_video_info(vid_path)
            print(f"📐 دقة الفيديو: {video_info['width']}x{video_info['height']}")
            print(f"⏱️  مدة الفيديو: {video_info['duration']} ثانية")
            
            # تحضير Thumbnail للفيديو بنفس أبعاد الصورة
            thumb_path = os.path.join(tmp_dir, "video_thumb.jpg")
            if not prepare_thumbnail_for_video(img_path, thumb_path):
                thumb_path = img_path
            
            # 4. رفع Album (صورة + فيديو في نفس البوست)
            print("\n" + "-"*70)
            print("📤 رفع Album (صورة على الشمال، فيديو على اليمين)...")
            print("-"*70)
            
            # رفع الصورة أولاً (عشان نجيب الـ file_id)
            print("⏳ جاري رفع الصورة...")
            uploaded_photo = await client.upload_file(img_path)
            
            # رفع الفيديو مع الـ thumbnail
            print("⏳ جاري رفع الفيديو...")
            
            # نجهز الـ attributes
            video_attributes = DocumentAttributeVideo(
                duration=video_info['duration'],
                w=video_info['width'],
                h=video_info['height'],
                supports_streaming=True
            )
            
            # رفع الفيديو
            uploaded_video = await client.upload_file(
                vid_path,
                progress_callback=lambda uploaded, total: print(f"   📥 {uploaded/1024/1024:.1f}/{total/1024/1024:.1f} MB", end="\r")
            )
            
            print("\n⏳ جاري إرسال Album...")
            
            # إنشاء الـ Album باستخدام send_file مع قائمة
            # الطريقة الصحيحة لعمل Album في Telethon
            album_messages = await client.send_file(
                entity,
                [img_path, vid_path],  # قائمة بالملفات
                caption=caption,  # الكابشن على الصورة الأولى
                attributes=[None, [video_attributes]],  # attributes للفيديو فقط
                force_document=False
            )
            
            print(f"✅ تم رفع Album بنجاح!")
            print(f"📸 عدد الرسائل: {len(album_messages) if isinstance(album_messages, list) else 1}")
            
            print("\n" + "="*70)
            print("🎉 تم رفع Album بنجاح!")
            print("📸 الصورة: على الشمال (بالأبعاد الأصلية)")
            print("🎬 الفيديو: على اليمين (مع نفس الـ thumbnail)")
            print("="*70)
            
        finally:
            await client.disconnect()
            print("\n🔌 تم قطع الاتصال بتيليجرام")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ تم إيقاف السكريبت يدوياً")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ خطأ: {str(e)}", file=sys.stderr)
        sys.exit(1)
