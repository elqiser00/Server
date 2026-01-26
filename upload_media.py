#!/usr/bin/env python3
"""
Script for GitHub Actions - Telegram Media Uploader
"""

import os
import sys
import asyncio
from pathlib import Path
import main  # استيراد الكود الرئيسي

async def run_upload():
    # قراءة المدخلات من GitHub Actions
    channel_url = os.getenv('INPUT_CHANNEL_URL')
    media_type = os.getenv('INPUT_MEDIA_TYPE', 'أفلام')
    caption = os.getenv('INPUT_CAPTION', '')
    logo_url = os.getenv('INPUT_LOGO_URL')
    
    # مسارات الملفات
    video_paths = []
    if os.getenv('INPUT_VIDEO_PATHS'):
        video_paths = [p.strip() for p in os.getenv('INPUT_VIDEO_PATHS').split(',')]
    
    # التحقق من البيانات
    if not channel_url:
        print("❌ CHANNEL_URL مطلوب!")
        sys.exit(1)
    
    # إنشاء مثيل الرفع
    uploader = main.TelegramMediaUploader()
    uploader.channel_url = channel_url
    uploader.media_type = media_type
    uploader.caption = caption
    
    # التحقق من البيانات
    if not uploader.validate_data():
        sys.exit(1)
    
    # إعداد العميل
    if not await uploader.setup_client():
        sys.exit(1)
    
    try:
        # معالجة الملفات
        if media_type == "أفلام" and video_paths:
            logo_path = await uploader.download_logo(logo_url) if logo_url else None
            video_path = Path(video_paths[0])
            await uploader.send_movie_post(video_path, logo_path)
        elif media_type == "مسلسلات" and video_paths:
            logo_path = await uploader.download_logo(logo_url) if logo_url else None
            video_files = [Path(p) for p in video_paths]
            await uploader.send_series_post(video_files[:10], logo_path)
    finally:
        # إغلاق العميل
        if uploader.client:
            await uploader.client.disconnect()

if __name__ == "__main__":
    asyncio.run(run_upload())
