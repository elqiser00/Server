# telegram_uploader_fixed.py
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

print("🎬 Telegram Movie Uploader v3.1 - Fixed")
print("=" * 60)

class MovieUploader:
    def __init__(self):
        self.client = None
        
    async def download_file(self, url, filename, max_retries=3):
        """تنزيل ملف مع تجاوز SSL وإعادة المحاولة"""
        for attempt in range(max_retries):
            try:
                print(f"⬇️  محاولة تنزيل {filename} ({attempt + 1}/{max_retries})...")
                
                cmd = [
                    'wget',
                    '--no-check-certificate',
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
        name = re.sub(r'[<>:"/\\|?*]', '', name)
        name = re.sub(r'\s+', ' ', name)
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
                request_retries=3
            )
            
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                print("❌ الجلسة غير صالحة!")
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
            
            # ⭐⭐ التصحيح: part_size_kb=512 أو أقل ⭐⭐
            print("📸 رفع الصورة...")
            photo_upload = await self.client.upload_file(
                poster_path,
                part_size_kb=512  # ⭐ 512KB كحد أقصى ⭐
            )
            print("✅ تم رفع الصورة")
            
            print("🎥 رفع الفيديو...")
            video_upload = await self.client.upload_file(
                video_path,
                part_size_kb=512,  # ⭐ 512KB كحد أقصى ⭐
                file_name=video_filename
            )
            print("✅ تم رفع الفيديو")
            
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
                            supports_streaming=True
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
    
    async def upload_separate_but_together(self, channel, poster_path, video_path, movie_name, video_filename):
        """بديل: رفع ملفين منفصلين ولكن متتاليين"""
        print(f"\n📤 جاري رفع الصورة والفيديو (بديل)...")
        
        try:
            # 1. رفع الصورة أولاً
            print("📸 رفع الصورة...")
            await self.client.send_file(
                channel,
                poster_path,
                caption=f"🎬 {movie_name}\n📸 بوستر الفيلم\n⏳ جاري رفع الفيديو..."
            )
            print("✅ تم رفع الصورة")
            
            # 2. رفع الفيديو ثانياً
            print("🎥 رفع الفيديو...")
            
            # دالة عرض التقدم
            upload_start = time.time()
            last_update = 0
            
            def progress_callback(current, total):
                nonlocal last_update
                now = time.time()
                
                if now - last_update > 10:  # تحديث كل 10 ثوان
                    percent = (current / total) * 100
                    elapsed = now - upload_start
                    speed = current / elapsed / (1024 * 1024)
                    
                    print(f"📤 رفع الفيديو: {percent:.1f}% | "
                          f"{current/(1024*1024):.1f}/{total/(1024*1024):.1f} MB | "
                          f"{speed:.2f} MB/ث")
                    last_update = now
            
            # رفع الفيديو
            await self.client.send_file(
                channel,
                video_path,
                caption=f"🎥 {movie_name}\n📁 {video_filename}\n✅ الفيلم كامل - يعمل كمشغل",
                progress_callback=progress_callback,
                supports_streaming=True,
                file_name=video_filename,
                part_size_kb=512  # ⭐ مهم: 512KB ⭐
            )
            
            upload_time = time.time() - upload_start
            print(f"✅ تم رفع الفيديو في {upload_time/60:.1f} دقيقة")
            
            return True
            
        except Exception as e:
            print(f"❌ خطأ في الرفع: {e}")
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
            
            # 3. تعديل اسم ملف الفيديو
            cleaned_name = self.clean_filename(config['movie_name'])
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
            print(f"🎥 جاري تنزيل الفيديو...")
            if not await self.download_file(config['video_url'], video_path):
                return False
            
            video_size = os.path.getsize(video_path)
            print(f"✅ حجم الفيديو: {video_size/(1024*1024):.1f} MB")
            
            # 5. محاولة رفع الألبوم أولاً
            print(f"\n🔄 محاولة رفع كألبوم...")
            success = await self.upload_side_by_side(
                channel,
                poster_path,
                video_path,
                config['movie_name'],
                video_filename
            )
            
            # 6. إذا فشل الألبوم، جرب الرفع المنفصل
            if not success:
                print(f"\n🔄 جرب طريقة الرفع المنفصل...")
                success = await self.upload_separate_but_together(
                    channel,
                    poster_path,
                    video_path,
                    config['movie_name'],
                    video_filename
                )
            
            return success
            
        except Exception as e:
            print(f"💥 خطأ غير متوقع: {type(e).__name__}")
            print(f"📝 {str(e)}")
            return False
            
        finally:
            # تنظيف الملفات
            for file in [poster_path, video_path]:
                if os.path.exists(file):
                    os.remove(file)
                    print(f"🗑️  تم حذف: {file}")
            
            if self.client:
                await self.client.disconnect()
                print("\n🔒 تم قطع الاتصال")

async def main():
    """الدالة الرئيسية"""
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
    print(f"👤 الحساب: @ELQISEER")
    print("=" * 60)
    
    if not config['video_url']:
        print("❌ يرجى إدخال رابط الفيديو")
        return False
    
    # تشغيل الرفع
    uploader = MovieUploader()
    success = await uploader.run(config)
    
    if success:
        print("\n" + "=" * 60)
        print("🎉 تم الرفع بنجاح!")
        print("✅ الصورة والفيديو في القناة")
        print("✅ اسم الفيلم ظاهر")
        print("✅ الفيديو يعمل كمشغل")
        print("=" * 60)
    else:
        print("\n❌ فشل الرفع!")
    
    return success

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️  تم إيقاف العملية")
        sys.exit(1)
