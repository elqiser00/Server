#!/usr/bin/env python3
"""
سكريبت لإنشاء جلسة تيليجرام (Session String)
شغّله محلياً على جهازك لمرة واحدة فقط، ثم احفظ الـ Session String في GitHub Secrets
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

async def main():
    print("="*60)
    print("🔐 إنشاء جلسة تيليجرام")
    print("="*60)
    
    api_id = input("أدخل API ID: ").strip()
    api_hash = input("أدخل API Hash: ").strip()
    phone = input("أدخل رقم الهاتف (مع كود الدولة): ").strip()
    
    if not api_id or not api_hash or not phone:
        print("❌ جميع الحقول مطلوبة!")
        return
    
    client = TelegramClient(StringSession(), api_id, api_hash)
    
    await client.start(phone)
    
    if not await client.is_user_authorized():
        print("❌ فشل التسجيل - تأكد من صحة البيانات")
        return
    
    session_string = client.session.save()
    print("\n" + "="*60)
    print("✅ تم إنشاء الجلسة بنجاح!")
    print("="*60)
    print("\n🔐 انسخ هذا الـ Session String وضعه في GitHub Secrets كـ TELEGRAM_SESSION_STRING:")
    print("\n" + session_string)
    print("\n" + "="*60)
    print("⚠️  تحذير أمان: لا تشارك هذا الكود مع أي شخص!")
    print("="*60)
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
