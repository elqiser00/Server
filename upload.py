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

async def validate_and_download_file(url, save_dir, base_name, is_image=False):
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
                url, stream=True, verify=verify_ssl, headers=headers,
                timeout=1200, allow_redirects=True
            )
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0)) or 1
            
            if is_image:
                ext = os.path.splitext(urlparse(url).path)[1].lower()
                if not ext or len(ext) > 5 or ext in ['.php', '.asp', '.html']:
                    content_type = response.headers.get('content-type', '')
                    ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or '.jpg'
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

def get_video_info(video_path):
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
        pass
    
    return {'width': 1280, 'height': 720, 'duration': 0}

def extract_video_thumbnail(video_path, output_path, time_sec=1):
    try:
        cmd = [
            'ffmpeg', '-y', '-i', video_path,
            '-ss', str(time_sec),
            '-vframes', '1',
            '-q:v', '1',
            '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception as e:
        return False

async def resolve_channel(client, channel_input):
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
    print("🚀 سكريبت رفع المحتوى على تيليجرام - Album حقيقي")
    print("="*70)
    
    required = ['MODE', 'CHANNEL', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION_STRING']
    for var in required:
        if not os.getenv(var, '').strip():
            raise Exception(f"المتغير {var} مطلوب")
    
    mode = os.getenv('MODE', '').strip().lower()
    channel = os.getenv('CHANNEL', '').strip()
    caption = os.getenv('CAPTION', '').replace('\\n', '\n').strip()
    
    if mode not in ['movie', 'series']:
        raise Exception("الوضع غير مدعوم!")
    
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
                
                print("جاري تحميل البوستر", end='', flush=True)
                image_path, img_size, img_speed = await validate_and_download_file(img_url, tmp_dir, 'poster', is_image=True)
                print(" ✅")
                
                # تحويل WebP إلى JPG
                if image_path.lower().endswith('.webp'):
                    try:
                        jpg_path = str(Path(image_path).with_suffix('.jpg'))
                        img = Image.open(image_path).convert('RGB')
                        img.save(jpg_path, 'JPEG', quality=95)
                        image_path = jpg_path
                        print(f"   تم تحويل WebP إلى JPG")
                    except:
                        pass
                
                print("جاري تحميل الفيديو", end='', flush=True)
                video_path, vid_size, vid_speed = await validate_and_download_file(vid_url, tmp_dir, vid_name, is_image=False)
                print(" ✅")
                
                print("جاري استخراج معلومات الفيديو...", end='', flush=True)
                video_info = get_video_info(video_path)
                print(" ✅")
                
                print("جاري استخراج Thumbnail...", end='', flush=True)
                video_thumb_path = os.path.join(tmp_dir, "video_thumb.jpg")
                
                if not extract_video_thumbnail(video_path, video_thumb_path, 1):
                    extract_video_thumbnail(video_path, video_thumb_path, 5)
                
                if os.path.exists(video_thumb_path):
                    print(" ✅")
                else:
                    print(" ⚠️")
                    video_thumb_path = image_path
                
                print(f"\n✅ جاهز للرفع")
            
            else:  # series
                try:
                    import json
                    series = json.loads(os.getenv('SERIES_VIDEOS', '[]'))
                except Exception as e:
                    raise Exception(f"خطأ في JSON: {str(e)}")
                
                if not isinstance(series, list) or not series:
                    raise Exception("مطلوب ملف فيديو واحد على الأقل")
                
                if len(series) > 10:
                    print(f"⚠️ سيتم رفع أول 10 ملفات فقط")
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
                        print(f"جاري تحميل الحلقة {i}", end='', flush=True)
                        file_path, file_size, file_speed = await validate_and_download_file(url, tmp_dir, name, is_image=False)
                        print(" ✅")
                        media_files.append(file_path)
                    except Exception as e:
                        print(f" ❌")
                        if not media_files:
                            raise Exception("فشل جميع الملفات")
                        break
            
            print(f"\n📤 جاري الرفع على القناة: {channel}")
            entity = await resolve_channel(client, channel)
            input_peer = get_input_peer(entity)
            
            if mode == 'movie':
                print("جاري رفع Album (صورة + فيديو جنب بعض)...", end='', flush=True)
                
                # ✅ رفع الملفات
                uploaded_photo = await client.upload_file(image_path)
                uploaded_video = await client.upload_file(video_path)
                uploaded_thumb = await client.upload_file(video_thumb_path)
                
                # ✅ إنشاء InputMedia للصورة
                photo_media = InputMediaUploadedPhoto(uploaded_photo)
                
                # ✅ إنشاء InputMedia للفيديو
                video_media = InputMediaUploadedDocument(
                    file=uploaded_video,
                    mime_type='video/mp4',
                    attributes=[
                        DocumentAttributeVideo(
                            duration=video_info['duration'],
                            w=video_info['width'],
                            h=video_info['height'],
                            supports_streaming=True
                        )
                    ],
                    thumb=uploaded_thumb,  # ✅ InputFile مش bytes
                    force_file=False
                )
                
                # ✅ إنشاء قائمة Album
                media_list = [
                    InputSingleMedia(
                        media=photo_media,
                        message=caption,
                        entities=[]
                    ),
                    InputSingleMedia(
                        media=video_media,
                        message='',
                        entities=[]
                    )
                ]
                
                # ✅ إرسال Album
                await client(SendMultiMediaRequest(
                    peer=input_peer,
                    multi_media=media_list
                ))
                
                print(" ✅")
                print("\n✅ تم الرفع بنجاح!")
                print("🎉 الشكل: صورة على اليسار + فيديو على اليمين (Album حقيقي)")
            
            else:  # series
                print("جاري رفع ملفات المسلسلات", end='', flush=True)
                await client.send_file(
                    entity,
                    media_files,
                    caption=caption,
                    parse_mode='html',
                    supports_streaming=True,
                    force_document=False
                )
                print(" ✅")
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
        print("\n⚠️ تم الإلغاء يدوياً", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"❌ خطأ: {str(e)}", file=sys.stderr)
        print(f"{'='*70}", file=sys.stderr)
        sys.exit(1)
