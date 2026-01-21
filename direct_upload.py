# upload_simple.py - أبسط وأسرع
import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
import subprocess

async def main():
    # اتصال بسيط
    client = TelegramClient(
        StringSession(os.environ['TELEGRAM_SESSION_STRING']),
        int(os.environ['TELEGRAM_API_ID']),
        os.environ['TELEGRAM_API_HASH']
    )
    
    await client.connect()
    
    # 1. رفع الصورة فقط أولاً (اختبار)
    print("📸 رفع الصورة كاختبار...")
    subprocess.run(['wget', '-O', 'test.jpg', os.environ['IMAGE_URL']])
    
    channel = await client.get_entity(os.environ['INVITE_LINK'])
    await client.send_file(channel, 'test.jpg', caption='🎬 اختبار رفع')
    
    print("✅ إذا وصلت الصورة، المشكلة في الفيديو")
    await client.disconnect()

asyncio.run(main())
