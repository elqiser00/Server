#!/usr/bin/env python3
"""
Script for GitHub Actions - Telegram Media Uploader
"""

import os
import sys
import asyncio
from pathlib import Path

# إضافة المسار للوحدات
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import TelegramMediaUploader

async def run_github_actions():
    """تشغيل الرفع في GitHub Actions"""
    print("=" * 60)
    print("🚀 بدء رفع الملفات إلى التليجرام عبر GitHub Actions")
    print("=" * 60)
    
    # إنشاء مثيل الرفع
    uploader = TelegramMediaUploader()
    uploader.is_github_actions = True
    
    # قراءة المدخلات
    channel_url = os.getenv('INPUT_CHANNEL_URL', '')
    media_type = os.getenv('INPUT_MEDIA_TYPE', 'أفلام')
    logo_url = os.getenv('INPUT_LOGO_URL', '')
    caption = os.getenv('INPUT_CAPTION', '')
    video_paths_input = os.getenv('INPUT_VIDEO_PATHS', '')
    
    # التحقق من البيانات الأساسية
    if not channel_url:
        print("❌ خطأ: رابط القناة مطلوب!")
        print("🔧 الحل: أضف 'channel_url' في مدخلات workflow")
        sys.exit(1)
    
    if not video_paths_input:
        print("❌ خطأ: روابط الفيديو مطلوبة!")
        print("🔧 الحل: أضف 'video_paths' في مدخلات workflow")
        sys.exit(1)
    
    print(f"📢 القناة: {channel_url}")
    print(f"🎬 النوع: {media_type}")
    print(f"🖼️  الشعار: {logo_url if logo_url else 'لا يوجد'}")
    print(f"📝 الكبشر: {caption if caption else 'لا يوجد'}")
    
    # التحقق من بيانات التليجرام
    required_secrets = ['TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_PHONE']
    missing_secrets = []
    
    for secret in required_secrets:
        if not os.getenv(secret):
            missing_secrets.append(secret)
    
    if missing_secrets:
        print(f"❌ خطأ: أسرار GitHub مفقودة: {', '.join(missing_secrets)}")
        print("🔧 الحل: أضف هذه الأسرار في Settings > Secrets and variables > Actions")
        sys.exit(1)
    
    # تمرير البيانات للكلاس
    os.environ['INPUT_CHANNEL_URL'] = channel_url
    os.environ['INPUT_MEDIA_TYPE'] = media_type
    os.environ['INPUT_LOGO_URL'] = logo_url
    os.environ['INPUT_CAPTION'] = caption
    os.environ['INPUT_VIDEO_PATHS'] = video_paths_input
    
    # التحقق من البيانات
    if not uploader.validate_data():
        sys.exit(1)
    
    # إعداد العميل
    print("🔗 جاري الاتصال بالتليجرام...")
    if not await uploader.setup_client():
        sys.exit(1)
    
    try:
        # معالجة الملفات
        print("📥 جاري معالجة الملفات...")
        await uploader.process_files()
        
        print("\n" + "=" * 60)
        print("✅ تم الانتهاء بنجاح!")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n⏹️  تم إيقاف العملية")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ خطأ غير متوقع: {str(e)}")
        sys.exit(1)
    finally:
        # إغلاق العميل
        if uploader.client:
            await uploader.client.disconnect()

if __name__ == "__main__":
    asyncio.run(run_github_actions())
