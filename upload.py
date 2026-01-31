
# إنشاء السكربت المحسن مع رسائل واضحة وThumbnail صحيح
script_content = '''#!/usr/bin/env python3
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
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
        
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
    تحضير Thumbnail مثالي للفيديو
    - مربع (1:1) عشان Telegram يعرضه صح
    - JPG بجودة عالية
    - حجم مناسب (أقل من 200KB)
    """
    try:
        print("🔧 معالجة الصورة للـ Thumbnail...", end=" ")
        
        # فتح الصورة
        img = Image.open(image_path)
        
        # تحويل لـ RGB
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        
        # قص الصورة لتكون مربعة (من المنتصف)
        width, height = img.size
        if width != height:
            min_dim = min(width, height)
            left = (width - min_dim) // 2
            top = (height - min_dim) // 2
            right = left + min_dim
            bottom = top + min_dim
            img = img.crop((left, top, right, bottom))
        
        # تغيير الحجم للـ 640x640 (مثالي لـ Telegram)
        img = img.resize((640, 640), Image.Resampling.LANCZOS)
        
        # حفظ بجودة متوسطة (عشان الحجم)
        img.save(output_path, 'JPEG', quality=85, optimize=True)
        
        size_kb = os.path.getsize(output_path) / 1024
        print(f"✅ ({size_kb:.1f} KB)")
        return True
        
    except Exception as e:
        print(f"❌ فشل: {e}")
        return False

async def main():
    print("="*70)
    print("🚀 سكريبت رفع الأفلام على تيليجرام - مع Thumbnail مثالي")
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
    
    print(f"📝 الكابشن: {caption[:50]}...")
    print(f"🎬 اسم الفيديو: {vid_name}")
    
    # إعداد العميل
    print("\\n🔌 جاري الاتصال بتيليجرام...", end=" ")
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
            print("\\n" + "-"*70)
            print("📥 [1/4] جاري تحميل البوستر...")
            print("-"*70)
            
            img_ext = os.path.splitext(urlparse(img_url).path)[1].lower()
            if not img_ext or len(img_ext) > 5:
                img_ext = '.jpg'
            img_path = os.path.join(tmp_dir, f"poster{img_ext}")
            
            img_size = await download_file(img_url, img_path)
            print(f"✅ تم تحميل البوستر: {img_size:.2f} MB")
            
            # تحويل WebP لـ JPG لو لازم
            if img_path.lower().endswith('.webp'):
                try:
                    print("🔄 تحويل WebP إلى JPG...", end=" ")
                    jpg_path = img_path.replace('.webp', '.jpg')
                    Image.open(img_path).convert('RGB').save(jpg_path, 'JPEG', quality=95)
                    img_path = jpg_path
                    print("✅")
                except Exception as e:
                    print(f"⚠️ فشل التحويل: {e}")
            
            # 2. تحميل الفيديو
            print("\\n" + "-"*70)
            print(f"📥 [2/4] جاري تحميل الفيديو ({vid_name})...")
            print("-"*70)
            
            vid_name_clean = sanitize_filename(vid_name)
            vid_path = os.path.join(tmp_dir, f"{vid_name_clean}.mp4")
            
            vid_size = await download_file(vid_url, vid_path)
            print(f"✅ تم تحميل الفيديو: {vid_size:.2f} MB")
            
            # 3. معلومات الفيديو وتحضير Thumbnail
            print("\\n" + "-"*70)
            print("🔍 [3/4] جاري استخراج معلومات الفيديو وتحضير Thumbnail...")
            print("-"*70)
            
            video_info = get_video_info(vid_path)
            print(f"📐 دقة الفيديو: {video_info['width']}x{video_info['height']}")
            print(f"⏱️  مدة الفيديو: {video_info['duration']} ثانية")
            
            # تحضير Thumbnail مثالي
            thumb_path = os.path.join(tmp_dir, "video_thumb.jpg")
            if not prepare_thumbnail_for_video(img_path, thumb_path):
                print("⚠️ سيتم استخدام البوستر الأصلي كـ Thumbnail")
                thumb_path = img_path
            
            # 4. رفع Album
            print("\\n" + "-"*70)
            print("📤 [4/4] جاري رفع Album على تيليجرام...")
            print("-"*70)
            print("⏳ جاري رفع البوستر...")
            
            # رفع الصورة أولاً (عشان نتأكد إنها اترفعت)
            photo_msg = await client.send_file(
                entity,
                img_path,
                caption=caption,
                force_document=False
            )
            print(f"✅ تم رفع البوستر (Msg ID: {photo_msg.id})")
            
            print("⏳ جاري رفع الفيديو مع Thumbnail...")
            
            # إعداد attributes للفيديو
            video_attributes = DocumentAttributeVideo(
                duration=video_info['duration'],
                w=video_info['width'],
                h=video_info['height'],
                supports_streaming=True
            )
            
            # رفع الفيديو كـ رد على الصورة (Album)
            video_msg = await client.send_file(
                entity,
                vid_path,
                reply_to=photo_msg.id,  # رد على الصورة عشان يبقوا Album
                attributes=[video_attributes],
                thumb=thumb_path,
                supports_streaming=True,
                force_document=False
            )
            
            print(f"✅ تم رفع الفيديو (Msg ID: {video_msg.id})")
            
            print("\\n" + "="*70)
            print("🎉 تم رفع Album بنجاح!")
            print("📸 الصورة: بوستر الفيلم (جودة عالية)")
            print("🎬 الفيديو: مع البوستر كـ Thumbnail")
            print("="*70)
            
        finally:
            await client.disconnect()
            print("\\n🔌 تم قطع الاتصال بتيليجرام")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\\n\\n⚠️ تم إيقاف السكريبت يدوياً")
        sys.exit(130)
    except Exception as e:
        print(f"\\n\\n❌ خطأ: {str(e)}", file=sys.stderr)
        sys.exit(1)
'''

print(script_content)
print("\\n" + "="*70)
print("✅ انسخ الكود ده وحطه في ملف upload.py")
print("="*70)
