#!/usr/bin/env python3
"""
سكريبت لإعداد جلسة التليجرام محلياً
"""

import asyncio
import os
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

async def setup_session():
    """إعداد جلسة التليجرام"""
    print("🔧 إعداد جلسة التليجرام")
    print("="*50)
    
    # الحصول على البيانات
    api_id = input("أدخل API ID: ").strip()
    api_hash = input("أدخل API Hash: ").strip()
    phone = input("أدخل رقم الهاتف (مثال: +201234567890): ").strip()
    
    # اسم ملف الجلسة
    session_name = phone.replace('+', '').replace(' ', '')
    
    # إنشاء العميل
    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
    
    await client.connect()
    
    if not await client.is_user_authorized():
        print("📱 إرسال رمز التحقق...")
        await client.send_code_request(phone)
        
        code = input("أدخل الرمز الذي وصلك: ").strip()
        
        try:
            await client.sign_in(phone, code)
            print("✅ تم تسجيل الدخول")
        except SessionPasswordNeededError:
            password = input("أدخل كلمة مرور الحساب: ").strip()
            await client.sign_in(password=password)
            print("✅ تم تسجيل الدخول بكلمة المرور")
    
    # اختبار الاتصال
    me = await client.get_me()
    print(f"👤 مرحباً {me.first_name}!")
    
    # الحصول على سلسلة الجلسة
    session_string = await client.session.save()
    print("\n" + "="*50)
    print("🔐 سلسلة الجلسة (SESSION STRING):")
    print("="*50)
    print(session_string)
    print("="*50)
    
    print("\n💡 انسخ السلسلة وضعها في GitHub Secrets كـ:")
    print("   TELEGRAM_SESSION_STRING")
    
    await client.disconnect()

if __name__ == "__main__":
    # إنشاء مجلد الجلسات
    os.makedirs("sessions", exist_ok=True)
    
    asyncio.run(setup_session())
