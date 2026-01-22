# telegram_uploader_final.py
import asyncio
import os
import sys
import subprocess
import time
import re
from telethon import TelegramClient, types
from telethon.sessions import StringSession
from telethon.tl.functions.messages import SendMultiMediaRequest
from telethon.tl.types import InputMediaUploadedPhoto, InputMediaUploadedDocument

print("🎬 Telegram Movie Uploader - Final Version")
print("=" * 60)

class MovieUploader:
    def __init__(self):
        self.client = None
        self.uploaded_files = []
        
    async def download_file(self, url, filename, max_retries=3):
        """تنزيل ملف مع إعادة المحاولة"""
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
                    '-O', filename,
                    url
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0 and os.path.exists(filename):
                    size = os.path.getsize(filename)
                    print(f"✅ تم تنزيل {filename} ({size:,} بايت)")
                    return True
                    
            except Exception as e:
                print(f"❌ خطأ: {e}")
            
            if attempt < max_retries - 1:
                print("⏳ انتظار 5 ثوان...")
                await asyncio.sleep(5)
        
        return False
    
    def clean_filename(self, name, max_length=60):
        """تنظيف وتعديل اسم الملف"""
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
                connection_retries=3
            )
            
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                print("❌ الجلسة غير صالحة!")
                return False
            
            me = await self.client.get_me()
            print(f"✅ متصل كـ: {me.first_name} (@{me.username})")
            return True
            
        except Exception as e:
            print(f"❌ خطأ: {e}")
            return False
    
    async def upload_as_album(self, channel, poster_path, video_path, movie_name, video_filename):
        """محاولة رفع كألبوم"""
        print("\n📦 محاولة الرفع كألبوم...")
        
        try:
            # رفع الصورة
            print("📸 رفع الصورة...")
            photo_upload = await self.client.upload_file(
                poster_path,
                part_size_kb=512
            )
            self.uploaded_files.append(photo_upload)
            
            # رفع الفيديو
            print("🎥 رفع الفيديو...")
            video_upload = await self.client.upload_file(
                video_path,
                part_size_kb=512,
                file_name=video_filename
            )
            self.uploaded_files.append(video_upload)
            
            # إنشاء الألبوم
            media = [
                InputMediaUploadedPhoto(
                    file=photo_upload,
                    caption=f"🎬 {movie_name} - بوستر"
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
                    caption=f"🎥 {movie_name}\n📁 {video_filename}\n✅ فيلم كامل"
                )
            ]
            
            # إرسال الألبوم
            await self.client(SendMultiMediaRequest(
                peer=channel,
                multi_media=media,
                silent=None,
                schedule_date=None,
                reply_to=None
            ))
            
            print("✅ تم الرفع كألبوم!")
            return True
            
        except Exception as e:
            print(f"⚠️  فشل الألبوم: {e}")
            return False
    
    async def upload_separately(self, channel, poster_path, video_path, movie_name, video_filename):
        """رفع ملفين منفصلين"""
        print("\n📤 رفع ملفين منفصلين...")
        
        try:
            # 1. رفع الصورة
            print("📸 رفع الصورة...")
            await self.client.send_file(
                channel,
                poster_path,
                caption=f"🎬 {movie_name}\n📸 بوستر الفيلم"
            )
            
            # 2. رفع الفيديو مع تتبع التقدم
            print("🎥 رفع الفيديو...")
            video_size = os.path.getsize(video_path)
            print(f"📊 حجم الفيديو: {video_size/(1024*1024):.1f} MB")
            print("⏳ قد يستغرق 30-60 دقيقة...")
            
            upload_start = time.time()
            last_progress = 0
            
            def progress_callback(current, total):
                nonlocal last_progress
                percent = (current / total) * 100
                
                # تحديث كل 10%
                if int(percent) // 10 > last_progress // 10:
                    elapsed = time.time() - upload_start
                    speed = current / elapsed / (1024 * 1024)
                    
                    print(f"📤 رفع: {percent:.1f}% | "
                          f"{current/(1024*1024):.1f} MB | "
                          f"{speed:.2f} MB/ث")
                    last_progress = int(percent)
            
            await self.client.send_file(
                channel,
                video_path,
                caption=f"🎥 {movie_name}\n📁 {video_filename}\n✅ فيلم كامل",
                progress_callback=progress_callback,
                supports_streaming=True,
                file_name=video_filename,
                part_size_kb=512,
                attributes=[
                    types.DocumentAttributeVideo(
                        duration=0,
                        w=0,
                        h=0,
                        round_message=False,
                        supports_streaming=True
                    )
                ]
            )
            
            upload_time = time.time() - upload_start
            print(f"✅ تم رفع الفيديو في {upload_time/60:.1f} دقيقة")
            return True
            
        except Exception as e:
            print(f"❌ خطأ: {e}")
            return False
    
    async def run(self, config):
        """تشغيل العملية"""
        try:
            # الاتصال
            if not await self.connect_telegram(
                config['api_id'],
                config['api_hash'],
                config['session_string']
            ):
                return False
            
            # الحصول على القناة
            print("\n📢 جاري الوصول للقناة...")
            try:
                channel = await self.client.get_entity(config['channel_link'])
                print(f"✅ القناة: {channel.title}")
            except Exception as e:
                print(f"❌ خطأ: {e}")
                return False
            
            # تعديل اسم الفيديو
            clean_name = self.clean_filename(config['movie_name'])
            video_filename = f"{clean_name}.mp4"
            print(f"📝 اسم الفيديو المعدل: {video_filename}")
            
            # تنزيل الملفات
            print("\n⬇️  تنزيل الملفات...")
            
            poster_path = "poster.jpg"
            video_path = "movie.mp4"
            
            if not await self.download_file(config['poster_url'], poster_path):
                return False
            
            if not await self.download_file(config['video_url'], video_path):
                return False
            
            # محاولة الرفع
            success = await self.upload_as_album(
                channel, poster_path, video_path, 
                config['movie_name'], video_filename
            )
            
            if not success:
                print("\n🔄 جرب طريقة الرفع المنفصل...")
                success = await self.upload_separately(
                    channel, poster_path, video_path,
                    config['movie_name'], video_filename
                )
            
            return success
            
        except Exception as e:
            print(f"\n💥 خطأ غير متوقع: {type(e).__name__}")
            print(f"📝 {str(e)[:200]}")
            return False
            
        finally:
            # تنظيف
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
    
    uploader = MovieUploader()
    success = await uploader.run(config)
    
    if success:
        print("\n" + "=" * 60)
        print("🎉 تم الرفع بنجاح!")
        print("✅ الصورة والفيديو في القناة")
        print("✅ اسم الفيديو معدل")
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
