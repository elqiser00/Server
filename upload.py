#!/usr/bin/env python3
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
from telethon.tl.types import DocumentAttributeVideo
import requests
import ssl
import urllib3
from PIL import Image

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MAX_VIDEO_SIZE_MB = 1999.0

def sanitize_filename(filename):
    return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip().rstrip('.')

def print_progress(current, total, prefix=''):
    """طباعة شريط التقدم"""
    percent = 100 * (current / total) if total > 0 else 0
    filled_len = int(50 * current // total) if total > 0 else 50
    bar = '█' * filled_len + '-' * (50 - filled_len)
    print(f'\r{prefix} |{bar}| {percent:.1f}%', end='', flush=True)
    if current == total:
        print()

async def download_file_with_progress(url, save_path, headers=None, prefix=''):
    """تحميل الملف مع مؤشر تقدم"""
    try:
        verify_ssl = True
        if not headers:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*'
            }
        
        # محاولة التحميل مع SSL أولاً، ثم بدونه إذا فشل
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
                    print(f"\n⚠️ خطأ SSL، إعادة المحاولة بدون تحقق...")
                    continue
                raise
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        print_progress(downloaded, total_size, prefix)
        
        return downloaded / 1024 / 1024  # حجم بالميجا
    except Exception as e:
        if os.path.exists(save_path):
            os.remove(save_path)
        raise Exception(f"فشل التحميل: {str(e)}")

def get_video_info(video_path):
    """استخراج معلومات الفيديو باستخدام ffprobe"""
    try:
        cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,duration,codec_name',
            '-show_entries', 'format=duration,size',
            '-of', 'json', video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            stream = data.get('streams', [{}])[0]
            format_info = data.get('format', {})
            
            return {
                'width': stream.get('width', 1280),
                'height': stream.get('height', 720),
                'duration': int(float(stream.get('duration') or format_info.get('duration', 0))),
                'size_mb': int(format_info.get('size', 0)) / 1024 / 1024
            }
    except Exception as e:
        print(f"⚠️ تعذر استخراج معلومات الفيديو: {e}")
    
    return {'width': 1280, 'height': 720, 'duration': 0, 'size_mb': 0}

def extract_thumbnail(video_path, output_path, time_sec=1):
    """استخراج صورة مصغرة من الفيديو"""
    try:
        # التأكد من عدم تجاوز مدة الفيديو
        info = get_video_info(video_path)
        if info['duration'] > 0 and time_sec >= info['duration']:
            time_sec = max(1, info['duration'] // 2)
        
        cmd = [
            'ffmpeg', '-y', '-ss', str(time_sec), '-i', video_path,
            '-vframes', '1', '-q:v', '2',
            '-vf', 'scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2:black',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"⚠️ فشل استخراج Thumbnail: {e}")
        return False

async def upload_with_progress(client, entity, file_path, caption='', thumb=None, is_video=False, video_info=None):
    """رفع الملف مع مؤشر تقدم"""
    def progress_callback(current, total):
        print_progress(current, total, '📤 الرفع')
    
    try:
        if is_video and video_info:
            attributes = [DocumentAttributeVideo(
                duration=video_info['duration'],
                w=video_info['width'],
                h=video_info['height'],
                supports_streaming=True
            )]
            
            return await client.send_file(
                entity,
                file_path,
                caption=caption,
                attributes=attributes,
                thumb=thumb,
                supports_streaming=True,
                progress_callback=progress_callback
            )
        else:
            return await client.send_file(
                entity,
                file_path,
                caption=caption,
                progress_callback=progress_callback
            )
    except Exception as e:
        raise Exception(f"فشل الرفع: {str(e)}")

async def main():
    print("="*70)
    print("🚀 سكريبت رفع المحتوى على تيليجرام - الإصدار المحسن")
    print("="*70)
    
    # التحقق من المتغيرات المطلوبة
    required = ['MODE', 'CHANNEL', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION_STRING']
    missing = [var for var in required if not os.getenv(var, '').strip()]
    if missing:
        raise Exception(f"المتغيرات التالية مفقودة: {', '.join(missing)}")
    
    mode = os.getenv('MODE', '').strip().lower()
    channel = os.getenv('CHANNEL', '').strip()
    caption = os.getenv('CAPTION', '').replace('\\n', '\n').strip()
    
    if mode not in ['movie', 'series']:
        raise Exception("الوضع يجب أن يكون 'movie' أو 'series' فقط!")
    
    # إعداد العميل
    client = TelegramClient(
        StringSession(os.getenv('TELEGRAM_SESSION_STRING')),
        int(os.getenv('TELEGRAM_API_ID')),
        os.getenv('TELEGRAM_API_HASH'),
        flood_sleep_threshold=120
    )
    
    await client.start()
    me = await client.get_me()
    print(f"✅ تم تسجيل الدخول كـ: {me.first_name} (@{me.username})")
    
    # الحصول على الكيان (القناة)
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
            if mode == 'movie':
                await handle_movie_mode(client, entity, caption, tmp_dir)
            else:
                await handle_series_mode(client, entity, caption, tmp_dir)
                
        finally:
            await client.disconnect()
            print("\n" + "="*70)
            print("✅ تم إنهاء الجلسة")
            print("="*70)

async def handle_movie_mode(client, entity, caption, tmp_dir):
    """معالجة وضع الأفلام"""
    img_url = os.getenv('IMAGE_URL', '').strip()
    vid_url = os.getenv('VIDEO_URL', '').strip()
    vid_name = os.getenv('VIDEO_NAME', 'movie').strip() or 'movie'
    
    if not img_url or not vid_url:
        raise Exception("وضع الفيلم يتطلب IMAGE_URL و VIDEO_URL")
    
    print("\n🎬 جاري تحضير الفيلم...")
    
    # تحميل البوستر
    print("\n📥 تحميل البوستر...")
    img_ext = os.path.splitext(urlparse(img_url).path)[1].lower()
    if not img_ext or len(img_ext) > 5:
        img_ext = '.jpg'
    img_path = os.path.join(tmp_dir, f"poster{img_ext}")
    
    await download_file_with_progress(img_url, img_path, prefix='📥 البوستر')
    
    # تحويل WebP إلى JPG إذا لزم الأمر
    if img_path.endswith('.webp'):
        try:
            jpg_path = img_path.replace('.webp', '.jpg')
            img = Image.open(img_path).convert('RGB')
            img.save(jpg_path, 'JPEG', quality=95)
            img_path = jpg_path
            print("🔄 تم تحويل WebP إلى JPG")
        except Exception as e:
            print(f"⚠️ فشل تحويل الصورة: {e}")
    
    # تحميل الفيديو
    print(f"\n📥 تحميل الفيديو ({vid_name})...")
    vid_name_clean = sanitize_filename(vid_name)
    vid_path = os.path.join(tmp_dir, f"{vid_name_clean}.mp4")
    
    vid_size = await download_file_with_progress(vid_url, vid_path, prefix='📥 الفيديو')
    print(f"✅ حجم الفيديو: {vid_size:.2f} MB")
    
    if vid_size > MAX_VIDEO_SIZE_MB:
        raise Exception(f"حجم الفيديو ({vid_size:.1f}MB) يتجاوز الحد المسموح ({MAX_VIDEO_SIZE_MB}MB)")
    
    # استخراج معلومات الفيديو
    print("\n🔍 استخراج معلومات الفيديو...")
    video_info = get_video_info(vid_path)
    print(f"   الدقة: {video_info['width']}x{video_info['height']}")
    print(f"   المدة: {video_info['duration']} ثانية")
    
    # استخراج Thumbnail
    print("\n🖼️ استخراج Thumbnail...")
    thumb_path = os.path.join(tmp_dir, "thumb.jpg")
    if not extract_thumbnail(vid_path, thumb_path):
        thumb_path = img_path  # استخدام البوستر كـ thumbnail احتياطي
        print("⚠️ تم استخدام البوستر كـ Thumbnail")
    else:
        print("✅ تم استخراج Thumbnail من الفيديو")
    
    # رفع Album (صورة + فيديو معاً)
    print("\n📤 جاري رفع Album (الصورة + الفيديو)...")
    print("⏳ قد يستغرق الرفع بعض الوقت حسب حجم الملف...\n")
    
    try:
        # طريقة أفضل لرفع Album باستخدام send_file مع قائمة
        album_files = [img_path, vid_path]
        
        # إعداد attributes للفيديو فقط
        vid_attributes = [DocumentAttributeVideo(
            duration=video_info['duration'],
            w=video_info['width'],
            h=video_info['height'],
            supports_streaming=True
        )]
        
        # رفع الـ Album
        # نستخدم force_document=False للفيديو ليعرض بشكل فيديو وليس ملف
        await client.send_file(
            entity,
            album_files,
            caption=[caption, ''],  # Caption للصورة فقط، الفيديو بدون caption
            force_document=False,
            supports_streaming=True,
            video_attributes=vid_attributes,  # خاصية جديدة في Telethon
            thumb=thumb_path
        )
        
        print("\n✅ تم رفع Album بنجاح!")
        print("🎉 الشكل: صورة + فيديو في رسالة واحدة (مجموعة)")
        
    except Exception as e:
        print(f"\n⚠️ فشل رفع Album، جاري المحاولة بالطريقة التقليدية...")
        # طريقة احتياطية: رفع منفصل
        print("📤 رفع البوستر...")
        await client.send_file(entity, img_path, caption=caption)
        print("📤 رفع الفيديو...")
        await upload_with_progress(client, entity, vid_path, caption='', 
                                 is_video=True, video_info=video_info, thumb=thumb_path)
        print("✅ تم الرفع منفصلاً")

async def handle_series_mode(client, entity, caption, tmp_dir):
    """معالجة وضع المسلسلات"""
    series_json = os.getenv('SERIES_DATA', '[]').strip()
    
    if not series_json:
        raise Exception("وضع المسلسلات يتطلب SERIES_DATA (JSON)")
    
    try:
        episodes = json.loads(series_json)
        if not isinstance(episodes, list):
            raise Exception("SERIES_DATA يجب أن يكون قائمة (Array)")
    except json.JSONDecodeError as e:
        raise Exception(f"خطأ في تنسيق JSON: {e}")
    
    if not episodes:
        raise Exception("القائمة فارغة، لا يوجد حلقات للرفع")
    
    if len(episodes) > 10:
        print(f"⚠️ الحد الأقصى 10 حلقات، سيتم تجاهل {len(episodes) - 10}")
        episodes = episodes[:10]
    
    print(f"\n📺 عدد الحلقات: {len(episodes)}")
    
    # تحميل جميع الحلقات
    video_files = []
    video_infos = []
    
    for i, ep in enumerate(episodes, 1):
        if not isinstance(ep, dict) or 'url' not in ep:
            print(f"⚠️ تخطي الحلقة {i}: بيانات غير صالحة")
            continue
        
        url = ep['url'].strip()
        name = sanitize_filename(ep.get('name', f'الحلقة_{i}'))
        
        if not url:
            continue
        
        print(f"\n📥 [{i}/{len(episodes)}] تحميل {name}...")
        vid_path = os.path.join(tmp_dir, f"{name}.mp4")
        
        try:
            await download_file_with_progress(url, vid_path, prefix=f'📥 {name}')
            
            # التحقق من الحجم
            size_mb = os.path.getsize(vid_path) / 1024 / 1024
            if size_mb > MAX_VIDEO_SIZE_MB:
                print(f"⚠️ {name} كبير جداً ({size_mb:.1f}MB)، سيتم تخطيه")
                os.remove(vid_path)
                continue
            
            # استخراج المعلومات
            info = get_video_info(vid_path)
            video_files.append(vid_path)
            video_infos.append(info)
            
        except Exception as e:
            print(f"❌ فشل تحميل {name}: {e}")
            continue
    
    if not video_files:
        raise Exception("لم يتم تحميل أي حلقة بنجاح")
    
    print(f"\n📤 جاري رفع {len(video_files)} حلقة...")
    
    # رفع كـ Album إذا كان العدد <= 10
    if len(video_files) > 1:
        print("📦 سيتم رفع الحلقات كـ Album...")
        try:
            await client.send_file(
                entity,
                video_files,
                caption=caption,
                supports_streaming=True,
                force_document=False
            )
            print("✅ تم رفع Album الحلقات بنجاح!")
        except Exception as e:
            print(f"⚠️ فشل Album، جاري الرفع المنفصل...")
            for i, (vid_path, info) in enumerate(zip(video_files, video_infos), 1):
                print(f"\n📤 رفع الحلقة {i}/{len(video_files)}...")
                await upload_with_progress(client, entity, vid_path, 
                                         caption=f"{caption}\n\nالحلقة {i}" if i == 1 else f"الحلقة {i}",
                                         is_video=True, video_info=info)
    else:
        # حلقة واحدة فقط
        print("📤 رفع الحلقة...")
        await upload_with_progress(client, entity, video_files[0], 
                                 caption=caption, is_video=True, video_info=video_infos[0])

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ تم الإلغاء يدوياً")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ خطأ: {str(e)}", file=sys.stderr)
        sys.exit(1)
