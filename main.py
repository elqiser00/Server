#!/usr/bin/env python3
"""
Telegram Media Uploader Bot - النسخة المبسطة
"""

import os
import sys
import asyncio
import logging
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
import mimetypes
import re

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SimpleTelegramUploader:
    def __init__(self):
        # قراءة الأسرار من البيئة
        self.api_id = os.getenv('TELEGRAM_API_ID')
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.phone = os.getenv('TELEGRAM_PHONE')
        self.password = os.getenv('TELEGRAM_PASSWORD', '')
        self.session_string = os.getenv('TELEGRAM_SESSION_STRING', '')
        
        # قراءة المدخلات من GitHub Actions
        self.is_github = os.getenv('GITHUB_ACTIONS') == 'true'
        self.channel_url = os.getenv('INPUT_CHANNEL_URL', '')
        self.media_type = os.getenv('INPUT_MEDIA_TYPE', 'أفلام')
        self.logo_url = os.getenv('INPUT_LOGO_URL', '')
        self.caption = os.getenv('INPUT_CAPTION', '')
        video_paths_input = os.getenv('INPUT_VIDEO_PATHS', '')
        
        # تقسيم روابط الفيديو
        self.video_urls = []
        if video_paths_input:
            for url in video_paths_input.split(','):
                url = url.strip()
                if url:
                    self.video_urls.append(url)
        
        # إعداد SSL
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        # مجلد التنزيلات
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)
        
        # العميل
        self.client = None
        self.channel = None
    
    def validate_inputs(self) -> bool:
        """التحقق من صحة المدخلات"""
        logger.info("🔍 التحقق من البيانات...")
        
        # التحقق من بيانات التليجرام
        if not self.api_id or not self.api_hash or not self.phone:
            logger.error("❌ بيانات التليجرام ناقصة!")
            logger.error("   تأكد من تعيين: TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE")
            return False
        
        # التحقق من رابط القناة
        if not self.channel_url:
            logger.error("❌ رابط القناة مطلوب!")
            return False
        
        # التحقق من روابط الفيديو
        if not self.video_urls:
            logger.error("❌ روابط الفيديو مطلوبة!")
            return False
        
        logger.info(f"✅ القناة: {self.channel_url}")
        logger.info(f"✅ النوع: {self.media_type}")
        logger.info(f"✅ عدد الفيديوهات: {len(self.video_urls)}")
        logger.info(f"✅ الكبشر: {self.caption[:50]}..." if self.caption else "✅ الكبشر: لا يوجد")
        
        return True
    
    def extract_filename(self, url: str) -> str:
        """استخراج اسم الملف من الرابط"""
        try:
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path)
            
            if not filename:
                filename = "video.mp4"
            
            # تنظيف اسم الملف
            filename = urllib.parse.unquote(filename)
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            
            # إضافة امتداد إذا لم يكن موجود
            if '.' not in filename:
                filename += '.mp4'
            
            return filename
        except:
            return "video.mp4"
    
    async def download_file(self, url: str) -> Path:
        """تحميل ملف من رابط"""
        filename = self.extract_filename(url)
        filepath = self.download_dir / filename
        
        logger.info(f"📥 جاري تحميل: {filename}")
        
        try:
            connector = aiohttp.TCPConnector(ssl=self.ssl_context)
            timeout = aiohttp.ClientTimeout(total=3600)  # ساعة كاملة
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        total_size = int(response.headers.get('content-length', 0))
                        
                        with open(filepath, 'wb') as f:
                            downloaded = 0
                            async for chunk in response.content.iter_chunked(1024*1024):  # 1MB chunks
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    
                                    if total_size > 0:
                                        percent = (downloaded / total_size) * 100
                                        if int(percent) % 20 == 0:  # كل 20%
                                            mb_downloaded = downloaded / 1024 / 1024
                                            mb_total = total_size / 1024 / 1024
                                            logger.info(f"   📊 {percent:.0f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)")
                        
                        size_mb = filepath.stat().st_size / 1024 / 1024
                        logger.info(f"✅ تم التحميل: {filename} ({size_mb:.1f} MB)")
                        return filepath
                    else:
                        logger.error(f"❌ فشل التحميل (HTTP {response.status})")
                        raise Exception(f"HTTP {response.status}")
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل {filename}: {str(e)}")
            raise
    
    async def download_logo(self) -> Path:
        """تحميل الشعار"""
        if not self.logo_url:
            return None
        
        logger.info(f"🎨 جاري تحميل الشعار...")
        
        try:
            connector = aiohttp.TCPConnector(ssl=self.ssl_context)
            
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(self.logo_url) as response:
                    if response.status == 200:
                        # تحديد الامتداد
                        content_type = response.headers.get('Content-Type', '')
                        if 'image/' in content_type:
                            ext = mimetypes.guess_extension(content_type) or '.jpg'
                        else:
                            ext = '.jpg'
                        
                        logo_path = self.download_dir / f"logo{ext}"
                        
                        with open(logo_path, 'wb') as f:
                            f.write(await response.read())
                        
                        size_kb = logo_path.stat().st_size / 1024
                        logger.info(f"✅ تم تحميل الشعار ({size_kb:.1f} KB)")
                        return logo_path
                    else:
                        logger.error(f"❌ فشل تحميل الشعار (HTTP {response.status})")
                        return None
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل الشعار: {str(e)}")
            return None
    
    async def connect_telegram(self) -> bool:
        """الاتصال بتليجرام"""
        try:
            logger.info("🔗 جاري الاتصال بالتليجرام...")
            
            # إنشاء الجلسة
            session_name = 'session'
            if self.session_string:
                session_name = self.session_string
            
            self.client = TelegramClient(
                session=session_name,
                api_id=int(self.api_id),
                api_hash=self.api_hash
            )
            
            # البدء
            await self.client.start(
                phone=self.phone,
                password=self.password if self.password else None
            )
            
            logger.info("✅ تم الاتصال بالتليجرام")
            
            # الحصول على القناة
            channel_id = self.channel_url.strip()
            
            # تنظيف الرابط
            if 't.me/' in channel_id:
                channel_id = channel_id.split('t.me/')[-1]
            if channel_id.startswith('+'):
                channel_id = channel_id[1:]
            if channel_id.startswith('@'):
                channel_id = channel_id[1:]
            
            logger.info(f"🔍 البحث عن القناة: {channel_id}")
            self.channel = await self.client.get_entity(channel_id)
            logger.info(f"✅ تم العثور على القناة: {self.channel.title}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ خطأ في الاتصال: {str(e)}")
            return False
    
    async def upload_file(self, filepath: Path, is_video: bool = True):
        """رفع ملف إلى تليجرام"""
        try:
            filename = filepath.name
            size_mb = filepath.stat().st_size / 1024 / 1024
            logger.info(f"⬆️  جاري رفع: {filename} ({size_mb:.1f} MB)")
            
            # رفع الملف
            file = await self.client.upload_file(filepath)
            
            if is_video:
                attributes = [DocumentAttributeVideo(duration=0, w=0, h=0, supports_streaming=True)]
                mime_type = "video/mp4"
            else:
                attributes = []
                mime_type = "image/jpeg"
            
            return {
                'file': file,
                'mime_type': mime_type,
                'attributes': attributes,
                'is_video': is_video
            }
            
        except FloodWaitError as e:
            logger.warning(f"⏳ انتظر {e.seconds} ثانية...")
            await asyncio.sleep(e.seconds)
            return await self.upload_file(filepath, is_video)
        except Exception as e:
            logger.error(f"❌ خطأ في رفع {filepath.name}: {str(e)}")
            raise
    
    async def send_movie(self, video_path: Path, logo_path: Path = None):
        """إرسال فيلم"""
        try:
            media_items = []
            
            # رفع الصورة إذا كانت موجودة وصغيرة
            if logo_path and logo_path.exists():
                logo_size = logo_path.stat().st_size
                if logo_size < 10 * 1024 * 1024:  # أقل من 10MB
                    logo_data = await self.upload_file(logo_path, is_video=False)
                    if logo_data:
                        media_items.append(InputSingleMedia(
                            media=InputMediaUploadedDocument(
                                file=logo_data['file'],
                                mime_type=logo_data['mime_type'],
                                attributes=logo_data['attributes'],
                                force_file=False
                            ),
                            message="",
                            entities=None
                        ))
                        logger.info("🖼️  تم إضافة الصورة")
                else:
                    # رفع الصورة الكبيرة منفصلة
                    await self.client.send_file(
                        self.channel,
                        logo_path,
                        caption=self.caption
                    )
                    logger.info("🖼️  تم إرسال الصورة الكبيرة منفصلة")
            
            # رفع الفيديو
            video_data = await self.upload_file(video_path, is_video=True)
            if video_data:
                media_items.append(InputSingleMedia(
                    media=InputMediaUploadedDocument(
                        file=video_data['file'],
                        mime_type=video_data['mime_type'],
                        attributes=video_data['attributes'],
                        force_file=False
                    ),
                    message=self.caption if self.caption else "",
                    entities=None
                ))
            
            # إرسال
            if media_items:
                await self.client(SendMultiMediaRequest(
                    peer=self.channel,
                    multi_media=media_items,
                    silent=None,
                    reply_to_msg_id=None,
                    schedule_date=None
                ))
                
                logger.info("✅ تم نشر الفيلم بنجاح!")
                
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال الفيلم: {str(e)}")
            raise
    
    async def send_series(self, video_paths: list, logo_path: Path = None):
        """إرسال مسلسل"""
        try:
            # إرسال الصورة أولاً إذا كانت موجودة
            if logo_path and logo_path.exists():
                await self.client.send_file(
                    self.channel,
                    logo_path,
                    caption=self.caption
                )
                logger.info("✅ تم إرسال الصورة")
            
            # إرسال الحلقات في مجموعات
            for i in range(0, len(video_paths), 10):
                batch = video_paths[i:i+10]
                media_items = []
                
                for j, video_path in enumerate(batch):
                    video_data = await self.upload_file(video_path, is_video=True)
                    if video_data:
                        episode_num = i + j + 1
                        episode_caption = f"الحلقة {episode_num}"
                        
                        media_items.append(InputSingleMedia(
                            media=InputMediaUploadedDocument(
                                file=video_data['file'],
                                mime_type=video_data['mime_type'],
                                attributes=video_data['attributes'],
                                force_file=False
                            ),
                            message=episode_caption,
                            entities=None
                        ))
                
                # إرسال الدفعة
                if media_items:
                    await self.client(SendMultiMediaRequest(
                        peer=self.channel,
                        multi_media=media_items,
                        silent=None,
                        reply_to_msg_id=None,
                        schedule_date=None
                    ))
                    
                    logger.info(f"✅ تم نشر {len(media_items)} حلقة")
                    
                    # انتظار بين الدفعات
                    if i + 10 < len(video_paths):
                        await asyncio.sleep(3)
            
            logger.info(f"🎉 تم نشر جميع الحلقات ({len(video_paths)} حلقة)")
            
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال المسلسل: {str(e)}")
            raise
    
    def cleanup(self, files: list):
        """تنظيف الملفات المؤقتة"""
        for file in files:
            try:
                if file and file.exists():
                    file.unlink()
                    logger.debug(f"🧹 تم حذف: {file.name}")
            except:
                pass
    
    async def run(self):
        """تشغيل البرنامج"""
        print("\n" + "="*60)
        print("🚀 Telegram Media Uploader v3.0")
        print("="*60 + "\n")
        
        # التحقق من البيانات
        if not self.validate_inputs():
            return False
        
        # الاتصال بتليجرام
        if not await self.connect_telegram():
            return False
        
        try:
            # تحميل الشعار
            logo_path = await self.download_logo()
            
            # تحميل الفيديوهات
            video_paths = []
            for url in self.video_urls:
                try:
                    video_path = await self.download_file(url)
                    video_paths.append(video_path)
                except Exception as e:
                    logger.error(f"❌ فشل تحميل: {url}")
                    continue
            
            if not video_paths:
                logger.error("❌ لم يتم تحميل أي فيديو!")
                return False
            
            # الإرسال حسب النوع
            if self.media_type == "أفلام":
                await self.send_movie(video_paths[0], logo_path)
            else:  # مسلسلات
                await self.send_series(video_paths, logo_path)
            
            # التنظيف
            self.cleanup(video_paths)
            if logo_path:
                self.cleanup([logo_path])
            
            return True
            
        except KeyboardInterrupt:
            logger.info("⏹️  تم الإيقاف")
            return False
        except Exception as e:
            logger.error(f"❌ خطأ غير متوقع: {str(e)}")
            return False
        finally:
            # إغلاق الاتصال
            if self.client:
                await self.client.disconnect()
                logger.info("✅ تم إغلاق الاتصال")

async def main():
    """الدالة الرئيسية"""
    uploader = SimpleTelegramUploader()
    success = await uploader.run()
    
    if success:
        print("\n" + "="*60)
        print("✅ تم الانتهاء بنجاح!")
        print("="*60 + "\n")
        sys.exit(0)
    else:
        print("\n" + "="*60)
        print("❌ فشل العملية!")
        print("="*60 + "\n")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
