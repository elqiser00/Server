#!/usr/bin/env python3
import os
import sys
import asyncio
import tempfile
import subprocess
import json
import traceback
from pathlib import Path
from urllib.parse import urlparse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeVideo
from PIL import Image
import requests
import ssl
import urllib3

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

def convert_image_to_jpg(image_path, output_path):
    """تحويل أي صورة لـ JPEG"""
    try:
        print("🔄 تحويل الصورة لـ JPEG...", end=" ")
        with Image.open(image_path) as img:
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (0, 0, 0))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                if img.mode in ('RGBA', 'LA'):
                    background.paste(img, mask=img.split()[-1])
                    img = background
                else:
                    img = img.convert('RGB')
            
            img.save(output_path, 'JPEG', quality=95, optimize=True)
        
        size_kb = os.path.getsize(output_path) / 1024
        print(f"✅ ({size_kb:.1f} KB)")
        return True
    except Exception as e:
        print(f"❌ فشل: {e}")
        return False

def extract_video_thumbnail(video_path, output_path, time_sec=5):
    """استخراج frame من الفيديو كـ thumbnail"""
    try:
        print(f"🎬 استخراج thumbnail من الفيديو...", end=" ")
        
        cmd = [
            'ffmpeg', '-ss', str(time_sec), '-i', video_path,
            '-vframes', '1', '-q:v', '2',
            '-y', output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        
        if result.returncode == 0 and os.path.exists(output_path):
            size_kb = os.path.getsize(output_path) / 1024
            print(f"✅ ({size_kb:.1f} KB)")
            return True
        else:
            print(f"⚠️ ffmpeg فشل")
            return False
            
    except Exception as e:
        print(f"❌ فشل: {e}")
        return False

async def main():
    print("="*70)
    print("🚀 سكريبت رفع Album - صورة على الشمال، فيديو على اليمين")
    print("="*70)
    
    try:
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
        
        print("\n🔌 جاري الاتصال بتيليجرام...", end=" ")
        client = TelegramClient(
            StringSession(os.getenv('TELEGRAM_SESSION_STRING')),
            int(os.getenv('TELEGRAM_API_ID')),
            os.getenv('TELEGRAM_API_HASH')
        )
        
        await client.start()
        me = await client.get_me()
        print(f"✅ متصل كـ: {me.first_name}")
        
        try:
            if channel.startswith('@'):
                entity = await client.get_entity(channel)
            elif channel.startswith('-100'):
                entity = await client.get_entity(int(channel))
            elif channel.startswith('https://t.me/+'):
                invite_hash = channel.split('+')[-1]
                try:
                    entity = await client.get_entity(channel)
                except:
                    from telethon.tl.functions.messages import ImportChatInviteRequest
                    updates = await client(ImportChatInviteRequest(invite_hash))
                    entity = updates.chats[0]
            else:
                entity = await client.get_entity(channel)
            print(f"📢 القناة المستهدفة: {entity.title if hasattr(entity, 'title') else channel}")
        except Exception as e:
            raise Exception(f"تعذر الوصول للقناة: {e}")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. تحميل البوستر
            print("\n" + "-"*70)
            print("📥 [1/4] جاري تحميل البوستر...")
            print("-"*70)
            
            img_ext = os.path.splitext(urlparse(img_url).path)[1].lower()
            if not img_ext or len(img_ext) > 5:
                img_ext = '.jpg'
            
            raw_img_path = os.path.join(tmp_dir, f"raw_poster{img_ext}")
            await download_file(img_url, raw_img_path)
            
            img_path = os.path.join(tmp_dir, "poster.jpg")
            if not convert_image_to_jpg(raw_img_path, img_path):
                img_path = raw_img_path
            
            print(f"✅ الصورة جاهزة")
            
            # 2. تحميل الفيديو
            print("\n" + "-"*70)
            print(f"📥 [2/4] جاري تحميل الفيديو...")
            print("-"*70)
            
            vid_name_clean = sanitize_filename(vid_name)
            vid_path = os.path.join(tmp_dir, f"{vid_name_clean}.mp4")
            
            vid_size = await download_file(vid_url, vid_path)
            print(f"✅ تم تحميل الفيديو: {vid_size:.2f} MB")
            
            # 3. معلومات الفيديو وthumbnail
            print("\n" + "-"*70)
            print("🔍 [3/4] جاري استخراج معلومات الفيديو...")
            print("-"*70)
            
            video_info = get_video_info(vid_path)
            print(f"📐 دقة الفيديو: {video_info['width']}x{video_info['height']}")
            print(f"⏱️  مدة الفيديو: {video_info['duration']} ثانية")
            
            # استخراج thumbnail من الفيديو
            video_thumb_path = os.path.join(tmp_dir, "video_thumb.jpg")
            if not extract_video_thumbnail(vid_path, video_thumb_path, time_sec=10):
                print("⚠️ استخدام الصورة كـ thumbnail")
                video_thumb_path = img_path
            
            # 4. رفع Album
            print("\n" + "-"*70)
            print("📤 [4/4] رفع Album...")
            print("-"*70)
            
            # إعداد attributes للفيديو
            video_attributes = DocumentAttributeVideo(
                duration=video_info['duration'],
                w=video_info['width'],
                h=video_info['height'],
                supports_streaming=True
            )
            
            print("⏳ جاري رفع Album...")
            
            # رفع الصورة أولاً (Album)
            print("   📤 رفع الصورة...")
            photo_msg = await client.send_file(
                entity,
                img_path,
                caption=caption,  # الكابشن على الصورة
                force_document=False
            )
            print(f"   ✅ تم رفع الصورة (ID: {photo_msg.id})")
            
            # رفع الفيديو كـ رد على الصورة (Album)
            print("   📤 رفع الفيديو...")
            video_msg = await client.send_file(
                entity,
                vid_path,
                reply_to=photo_msg.id,  # رد على الصورة = Album
                attributes=[video_attributes],
                thumb=video_thumb_path,
                supports_streaming=True,
                force_document=False
            )
            print(f"   ✅ تم رفع الفيديو (ID: {video_msg.id})")
            
            print("\n" + "="*70)
            print("🎉 تم رفع Album بنجاح!")
            print("📸 الصورة: على الشمال (أو فوق لو كبيرة)")
            print("🎬 الفيديو: على اليمين (أو تحت لو الصورة كبيرة)")
            print("="*70)
            
    except Exception as e:
        print(f"\n\n❌ خطأ: {str(e)}")
        print("\n📋 تفاصيل الخطأ:")
        traceback.print_exc()
        sys.exit(1)
    finally:
        try:
            await client.disconnect()
            print("\n🔌 تم قطع الاتصال بتيليجرام")
        except:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ تم إيقاف السكريبت يدوياً")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ خطأ عام: {str(e)}")
        traceback.print_exc()
        sys.exit(1)
