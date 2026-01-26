#!/usr/bin/env python3
"""
Telegram Media Uploader - إرسال الصورة والفيديو معاً
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
from telethon.tl.types import InputMediaUploadedPhoto, InputMediaUploadedDocument
from telethon.tl.functions.messages import SendMultiMediaRequest
from telethon.tl.types import InputSingleMedia
from telethon.tl.types import DocumentAttributeVideo
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
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
        
        # تحرير اسم الفيديو
        self.video_name_override = os.getenv('INPUT_VIDEO_NAME', '').strip()
        
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
        logger.info(f"   ✏️  اسم الفيديو: {self.video_name_override if self.video_name_override else 'تلقائي'}")
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
            except Exception as e:
                logger.debug(f"   المحاولة الأولى فشلت: {str(e)}")
            
            # رابط دعوة
            if channel_input.startswith('https://t.me/+'):
                invite_hash = channel_input.replace('https://t.me/+', '')
                logger.info(f"   📨 رابط دعوة: {invite_hash}")
                
                try:
                    result = await self.client(ImportChatInviteRequest(invite_hash))
                    self.channel = await self.client.get_entity(result.chats[0])
                    logger.info(f"✅ تم الانضمام للقناة: {self.channel.title}")
                    return True
                except Exception as e:
                    logger.error(f"❌ لا يمكن الانضمام: {str(e)}")
                    return False
            
            logger.error("❌ لم أتمكن من العثور على القناة")
            return False
            
        except Exception as e:
            logger.error(f"❌ خطأ في البحث عن القناة: {str(e)}")
            return False
    
    def extract_filename(self, url: str, is_logo: bool = False) -> str:
        """استخراج اسم ملف"""
        if is_logo:
            # للشعار: اسم ثابت
            if self.logo_url and '.' in self.logo_url:
                ext = '.' + self.logo_url.split('.')[-1].split('?')[0]
                ext = re.sub(r'[^a-zA-Z0-9.]', '', ext)
                if len(ext) > 10:
                    ext = '.jpg'
            else:
                ext = '.jpg'
            return f"Logo{ext}"
        
        # للفيديو: اسم مخصص أو من الرابط
        if self.video_name_override:
            filename = self.video_name_override
            if '.' not in filename:
                filename += '.mp4'
            return filename
        
        # استخراج من الرابط
        try:
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path)
            
            if not filename or filename == '/':
                import hashlib
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
    
    async def download_file(self, url: str, is_logo: bool = False) -> Path:
        """تحميل ملف"""
        filename = self.extract_filename(url, is_logo)
        filepath = self.downloads_dir / filename
        
        if is_logo:
            logger.info(f"🎨 جاري تحميل الشعار...")
        else:
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
                                    
                                    if total_size > 0 and not is_logo:
                                        progress = (downloaded / total_size) * 100
                                        if int(progress) >= last_progress + 10:
                                            mb_downloaded = downloaded / 1024 / 1024
                                            mb_total = total_size / 1024 / 1024
                                            logger.info(f"   📊 {int(progress)}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)")
                                            last_progress = int(progress)
                        
                        if filepath.exists():
                            file_size = filepath.stat().st_size
                            if file_size > 0:
                                if is_logo:
                                    size_kb = file_size / 1024
                                    logger.info(f"✅ تم تحميل الشعار: {filename} ({size_kb:.1f} KB)")
                                else:
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
            if is_logo:
                logger.error(f"❌ فشل تحميل الشعار: {str(e)}")
            else:
                logger.error(f"❌ فشل تحميل {filename}: {str(e)}")
            if filepath.exists():
                filepath.unlink(missing_ok=True)
            raise
    
    async def upload_photo(self, filepath: Path):
        """رفع صورة"""
        try:
            filename = filepath.name
            size_mb = filepath.stat().st_size / 1024 / 1024
            
            logger.info(f"🖼️  جاري رفع الصورة: {filename} ({size_mb:.1f} MB)")
            
            file = await self.client.upload_file(filepath)
            
            return InputMediaUploadedPhoto(file=file)
            
        except Exception as e:
            logger.error(f"❌ خطأ في رفع الصورة: {str(e)}")
            raise
    
    async def upload_video(self, filepath: Path):
        """رفع فيديو"""
        try:
            filename = filepath.name
            size_mb = filepath.stat().st_size / 1024 / 1024
            
            logger.info(f"🎬 جاري رفع الفيديو: {filename} ({size_mb:.1f} MB)")
            logger.info(f"⏱️  قد يستغرق: {(size_mb / 2) / 60:.1f} دقيقة")
            
            self.upload_start_time = time.time()
            
            file = await self.client.upload_file(
                filepath,
                progress_callback=self.upload_progress
            )
            
            attributes = [DocumentAttributeVideo(
                duration=0,
                w=0,
                h=0,
                supports_streaming=True
            )]
            
            self.stats['videos_uploaded'] += 1
            
            return InputMediaUploadedDocument(
                file=file,
                mime_type="video/mp4",
                attributes=attributes,
                force_file=False
            )
            
        except FloodWaitError as e:
            wait_time = e.seconds
            logger.warning(f"⏳ FloodWait: انتظر {wait_time} ثانية")
            await asyncio.sleep(wait_time)
            return await self.upload_video(filepath)
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"❌ خطأ في رفع الفيديو: {str(e)}")
            raise
    
    def upload_progress(self, current: int, total: int):
        """عرض تقدم رفع الفيديو"""
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
    
    async def send_movie_with_logo(self, video_path: Path, logo_path: Path = None):
        """إرسال فيلم مع صورة في نفس البوست"""
        try:
            logger.info("🎬 جاري إرسال الفيلم مع الصورة...")
            
            media_items = []
            
            # إضافة الصورة أولاً
            if logo_path and logo_path.exists():
                try:
                    photo_media = await self.upload_photo(logo_path)
                    media_items.append(InputSingleMedia(
                        media=photo_media,
                        message="",
                        entities=None
                    ))
                    logger.info("✅ تم رفع الصورة")
                except Exception as e:
                    logger.warning(f"⚠️  فشل رفع الصورة: {str(e)}")
            
            # إضافة الفيديو مع الوصف
            video_media = await self.upload_video(video_path)
            
            media_items.append(InputSingleMedia(
                media=video_media,
                message=self.caption if self.caption else "",
                entities=None
            ))
            
            # إرسال الوسائط معاً
            logger.info(f"📤 جاري إرسال {len(media_items)} وسائط معاً...")
            
            # الطريقة الصحيحة لإرسال الوسائط المتعددة
            try:
                # المحاولة الأولى: مع جميع الخيارات
                result = await self.client(SendMultiMediaRequest(
                    peer=self.channel,
                    multi_media=media_items,
                    silent=None,
                    schedule_date=None
                ))
            except TypeError:
                # المحاولة الثانية: بدون خيارات إضافية
                result = await self.client(SendMultiMediaRequest(
                    peer=self.channel,
                    multi_media=media_items
                ))
            
            logger.info(f"✅ تم نشر البوست بنجاح! (Message ID: {result.id})")
            
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال البوست: {str(e)}")
            # محاولة إرسال كل وسيط منفرداً
            await self.send_separately(video_path, logo_path)
    
    async def send_separately(self, video_path: Path, logo_path: Path = None):
        """إرسال الصورة والفيديو منفصلين إذا فشلت المحاولة الأولى"""
        try:
            logger.info("🔄 محاولة الإرسال المنفصل...")
            
            # إرسال الصورة أولاً
            if logo_path and logo_path.exists():
                await self.client.send_file(
                    self.channel,
                    logo_path,
                    caption=""
                )
                logger.info("✅ تم إرسال الصورة")
                await asyncio.sleep(1)
            
            # إرسال الفيديو مع الوصف
            await self.client.send_file(
                self.channel,
                video_path,
                caption=self.caption if self.caption else "",
                supports_streaming=True
            )
            logger.info("✅ تم إرسال الفيديو")
            
        except Exception as e:
            logger.error(f"❌ فشل الإرسال المنفصل أيضاً: {str(e)}")
            raise
    
    async def download_logo(self) -> Path:
        """تحميل الشعار"""
        if not self.logo_url:
            return None
        
        return await self.download_file(self.logo_url, is_logo=True)
    
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
            
            # إرسال الحلقات في مجموعات
            for i in range(0, len(video_paths), 10):
                batch = video_paths[i:i+10]
                
                logger.info(f"   📦 مجموعة {i//10 + 1}: {len(batch)} حلقة")
                
                for j, video_path in enumerate(batch):
                    try:
                        await self.client.send_file(
                            self.channel,
                            video_path,
                            caption=f"الحلقة {i + j + 1}",
                            supports_streaming=True
                        )
                        logger.info(f"   ✅ تم إرسال الحلقة {i + j + 1}")
                        
                        # انتظار بين الحلقات
                        if j < len(batch) - 1:
                            await asyncio.sleep(1)
                    except Exception as e:
                        logger.error(f"   ❌ فشل إرسال الحلقة {i + j + 1}: {str(e)}")
                
                # انتظار بين المجموعات
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
            
            # الإرسال حسب النوع
            if self.media_type == "أفلام":
                await self.send_movie_with_logo(video_paths[0], logo_path)
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
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
