#!/usr/bin/env python3
"""
Telegram Media Uploader - النسخة النهائية
"""

import os
import sys
import asyncio
import logging
import time
from pathlib import Path
import urllib.parse
import ssl
import aiohttp
from telethon import TelegramClient
from telethon.errors import RPCError, FloodWaitError
from telethon.tl.types import InputMediaUploadedDocument
from telethon.tl.functions.messages import SendMultiMediaRequest
from telethon.tl.types import InputSingleMedia
from telethon.tl.types import DocumentAttributeVideo
from telethon.sessions import StringSession
import mimetypes
import re

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('telegram_upload.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class TelegramUploader:
    def __init__(self):
        self.upload_start_time = 0
        self.print_header()
        self.validate_secrets()
        self.load_inputs()
        
        # إعداد SSL
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        # مجلدات
        self.downloads_dir = Path("downloads")
        self.downloads_dir.mkdir(exist_ok=True)
        
        # العميل
        self.client = None
        self.channel = None
        
        # إحصائيات
        self.stats = {
            'videos_downloaded': 0,
            'videos_uploaded': 0,
            'errors': 0,
            'start_time': time.time()
        }
    
    def print_header(self):
        """طباعة رأس البرنامج"""
        header = """
╔══════════════════════════════════════════════════════╗
║      🚀 TELEGRAM MEDIA UPLOADER - GitHub Actions    ║
║           رفع الأفلام والمسلسلات إلى التليجرام      ║
╚══════════════════════════════════════════════════════╝
        """
        print(header)
    
    def validate_secrets(self):
        """التحقق من وجود الأسرار"""
        logger.info("🔍 التحقق من أسرار GitHub...")
        
        self.api_id = os.getenv('TELEGRAM_API_ID', '')
        self.api_hash = os.getenv('TELEGRAM_API_HASH', '')
        self.phone = os.getenv('TELEGRAM_PHONE', '')
        self.password = os.getenv('TELEGRAM_PASSWORD', '')
        self.session_string = os.getenv('TELEGRAM_SESSION_STRING', '')
        
        # تسجيل
        logger.info(f"   📊 API ID: {'✓' if self.api_id else '✗'}")
        logger.info(f"   🔑 API Hash: {'✓' if self.api_hash else '✗'}")
        logger.info(f"   📱 الهاتف: {'✓' if self.phone else '✗'}")
        logger.info(f"   🔒 كلمة المرور: {'✓' if self.password else '✗'}")
        logger.info(f"   🗝️  سلسلة الجلسة: {'✓' if self.session_string else '✗'}")
        
        # التحقق من الضروريات
        if not self.api_id or not self.api_hash:
            logger.error("❌ بيانات التليجرام الأساسية مفقودة!")
            sys.exit(1)
    
    def load_inputs(self):
        """تحميل مدخلات الـ workflow"""
        logger.info("📥 جاري تحميل المدخلات...")
        
        self.channel_url = os.getenv('INPUT_CHANNEL_URL', '').strip()
        self.media_type = os.getenv('INPUT_MEDIA_TYPE', 'أفلام').strip()
        self.logo_url = os.getenv('INPUT_LOGO_URL', '').strip()
        self.caption = os.getenv('INPUT_CAPTION', '').strip()
        
        # تحميل روابط الفيديو
        video_paths_input = os.getenv('INPUT_VIDEO_PATHS', '').strip()
        self.video_urls = []
        
        if video_paths_input:
            for url in video_paths_input.split(','):
                url = url.strip()
                if url and url.startswith(('http://', 'https://')):
                    self.video_urls.append(url)
        
        # تسجيل المدخلات
        logger.info(f"   📢 القناة: {self.channel_url}")
        logger.info(f"   🎬 النوع: {self.media_type}")
        logger.info(f"   🖼️  الشعار: {self.logo_url if self.logo_url else 'لا يوجد'}")
        logger.info(f"   📝 الوصف: {self.caption if self.caption else 'لا يوجد'}")
        logger.info(f"   📁 الفيديوهات: {len(self.video_urls)}")
        
        # التحقق من المدخلات الأساسية
        if not self.channel_url:
            logger.error("❌ رابط القناة مطلوب!")
            sys.exit(1)
        
        if not self.video_urls:
            logger.error("❌ روابط الفيديو مطلوبة!")
            sys.exit(1)
    
    async def connect_to_telegram(self):
        """الاتصال بتليجرام"""
        try:
            logger.info("🔗 جاري الاتصال بالتليجرام...")
            
            if not self.session_string or not self.session_string.startswith('1'):
                logger.error("❌ سلسلة الجلسة غير صالحة")
                return False
            
            session = StringSession(self.session_string)
            self.client = TelegramClient(
                session=session,
                api_id=int(self.api_id),
                api_hash=self.api_hash,
                device_model="GitHub Actions Bot",
                system_version="Ubuntu Linux",
                app_version="1.0.0"
            )
            
            await self.client.connect()
            
            if await self.client.is_user_authorized():
                me = await self.client.get_me()
                logger.info(f"✅ تم الاتصال كـ: {me.first_name} (@{me.username})")
                return True
            else:
                logger.error("❌ الجلسة غير مفعلة")
                return False
                
        except Exception as e:
            logger.error(f"❌ خطأ في الاتصال: {str(e)}")
            return False
    
    async def get_channel(self):
        """الحصول على كيان القناة"""
        try:
            logger.info(f"🔍 جاري البحث عن القناة...")
            
            channel_input = self.channel_url.strip()
            
            # محاولة مباشرة
            try:
                self.channel = await self.client.get_entity(channel_input)
                logger.info(f"✅ تم العثور على القناة: {self.channel.title}")
                return True
            except Exception:
                pass
            
            # إذا كان رابط دعوة
            if channel_input.startswith('https://t.me/+'):
                invite_hash = channel_input.replace('https://t.me/+', '')
                logger.info(f"   رابط دعوة: {invite_hash}")
                
                try:
                    from telethon.tl.functions.messages import ImportChatInviteRequest
                    result = await self.client(ImportChatInviteRequest(invite_hash))
                    self.channel = await self.client.get_entity(result.chats[0])
                    logger.info(f"✅ تم الانضمام للقناة: {self.channel.title}")
                    return True
                except Exception as e:
                    logger.error(f"❌ لا يمكن الانضمام: {str(e)}")
            
            logger.error("❌ لم أتمكن من العثور على القناة")
            return False
            
        except Exception as e:
            logger.error(f"❌ خطأ في البحث عن القناة: {str(e)}")
            return False
    
    def extract_filename(self, url: str) -> str:
        """استخراج اسم ملف من الرابط"""
        try:
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path)
            
            if not filename or filename == '/':
                domain = parsed.netloc.replace('.', '_')[:20]
                timestamp = int(time.time())
                hash_str = hashlib.md5(url.encode()).hexdigest()[:6]
                filename = f"{domain}_{timestamp}_{hash_str}.mp4"
            
            filename = urllib.parse.unquote(filename)
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            
            if '.' not in filename:
                filename += '.mp4'
            
            return filename[:100]
            
        except:
            import hashlib
            return f"video_{int(time.time())}.mp4"
    
    async def download_file(self, url: str) -> Path:
        """تحميل ملف"""
        filename = self.extract_filename(url)
        filepath = self.downloads_dir / filename
        
        logger.info(f"📥 جاري تحميل: {filename}")
        
        try:
            connector = aiohttp.TCPConnector(ssl=self.ssl_context)
            timeout = aiohttp.ClientTimeout(total=3600)
            
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            ) as session:
                
                async with session.get(url) as response:
                    if response.status == 200:
                        total_size = int(response.headers.get('content-length', 0))
                        
                        with open(filepath, 'wb') as f:
                            downloaded = 0
                            last_progress = 0
                            
                            async for chunk in response.content.iter_chunked(1024*1024):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    
                                    if total_size > 0:
                                        progress = (downloaded / total_size) * 100
                                        if int(progress) >= last_progress + 10:
                                            mb_downloaded = downloaded / 1024 / 1024
                                            mb_total = total_size / 1024 / 1024
                                            logger.info(f"   📊 {int(progress)}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)")
                                            last_progress = int(progress)
                        
                        if filepath.exists():
                            file_size = filepath.stat().st_size
                            if file_size > 0:
                                size_mb = file_size / 1024 / 1024
                                self.stats['videos_downloaded'] += 1
                                logger.info(f"✅ تم التحميل: {filename} ({size_mb:.1f} MB)")
                                return filepath
                            else:
                                filepath.unlink()
                                raise Exception("الملف فارغ")
                        else:
                            raise Exception("فشل حفظ الملف")
                    else:
                        raise Exception(f"HTTP {response.status}")
                        
        except Exception as e:
            logger.error(f"❌ فشل تحميل {filename}: {str(e)}")
            if filepath.exists():
                filepath.unlink(missing_ok=True)
            raise
    
    async def upload_file(self, filepath: Path, is_video: bool = True):
        """رفع ملف"""
        try:
            filename = filepath.name
            size_mb = filepath.stat().st_size / 1024 / 1024
            
            logger.info(f"⬆️  جاري رفع: {filename} ({size_mb:.1f} MB)")
            logger.info(f"⏱️  قد يستغرق: {(size_mb / 2) / 60:.1f} دقيقة تقريباً")
            
            self.upload_start_time = time.time()
            
            file = await self.client.upload_file(
                filepath,
                progress_callback=self.upload_progress
            )
            
            if is_video:
                attributes = [DocumentAttributeVideo(
                    duration=0,
                    w=0,
                    h=0,
                    supports_streaming=True
                )]
                mime_type = "video/mp4"
            else:
                attributes = []
                mime_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
            
            self.stats['videos_uploaded'] += 1
            
            return InputMediaUploadedDocument(
                file=file,
                mime_type=mime_type,
                attributes=attributes,
                force_file=False
            )
            
        except FloodWaitError as e:
            wait_time = e.seconds
            logger.warning(f"⏳ FloodWait: انتظر {wait_time} ثانية")
            await asyncio.sleep(wait_time)
            return await self.upload_file(filepath, is_video)
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"❌ خطأ في رفع {filename}: {str(e)}")
            raise
    
    def upload_progress(self, current: int, total: int):
        """عرض تقدم الرفع"""
        percent = (current / total) * 100
        elapsed = time.time() - self.upload_start_time
        
        if elapsed > 0:
            speed = current / elapsed / 1024 / 1024  # MB/s
            remaining = (total - current) / (speed * 1024 * 1024) if speed > 0 else 0
            
            if int(percent) % 10 == 0:
                mb_current = current / 1024 / 1024
                mb_total = total / 1024 / 1024
                logger.info(f"   📤 {int(percent)}% ({mb_current:.1f}/{mb_total:.1f} MB)")
                logger.info(f"   🚀 السرعة: {speed:.1f} MB/ث - ⏱️  المتبقي: {remaining:.0f} ثانية")
    
    async def download_logo(self) -> Path:
        """تحميل الشعار"""
        if not self.logo_url:
            return None
        
        logger.info("🎨 جاري تحميل الشعار...")
        
        try:
            connector = aiohttp.TCPConnector(ssl=self.ssl_context)
            
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(self.logo_url) as response:
                    if response.status == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if 'image/' in content_type:
                            ext = mimetypes.guess_extension(content_type) or '.jpg'
                        else:
                            if '.' in self.logo_url:
                                ext = '.' + self.logo_url.split('.')[-1].split('?')[0]
                                if ext.lower() not in ['.jpg', '.jpeg', '.png', '.webp']:
                                    ext = '.jpg'
                            else:
                                ext = '.jpg'
                        
                        logo_path = self.downloads_dir / f"logo{ext}"
                        
                        with open(logo_path, 'wb') as f:
                            f.write(await response.read())
                        
                        size_kb = logo_path.stat().st_size / 1024
                        logger.info(f"✅ تم تحميل الشعار ({size_kb:.1f} KB)")
                        return logo_path
                    else:
                        logger.warning(f"⚠️  فشل تحميل الشعار")
                        return None
        except Exception as e:
            logger.warning(f"⚠️  خطأ في تحميل الشعار: {str(e)}")
            return None
    
    async def send_movie(self, video_path: Path, logo_path: Path = None):
        """إرسال فيلم"""
        try:
            logger.info("🎬 جاري إرسال الفيلم...")
            
            media_items = []
            
            # إضافة الصورة
            if logo_path and logo_path.exists():
                try:
                    logo_media = await self.upload_file(logo_path, is_video=False)
                    media_items.append(InputSingleMedia(
                        media=logo_media,
                        message="",
                        entities=None
                    ))
                    logger.info("🖼️  تم إضافة الصورة")
                except Exception as e:
                    logger.warning(f"⚠️  فشل رفع الصورة: {str(e)}")
            
            # رفع الفيديو
            video_media = await self.upload_file(video_path, is_video=True)
            
            media_items.append(InputSingleMedia(
                media=video_media,
                message=self.caption if self.caption else "",
                entities=None
            ))
            
            # إرسال الوسائط - بدون reply_to_msg_id
            result = await self.client(SendMultiMediaRequest(
                peer=self.channel,
                multi_media=media_items,
                silent=None,
                schedule_date=None
            ))
            
            logger.info(f"✅ تم نشر الفيلم بنجاح! (Message ID: {result.id})")
            
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال الفيلم: {str(e)}")
            raise
    
    async def send_series(self, video_paths: list, logo_path: Path = None):
        """إرسال مسلسل"""
        try:
            logger.info(f"📺 جاري إرسال {len(video_paths)} حلقة...")
            
            # الصورة أولاً
            if logo_path and logo_path.exists():
                await self.client.send_file(
                    self.channel,
                    logo_path,
                    caption=self.caption if self.caption else "مسلسل جديد 🎬"
                )
                logger.info("✅ تم إرسال الصورة")
                await asyncio.sleep(1)
            
            # الحلقات في مجموعات
            for i in range(0, len(video_paths), 10):
                batch = video_paths[i:i+10]
                media_items = []
                
                logger.info(f"   📦 مجموعة {i//10 + 1}: {len(batch)} حلقة")
                
                for j, video_path in enumerate(batch):
                    video_media = await self.upload_file(video_path, is_video=True)
                    
                    episode_num = i + j + 1
                    episode_caption = f"الحلقة {episode_num}"
                    
                    media_items.append(InputSingleMedia(
                        media=video_media,
                        message=episode_caption,
                        entities=None
                    ))
                
                # إرسال الدفعة
                if media_items:
                    await self.client(SendMultiMediaRequest(
                        peer=self.channel,
                        multi_media=media_items,
                        silent=None,
                        schedule_date=None
                    ))
                    
                    logger.info(f"   ✅ تم نشر {len(media_items)} حلقة")
                    
                    # انتظار
                    if i + 10 < len(video_paths):
                        await asyncio.sleep(2)
            
            logger.info(f"🎉 تم نشر جميع الحلقات ({len(video_paths)} حلقة)")
            
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال المسلسل: {str(e)}")
            raise
    
    def cleanup_files(self):
        """تنظيف الملفات"""
        try:
            if self.downloads_dir.exists():
                for file in self.downloads_dir.glob("*"):
                    try:
                        file.unlink()
                    except:
                        pass
        except:
            pass
    
    def print_stats(self):
        """طباعة الإحصائيات"""
        total_time = time.time() - self.stats['start_time']
        minutes = total_time / 60
        
        logger.info("📊 الإحصائيات النهائية:")
        logger.info(f"   📥 تم تنزيل: {self.stats['videos_downloaded']}")
        logger.info(f"   📤 تم رفع: {self.stats['videos_uploaded']}")
        logger.info(f"   ⏱️  الوقت الإجمالي: {minutes:.1f} دقيقة")
        logger.info(f"   ❌ أخطاء: {self.stats['errors']}")
    
    async def run(self):
        """تشغيل البرنامج"""
        try:
            # الاتصال
            if not await self.connect_to_telegram():
                return False
            
            # القناة
            if not await self.get_channel():
                return False
            
            # الشعار
            logo_path = await self.download_logo()
            
            # تحميل الفيديوهات
            video_paths = []
            for url in self.video_urls:
                try:
                    video_path = await self.download_file(url)
                    video_paths.append(video_path)
                except Exception as e:
                    logger.error(f"❌ تخطي: {url} - {str(e)}")
                    continue
            
            if not video_paths:
                logger.error("❌ لم يتم تحميل أي فيديو!")
                return False
            
            logger.info(f"✅ جاهز للرفع: {len(video_paths)} ملف")
            
            # الإرسال
            if self.media_type == "أفلام":
                await self.send_movie(video_paths[0], logo_path)
            elif self.media_type == "مسلسلات":
                await self.send_series(video_paths, logo_path)
            else:
                logger.error(f"❌ نوع غير معروف: {self.media_type}")
                return False
            
            # الإحصائيات
            self.print_stats()
            
            return True
            
        except KeyboardInterrupt:
            logger.info("⏹️  تم إيقاف العملية")
            return False
        except Exception as e:
            logger.error(f"❌ خطأ غير متوقع: {str(e)}")
            return False
        finally:
            # تنظيف
            self.cleanup_files()
            
            # إغلاق
            if self.client:
                await self.client.disconnect()
                logger.info("🔌 تم إغلاق الاتصال")

async def main():
    """الدالة الرئيسية"""
    uploader = TelegramUploader()
    success = await uploader.run()
    
    if success:
        print("\n" + "="*60)
        print("✅ تم رفع الملفات بنجاح!")
        print("="*60)
        return 0
    else:
        print("\n" + "="*60)
        print("❌ فشلت عملية الرفع")
        print("="*60)
        return 1

if __name__ == "__main__":
    # إضافة hashlib للاستيراد
    import hashlib
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
