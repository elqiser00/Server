#!/usr/bin/env python3
import os
import sys
import asyncio
import tempfile
from pathlib import Path
import requests
import urllib3
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors.rpcerrorlist import UserAlreadyParticipantError

# تجاوز SSL عند الحاجة
if os.getenv('SKIP_SSL_VERIFY', 'false').lower() == 'true':
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context

async def download_file(url, save_dir, filename):
    """تنزيل ملف بسيط وسريع"""
    verify = os.getenv('SKIP_SSL_VERIFY', 'false').lower() != 'true'
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    if 'github.com' in url and os.getenv('REPO_TOKEN'):
        headers['Authorization'] = f'token {os.getenv("REPO_TOKEN")}'
    
    r = requests.get(url, stream=True, verify=verify, headers=headers, timeout=1200)
    r.raise_for_status()
    
    filepath = Path(save_dir) / filename
    with open(filepath, 'wb') as f:
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
    return str(filepath)

async def resolve_channel(client, channel_input):
    """التعامل مع روابط الدعوة الخاصة"""
    channel_input = channel_input.strip()
    
    # تنظيف الرابط
    for prefix in ['https://', 'http://', 't.me/', 'telegram.me/']:
        if channel_input.startswith(prefix):
            channel_input = channel_input[len(prefix):]
    
    # معالجة روابط الدعوة (+Abc123)
    if '+' in channel_input:
        hash_part = channel_input.split('+')[-1].split('?')[0].split('&')[0].strip('/')
        try:
            return await client.get_entity(f"https://t.me/joinchat/{hash_part}")
        except:
            # البحث في القنوات المنضمة (كـ صاحب القناة)
            async for dialog in client.iter_dialogs(limit=10):
                if dialog.is_channel and not dialog.is_group:
                    return dialog.entity
    
    return await client.get_entity(channel_input)

async def main():
    print("="*60)
    print("🚀 رفع الفيديو مع صورة مصغرة مخصصة (الطريقة القياسية)")
    print("="*60)
    
    # التحقق من المتغيرات الأساسية
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
    
    # إعداد العميل
    client = TelegramClient(
        StringSession(os.getenv('TELEGRAM_SESSION_STRING')),
        int(os.getenv('TELEGRAM_API_ID')),
        os.getenv('TELEGRAM_API_HASH')
    )
    await client.start()
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            # تنزيل الصورة (كـ صورة مصغرة)
            print("⬇️ جاري تنزيل الصورة المصغرة...")
            thumb_path = await download_file(img_url, tmp_dir, 'thumb.jpg')
            
            # تنزيل الفيديو
            print("⬇️ جاري تنزيل الفيديو...")
            if vid_name.lower().endswith('.mp4'):
                vid_name = vid_name[:-4]
            video_path = await download_file(vid_url, tmp_dir, f"{vid_name}.mp4")
            
            # الحصول على القناة
            print(f"\n📤 الرفع على القناة: {channel}")
            entity = await resolve_channel(client, channel)
            
            # الرفع النهائي (الفيديو مع الصورة كـ صورة مصغرة)
            print("⬆️ جاري الرفع (الفيديو مع الصورة المصغرة)...")
            await client.send_file(
                entity,
                video_path,
                thumb=thumb_path,          # ← الصورة تظهر كـ "بوستر"
                caption=caption,           # ← الكابشن أسفل البوستر
                supports_streaming=True,   # ← تشغيل مباشر بدون تنزيل
                force_document=False,
                parse_mode='html'
            )
            
            print("\n✅ تم الرفع بنجاح!")
            print("ℹ️  الملاحظة: هذه هي الطريقة القياسية المستخدمة")
            print("   في جميع قنوات الأفلام الرسمية على تيليجرام")
            
        finally:
            await client.disconnect()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\n❌ خطأ: {e}", file=sys.stderr)
        sys.exit(1)
