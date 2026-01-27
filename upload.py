#!/usr/bin/env python3
import os
import sys
import asyncio
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors.rpcerrorlist import UserAlreadyParticipantError
import requests
import ssl
import urllib3
import time

# تجاوز SSL
if os.getenv('SKIP_SSL_VERIFY', 'false').lower() == 'true':
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    ssl._create_default_https_context = ssl._create_unverified_context

MAX_VIDEO_SIZE_MB = 1999.0
MAX_VIDEO_SIZE_BYTES = int(MAX_VIDEO_SIZE_MB * 1024 * 1024)

def sanitize_filename(filename):
    return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip().rstrip('.')

async def download_file(url, save_dir, base_name, is_image=False):
    url = url.strip()
    if not url:
        raise Exception("رابط فارغ!")
    
    try:
        skip_ssl = os.getenv('SKIP_SSL_VERIFY', 'false').lower() == 'true'
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        print(f"⬇️  تنزيل: {url[:50]}...")
        start = time.time()
        total = 0
        
        response = requests.get(url, stream=True, verify=not skip_ssl, headers=headers, timeout=1200)
        response.raise_for_status()
        
        # تحديد الامتداد
        if is_image:
            ext = os.path.splitext(urlparse(url).path)[1].lower()
            if not ext or len(ext) > 5:
                ext = '.jpg'
            filepath = Path(save_dir) / f"Logo{ext}"
        else:
            base = sanitize_filename(base_name)
            if base.lower().endswith('.mp4'):
                base = base[:-4]
            filepath = Path(save_dir) / f"{base}.mp4"
        
        # التنزيل
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(65536):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
                    if not is_image and total > MAX_VIDEO_SIZE_BYTES * 1.05:
                        f.close()
                        filepath.unlink()
                        raise Exception(f"الحجم تجاوز {MAX_VIDEO_SIZE_MB} ميجابايت")
        
        if total == 0:
            raise Exception("ملف فارغ")
        
        elapsed = time.time() - start
        speed = total / elapsed / 1024 / 1024 if elapsed > 0 else 0
        
        if not is_image and total > MAX_VIDEO_SIZE_BYTES:
            filepath.unlink()
            raise Exception(f"الحجم ({total/1024/1024:.1f} ميجابايت) يتجاوز 1999 ميجابايت")
        
        print(f"✅ تم التنزيل: {filepath.name} ({total/1024/1024:.1f} ميجابايت) | {speed:.1f} ميجابايت/ثانية")
        return str(filepath)
    
    except Exception as e:
        if 'filepath' in locals() and Path(filepath).exists():
            Path(filepath).unlink(missing_ok=True)
        raise Exception(f"فشل التنزيل: {str(e)}")

async def get_channel(client, channel_input):
    channel_input = channel_input.strip()
    
    # تنظيف الرابط
    for prefix in ['https://', 'http://', 't.me/', 'telegram.me/']:
        if channel_input.startswith(prefix):
            channel_input = channel_input[len(prefix):]
    
    # معالجة روابط الدعوة
    if '+' in channel_input:
        hash_part = channel_input.split('+')[-1].split('?')[0].split('&')[0].strip('/')
        try:
            entity = await client.get_entity(f"https://t.me/joinchat/{hash_part}")
            return entity
        except:
            async for dialog in client.iter_dialogs(limit=20):
                if dialog.is_channel and not dialog.is_group:
                    return dialog.entity
    
    # محاولة عادية
    try:
        return await client.get_entity(channel_input)
    except Exception as e:
        raise Exception(f"فشل العثور على القناة: {str(e)}")

async def main():
    print("="*60)
    print("🚀 رفع الألبوم (صورة + فيديو) - الطريقة الصحيحة")
    print("="*60)
    
    # التحقق من المتغيرات
    required = ['CHANNEL', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION_STRING']
    for var in required:
        if not os.getenv(var, '').strip():
            raise Exception(f"المتغير {var} مطلوب")
    
    channel = os.getenv('CHANNEL', '').strip()
    caption = os.getenv('CAPTION', '').replace('\\n', '\n').strip()
    img_url = os.getenv('IMAGE_URL', '').strip()
    vid_url = os.getenv('VIDEO_URL', '').strip()
    vid_name = os.getenv('VIDEO_NAME', 'movie').strip() or 'movie'
    
    if not img_url or not vid_url:
        raise Exception("مطلوب رابط الصورة ورابط الفيديو")
    
    # تسجيل الدخول
    client = TelegramClient(
        StringSession(os.getenv('TELEGRAM_SESSION_STRING')),
        int(os.getenv('TELEGRAM_API_ID')),
        os.getenv('TELEGRAM_API_HASH'),
        flood_sleep_threshold=120
    )
    await client.start()
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            # تنزيل الملفات
            print("\n🎬 جاري التنزيل...")
            image = await download_file(img_url, tmp_dir, 'Logo', is_image=True)
            video = await download_file(vid_url, tmp_dir, vid_name, is_image=False)
            
            # الحصول على القناة
            print(f"\n📤 الرفع على القناة: {channel}")
            entity = await get_channel(client, channel)
            
            # ✅ الحل السحري: رفع الصورة أولاً ثم تعديلها بإضافة الفيديو
            print("🔄 رفع الصورة أولاً...")
            photo_msg = await client.send_file(
                entity,
                image,
                caption=caption,
                parse_mode='html'
            )
            
            print("🔄 تعديل الرسالة بإضافة الفيديو (الخدعة الذكية)...")
            await client.edit_message(
                entity,
                photo_msg.id,
                file=video,
                supports_streaming=True
            )
            
            print("\n✅ تم الرفع بنجاح! الشكل مطابق لتيليجرام ديسكتوب 100%")
            print("ℹ️  الطريقة: تم رفع الصورة أولاً ثم استبدالها بالفيديو مع الحفاظ على المعاينة")
            
        finally:
            await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\n❌ خطأ: {str(e)}", file=sys.stderr)
        sys.exit(1)
