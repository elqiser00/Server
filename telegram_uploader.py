# telegram_uploader.py
import asyncio
import os
import sys
import ssl
import aiohttp
import subprocess
import time
import re
from telethon import TelegramClient, types
from telethon.sessions import StringSession
from telethon.tl.functions.messages import SendMultiMediaRequest
from telethon.tl.types import InputMediaUploadedPhoto, InputMediaUploadedDocument

print("🎬 Telegram Movie Uploader v3.0")
print("=" * 60)

class MovieUploader:
    def __init__(self):
        self.client = None
        self.session = None
        
    async def setup_ssl_context(self):
        """إعداد SSL لتجاوز مشاكل الشهادات"""
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
        
    async def download_file(self, url, filename, max_retries=3):
        """تنزيل ملف مع تجاوز SSL وإعادة المحاولة"""
        for attempt in range(max_retries):
            try:
                print(f"⬇️  محاولة تنزيل {filename} ({attempt + 1}/{max_retries})...")
                
                # استخدام wget مع خيارات SSL
                cmd = [
                    'wget',
                    '--no-check-certificate',  # ⭐ تجاوز SSL
                    '--timeout=60',
                    '--tries=3',
                    '--waitretry=5',
                    '--retry-connrefused',
                    '--user-agent=Mozilla/5.0',
                    '--show-progress',
                    '-O', filename,
                    url
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    if os.path.exists(filename):
                        size = os.path.getsize(filename)
                        print(f"✅ تم تنزيل {filename} ({size:,} بايت)")
                        return True
                else:
                    print(f"⚠️  فشل التنزيل: {result.stderr[:100]}")
                    
            except Exception as e:
                print(f"❌ خطأ في التنزيل: {e}")
            
            if attempt < max_retries - 1:
                print(f"⏳ انتظار 5 ثوان قبل إعادة المحاولة...")
                await asyncio.sleep(5)
        
        return False
    
    def clean_filename(self, name, max_length=60):
        """تنظيف اسم الملف وتعديله"""
        # إزالة الأحرف غير المسموحة
        name = re.sub(r'[<>:"/\\|?*]', '', name)
        # استبدال المساحات المتعددة
        name = re.sub(r'\s+', ' ', name)
        # تقصير إذا كان طويلاً
        if len(name) > max_length:
            name = name[:max_length-3] + "..."
        return name.strip()
    
    async def connect_telegram(self, api_id, api_hash, session_string):
        """الاتصال بـ Telegram"""
        print("\n🔌 جاري الاتصال بـ Telegram...")
        
        try:
            self.client = TelegramClient(
                StringSession(session_string),
                api_id,
                api_hash,
                connection_retries=5,
                request_retries=3,
                use_ipv6=False
            )
            
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                print("❌ الجلسة غير صالحة! يرجى إنشاء SESSION_STRING جديدة")
                return False
            
            me = await self.client.get_me()
            print(f"✅ متصل كـ: {me.first_name} (@{me.username})")
            return True
            
        except Exception as e:
            print(f"❌ خطأ في الاتصال: {e}")
            return False
    
    async def upload_side_by_side(self, channel, poster_path, video_path, movie_name, video_filename):
        """رفع الصورة والفيديو معاً (جانبياً)"""
        print(f"\n📤 جاري رفع الصورة والفيديو معاً...")
        
        try:
            # ⭐⭐ رفع الملفات أولاً ⭐⭐
            print("📦 جاري تحميل الملفات إلى Telegram...")
            
            # رفع الصورة
            photo_upload = await self.client.upload_file(
                poster_path,
                part_size_kb=512
            )
            
            # رفع الفيديو مع دعم البث المباشر
            video_upload = await self.client.upload_file(
                video_path,
                part_size_kb=1024,  # أجزاء أكبر للسرعة
                file_name=video_filename  # ⭐ اسم الملف المعدل ⭐
            )
            
            print("✅ تم تحميل الملفات")
            
            # ⭐⭐ إنشاء وسائط متعددة (ألبوم) ⭐⭐
            media = [
                InputMediaUploadedPhoto(
                    file=photo_upload,
                    caption=f"🎬 {movie_name} - 📸 بوستر الفيلم"
                ),
                InputMediaUploadedDocument(
                    file=video_upload,
                    mime_type='video/mp4',
                    attributes=[
                        types.DocumentAttributeVideo(
                            duration=0,
                            w=0,
                            h=0,
                            round_message=False,
                            supports_streaming=True  # ⭐ دعم البث المباشر ⭐
                        )
                    ],
                    caption=f"🎥 {movie_name}\n📁 {video_filename}\n✅ الفيلم كامل - يعمل كمشغل"
                )
            ]
            
            # ⭐⭐ إرسال الألبوم ⭐⭐
            print("🚀 جاري إرسال الألبوم (الصورة والفيديو معاً)...")
            
            result = await self.client(SendMultiMediaRequest(
                peer=channel,
                multi_media=media,
                silent=None,
                schedule_date=None,
                reply_to=None
            ))
            
            print("✅ تم رفع الألبوم بنجاح!")
            print(f"📸 الصورة: على اليسار")
            print(f"🎥 الفيديو: على اليمين")
            print(f"📝 الاسم: {movie_name}")
            
            return True
            
        except Exception as e:
            print(f"❌ خطأ في رفع الألبوم: {e}")
            return False
    
    async def run(self, config):
        """تشغيل العملية الرئيسية"""
        try:
            # 1. الاتصال بـ Telegram
            if not await self.connect_telegram(
                config['api_id'],
                config['api_hash'],
                config['session_string']
            ):
                return False
            
            # 2. الحصول على القناة
            print(f"\n📢 جاري الوصول للقناة...")
            try:
                channel = await self.client.get_entity(config['channel_link'])
                print(f"✅ القناة: {channel.title}")
            except Exception as e:
                print(f"❌ خطأ في القناة: {e}")
                return False
            
            # 3. ⭐⭐ تعديل اسم ملف الفيديو ⭐⭐
            original_video_name = config['movie_name']
            cleaned_name = self.clean_filename(original_video_name)
            video_filename = f"{cleaned_name}.mp4"
            print(f"📝 اسم الفيديو المعدل: {video_filename}")
            
            # 4. تنزيل الملفات
            print(f"\n⬇️  بدء تنزيل الملفات...")
            
            poster_path = "movie_poster.jpg"
            video_path = "full_movie.mp4"
            
            # تنزيل البوستر
            if not await self.download_file(config['poster_url'], poster_path):
                return False
            
            # تنزيل الفيديو
            print(f"🎥 جاري تنزيل الفيديو ({config['movie_name']})...")
            if not await self.download_file(config['video_url'], video_path):
                return False
            
            video_size = os.path.getsize(video_path)
            print(f"✅ حجم الفيديو: {video_size/(1024*1024):.1f} MB")
            
            # 5. رفع الصورة والفيديو معاً
            success = await self.upload_side_by_side(
                channel,
                poster_path,
                video_path,
                config['movie_name'],
                video_filename  # ⭐ الاسم المعدل ⭐
            )
            
            return success
            
        except Exception as e:
            print(f"💥 خطأ غير متوقع: {type(e).__name__}")
            print(f"📝 {str(e)}")
            return False
            
        finally:
            # تنظيف الملفات
            for file in ['movie_poster.jpg', 'full_movie.mp4']:
                if os.path.exists(file):
                    os.remove(file)
                    print(f"🗑️  تم حذف: {file}")
            
            if self.client:
                await self.client.disconnect()
                print("\n🔒 تم قطع الاتصال")

async def main():
    """الدالة الرئيسية"""
    # ⭐⭐ إعدادات التحميل ⭐⭐
    config = {
        'api_id': int(os.environ.get('TELEGRAM_API_ID', '0')),
        'api_hash': os.environ.get('TELEGRAM_API_HASH', ''),
        'session_string': os.environ.get('TELEGRAM_SESSION_STRING', ''),
        'channel_link': os.environ.get('CHANNEL_LINK', 'https://t.me/+VvLRMffUCXNlNjRk'),
        'movie_name': os.environ.get('MOVIE_NAME', 'Truth & Treason 2025'),
        'poster_url': os.environ.get('POSTER_URL', 'https://img.downet.net/uploads/U8xQf.webp'),
        'video_url': os.environ.get('VIDEO_URL', '')
    }
    
    print(f"🎬 الفيلم: {config['movie_name']}")
    print(f"📢 القناة: {config['channel_link']}")
    print(f"🖼️  البوستر: {config['poster_url'][:50]}...")
    print(f"🎥 الفيديو: {config['video_url'][:50]}...")
    print("=" * 60)
    
    # التحقق من المدخلات
    if not config['video_url']:
        print("❌ يرجى إدخال رابط الفيديو")
        return False
    
    if not config['video_url'].lower().endswith('.mp4'):
        print("⚠️  رابط الفيديو يجب أن ينتهي بـ .mp4")
    
    # تشغيل الرفع
    uploader = MovieUploader()
    success = await uploader.run(config)
    
    if success:
        print("\n" + "=" * 60)
        print("🎉 تم الرفع بنجاح!")
        print("📸 الصورة والفيديو في نفس البوست")
        print("📍 الصورة على اليسار | الفيديو على اليمين")
        print("📝 اسم الفيلم في الكابشن")
        print("🎬 الفيديو يعمل كمشغل مباشر")
        print("=" * 60)
    else:
        print("\n❌ فشل الرفع!")
    
    return success

if __name__ == "__main__":
    # إعدادات asyncio للملفات الكبيرة
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # تشغيل البرنامج
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️  تم إيقاف العملية")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 خطأ في التشغيل: {e}")
        sys.exit(1)
