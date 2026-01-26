#!/usr/bin/env python3
"""
Script for GitHub Actions - Telegram Media Uploader
"""

import os
import sys
import asyncio
import json
from pathlib import Path

# إضافة المسار للوحدات
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import TelegramMediaUploader

async def run_github_actions():
    """تشغيل الرفع في GitHub Actions"""
    print("🚀 بدء رفع الملفات إلى التليجرام عبر GitHub Actions...")
    
    # إنشاء مثيل الرفع
    uploader = TelegramMediaUploader()
    
    # قراءة المدخلات من GitHub Actions
    uploader.is_github_actions = True
    
    # الحصول على معلومات الملفات من workflow
    logo_url = os.getenv('INPUT_LOGO_URL', '')
    media_type = os.getenv('INPUT_MEDIA_TYPE', 'أفلام')
    caption = os.getenv('INPUT_CAPTION', '')
    
    # الحصول على مسارات الملفات
    video_paths_input = os.getenv('INPUT_VIDEO_PATHS', '')
    if video_paths_input:
        # تقسيم المسارات وفلترتها
        video_paths = []
        for path in video_paths_input.split(','):
            path = path.strip()
            if path:
                video_paths.append(path)
        
        print(f"📁 عدد الملفات: {len(video_paths)}")
        
        # التحقق من وجود الملفات
        valid_paths = []
        for path in video_paths:
            p = Path(path)
            if p.exists():
                valid_paths.append(p)
                print(f"✓ {p.name}")
            else:
                print(f"✗ {path} (غير موجود)")
        
        if not valid_paths:
            print("❌ لا توجد ملفات صالحة للرفع")
            sys.exit(1)
        
        # التحقق من البيانات
        if not uploader.validate_data():
            sys.exit(1)
        
        # إعداد العميل
        if not await uploader.setup_client():
            sys.exit(1)
        
        try:
            # تحميل الشعار
            logo_path = await uploader.download_logo(logo_url) if logo_url else None
            
            # معالجة الملفات حسب النوع
            if media_type == "أفلام":
                uploader.media_type = "أفلام"
                uploader.caption = caption
                await uploader.send_movie_post(valid_paths[0], logo_path)
            else:  # مسلسلات
                uploader.media_type = "مسلسلات"
                uploader.caption = caption
                await uploader.send_series_post(valid_paths[:10], logo_path)
                
        except Exception as e:
            print(f"❌ خطأ أثناء الرفع: {str(e)}")
            sys.exit(1)
        finally:
            # إغلاق العميل
            if uploader.client:
                await uploader.client.disconnect()
    else:
        print("❌ لم يتم توفير مسارات الملفات")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_github_actions())
