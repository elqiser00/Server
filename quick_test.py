#!/usr/bin/env python3
"""
اختبار سريع للاتصال
"""

import os
import sys

print("🔍 اختبار الإعدادات...")
print("="*40)

# التحقق من الأسرار
secrets = {
    'TELEGRAM_API_ID': os.getenv('TELEGRAM_API_ID'),
    'TELEGRAM_API_HASH': os.getenv('TELEGRAM_API_HASH'),
    'TELEGRAM_PHONE': os.getenv('TELEGRAM_PHONE'),
    'TELEGRAM_SESSION_STRING': os.getenv('TELEGRAM_SESSION_STRING'),
}

for key, value in secrets.items():
    status = "✅" if value else "❌"
    display = value[:20] + "..." if value and len(value) > 20 else value or "مفقود"
    print(f"{status} {key}: {display}")

print("="*40)

if all([secrets['TELEGRAM_API_ID'], secrets['TELEGRAM_API_HASH'], secrets['TELEGRAM_PHONE']]):
    print("✅ البيانات الأساسية موجودة")
    
    if secrets['TELEGRAM_SESSION_STRING']:
        print("✅ سلسلة الجلسة موجودة")
        
        # اختبار صيغة سلسلة الجلسة
        if secrets['TELEGRAM_SESSION_STRING'].startswith('1'):
            print("✅ صيغة سلسلة الجلسة صحيحة")
        else:
            print("⚠️  صيغة سلسلة الجلسة قد تكون غير صحيحة")
    else:
        print("⚠️  سلسلة الجلسة مفقودة - ستحتاج لتسجيل الدخول")
    
    print("\n✅ جاهز للتشغيل!")
else:
    print("❌ بعض البيانات الأساسية مفقودة")
    sys.exit(1)
