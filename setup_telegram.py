#!/usr/bin/env python3
"""
سكريبت لإنشاء سلسلة جلسة صالحة لـ GitHub Actions
"""

import asyncio
import base64
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

async def main():
    print("🔧 إنشاء جلسة تليجرام لـ GitHub Actions")
    print("="*50)
    
    # البيانات
    api_id = input("API ID: ").strip()
    api_hash = input("API Hash: ").strip()
    phone = input("رقم الهاتف (مثال: +201234567890): ").strip()
    
    # إنشاء جلسة نصية
    session = StringSession()
    client = TelegramClient(session, api_id, api_hash)
    
    await client.connect()
    
    if not await client.is_user_authorized():
        print("\n📱 إرسال رمز التحقق...")
        await client.send_code_request(phone)
        
        code = input("أدخل الرمز من تليجرام: ").strip()
        
        try:
            await client.sign_in(phone, code)
            print("✅ تم التسجيل")
        except SessionPasswordNeededError:
            password = input("كلمة المرور (2FA): ").strip()
            await client.sign_in(password=password)
            print("✅ تم التسجيل بكلمة المرور")
    
    # الحصول على سلسلة الجلسة
    session_string = session.save()
    
    print("\n" + "="*50)
    print("🎉 تم إنشاء الجلسة!")
    print("="*50)
    
    print("\n🔐 سلسلة الجلسة الصحيحة:")
    print("="*50)
    print(session_string)
    print("="*50)
    
    # التحقق
    print("\n🔍 اختبار الجلسة...")
    me = await client.get_me()
    print(f"✅ الحساب: {me.first_name} (@{me.username})")
    
    print("\n💡 تعليمات:")
    print("1. انسخ السلسلة أعلاه كاملة")
    print("2. اذهب إلى GitHub → Settings → Secrets → Actions")
    print("3. أضف سر جديد باسم TELEGRAM_SESSION_STRING")
    print("4. الصق السلسلة كقيمة")
    print("5. احفظ التغييرات")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
