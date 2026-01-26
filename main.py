#!/usr/bin/env python3
"""
Telegram Media Uploader Bot - النسخة النهائية
"""

import os
import sys
import asyncio
import logging
import json
from pathlib import Path
import urllib.parse
import ssl
import aiohttp
from telethon import TelegramClient
from telethon.errors import RPCError, FloodWaitError, SessionPasswordNeededError
from telethon.tl.types import InputMediaUploadedDocument
from telethon.tl.functions.messages import SendMultiMediaRequest
from telethon.tl.types import InputSingleMedia
from telethon.tl.types import DocumentAttributeVideo
import mimetypes
import re

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('uploader.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class TelegramUploader:
    def __init__(self):
        # قراءة الأسرار
        self.load_secrets()
        
        # قراءة المدخلات
        self.load_inputs()
        
        # إعداد SSL
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        # مجلدات
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)
        
        self.session_dir = Path("sessions")
        self.session_dir.mkdir(exist_ok=True)
        
        # العميل
        self.client = None
        self.channel = None
        
        # إحصائيات
        self.stats = {
            'downloaded': 0,
            'uploaded': 0,
            'errors': 0
        }
    
    def load_secrets(self):
        """تحميل الأسرار"""
        self.api_id = os.getenv('TELEGRAM_API_ID')
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.phone = os.getenv('TELEGRAM_PHONE')
        self.password = os.getenv('TELEGRAM_PASSWORD', '')
        self.session_string = os.getenv('TELEGRAM_SESSION_STRING', '')
        
        # تسجيل الأسرار (بدون عرض القيم الحساسة)
        logger.info("🔐 تحميل الأسرار...")
        logger.info(f"   📱 الهاتف: {self.phone}")
        logger.info(f"   📊 API ID: {'✓' if self.api_id else '✗'}")
        logger.info(f"   🔑 API Hash: {'✓' if self.api_hash else '✗'}")
        logger.info(f"   🔒 كلمة المرور: {'✓' if self.password else '✗'}")
        logger.info(f"   🗝️  سلسلة الجلسة: {'✓' if self.session_string else '✗'}")
    
    def load_inputs(self):
        """تحميل المدخلات"""
        self.channel_url = os.getenv('INPUT_CHANNEL_URL', '')
        self.media_type = os.getenv('INPUT_MEDIA_TYPE', 'أفلام')
        self.logo_url = os.getenv('INPUT_LOGO_URL', '')
        self.caption = os.getenv('INPUT_CAPTION', '')
        
        video_paths_input = os.getenv('INPUT_VIDEO_PATHS', '')
        self.video_urls = []
        
        if video_paths_input:
            for url in video_paths_input.split(','):
                url = url.strip()
                if url and url.startswith(('http://', 'https://')):
                    self.video_urls.append(url)
        
        logger.info("📥 تحميل المدخلات...")
        logger.info(f"   📢 القناة: {self.channel_url}")
        logger.info(f"   🎬 النوع: {self.media_type}")
        logger.info(f"   🖼️  الشعار: {self.logo_url if self.logo_url else 'لا يوجد'}")
        logger.info(f"   📝 الوصف: {self.caption[:50] + '...' if len(self.caption) > 50 else self.caption or 'لا يوجد'}")
        logger.info(f"   📁 الفيديوهات: {len(self.video_urls)}")
    
    def print_banner(self):
        """طباعة بانر"""
        banner = """
╔═══════════════════════════════════════════════════╗
║      🚀 TELEGRAM MEDIA UPLOADER v4.0      ║
║           أداة رفع الأفلام والمسلسلات           ║
╚═══════════════════════════════════════════════════╝
        """
        print(banner)
        print(f"📢 القناة: {self.channel_url}")
        print(f"🎬 النوع: {self.media_type}")
        print(f"📁 الملفات: {len(self.video_urls)}")
        if self.caption:
            print(f"📝 الوصف: {self.caption}")
        print("="*60)
    
    def validate_inputs(self) -> bool:
        """التحقق من صحة البيانات"""
        logger.info("🔍 جاري التحقق من البيانات...")
        
        errors = []
        
        # التحقق من بيانات التليجرام
        if not self.api_id or not self.api_hash or not self.phone:
            errors.append("بيانات التليجرام غير مكتملة")
            logger.error("❌ TELEGRAM_API_ID و TELEGRAM_API_HASH و TELEGRAM_PHONE مطلوبة")
        
        # التحقق من رابط القناة
        if not self.channel_url:
            errors.append("رابط القناة مطلوب")
            logger.error("❌ INPUT_CHANNEL_URL مطلوب")
        
        # التحقق من روابط الفيديو
        if not self.video_urls:
            errors.append("روابط الفيديو مطلوبة")
            logger.error("❌ INPUT_VIDEO_PATHS مطلوب")
        
        # التحقق من صحة الروابط
        valid_urls = []
        for url in self.video_urls:
            if url.startswith(('http://', 'https://')):
                valid_urls.append(url)
            else:
                logger.warning(f"⚠️  رابط غير صالح: {url}")
        
        if not valid_urls:
            errors.append("لا توجد روابط فيديو صالحة")
        
        self.video_urls = valid_urls
        
        if errors:
            logger.error(f"❌ وجدت {len(errors)} أخطاء:")
            for error in errors:
                logger.error(f"   • {error}")
            return False
        
        logger.info("✅ جميع البيانات صحيحة")
        return True
    
    async def create_telegram_client(self) -> bool:
        """إنشاء وتوصيل عميل التليجرام"""
        try:
            logger.info("🔗 جاري الاتصال بالتليجرام...")
            
            # استخدام سلسلة الجلسة إذا كانت متوفرة
            if self.session_string:
                logger.info("🗝️  استخدام سلسلة الجلسة...")
                try:
                    self.client = TelegramClient(
                        session=self.session_string,
                        api_id=int(self.api_id),
                        api_hash=self.api_hash,
                        device_model="Telegram Uploader",
                        system_version="Linux",
                        app_version="4.0.0"
                    )
                    await self.client.connect()
                    
                    # التحقق من الجلسة
                    if await self.client.is_user_authorized():
                        logger.info("✅ تم الاتصال باستخدام سلسلة الجلسة")
                        return True
                    else:
                        logger.warning("⚠️  سلسلة الجلسة غير صالحة")
                except Exception as e:
                    logger.warning(f"⚠️  فشل استخدام سلسلة الجلسة: {str(e)}")
            
            # استخدام ملف الجلسة
            session_name = self.phone.replace('+', '').replace(' ', '_')
            session_file = self.session_dir / f"{session_name}.session"
            
            logger.info(f"📁 استخدام ملف الجلسة: {session_file.name}")
            
            self.client = TelegramClient(
                str(session_file),
                api_id=int(self.api_id),
                api_hash=self.api_hash,
                device_model="Telegram Uploader",
                system_version="Linux",
                app_version="4.0.0"
            )
            
            await self.client.connect()
            
            # التحقق إذا كانت الجلسة مفعلة
            if await self.client.is_user_authorized():
                logger.info("✅ الجلسة مفعلة مسبقاً")
                return True
            
            # تسجيل الدخول
            logger.info("🔐 جاري تسجيل الدخول...")
            
            # في بيئة GitHub Actions، نحتاج لجلسة مسبقة
            if os.getenv('GITHUB_ACTIONS') == 'true':
                logger.error("❌ لا يمكن تسجيل الدخول في GitHub Actions")
                logger.error("💡 الحل: استخدم TELEGRAM_SESSION_STRING")
                return False
            
            # في الوضع المحلي
            await self.client.send_code_request(self.phone)
            code = input("📱 أدخل الرمز من تليجرام: ").strip()
            
            try:
                await self.client.sign_in(self.phone, code)
                logger.info("✅ تم تسجيل الدخول")
            except SessionPasswordNeededError:
                if self.password:
                    await self.client.sign_in(password=self.password)
                    logger.info("✅ تم تسجيل الدخول بكلمة المرور")
                else:
                    logger.error("❌ كلمة المرور مطلوبة!")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ خطأ في الاتصال: {str(e)}")
            return False
    
    async def get_channel_entity(self) -> bool:
        """الحصول على كيان القناة"""
        try:
            logger.info(f"🔍 جاري البحث عن القناة: {self.channel_url}")
            
            # تنظيف الرابط
            channel_id = self.channel_url.strip()
            
            # إزالة https://t.me/
            if 't.me/' in channel_id:
                channel_id = channel_id.split('t.me/')[-1]
            
            # إزالة @ أو +
            if channel_id.startswith(('@', '+')):
                channel_id = channel_id[1:]
            
            logger.info(f"   المعرف: {channel_id}")
            
            # محاولات متعددة
            attempts = [
                channel_id,
                f"@{channel_id}",
                f"https://t.me/{channel_id}",
                f"t.me/{channel_id}"
            ]
            
            for attempt in attempts:
                try:
                    self.channel = await self.client.get_entity(attempt)
                    logger.info(f"✅ تم العثور على القناة: {self.channel.title}")
                    
                    # التحقق من صلاحيات النشر
                    try:
                        permissions = await self.client.get_permissions(self.channel, await self.client.get_me())
                        if permissions.post_messages:
                            logger.info("✅ لديك صلاحية النشر")
                        else:
                            logger.warning("⚠️  قد لا تكون لديك صلاحية النشر")
                    except:
                        pass
                    
                    return True
                except:
                    continue
            
            logger.error("❌ لم أتمكن من إيجاد القناة")
            return False
            
        except Exception as e:
            logger.error(f"❌ خطأ في البحث عن القناة: {str(e)}")
            return False
    
    def extract_filename(self, url: str) -> str:
        """استخراج اسم الملف"""
        try:
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path)
            
            if not filename or filename == '/':
                # توليد اسم من المجال والتاريخ
                import hashlib
                import time
                domain = parsed.netloc.replace('.', '_')
                timestamp = int(time.time())
                hash_str = hashlib.md5(url.encode()).hexdigest()[:8]
                filename = f"{domain}_{timestamp}_{hash_str}.mp4"
            
            # تنظيف الاسم
            filename = urllib.parse.unquote(filename)
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            
            # إضافة امتداد
            if '.' not in filename:
                filename += '.mp4'
            
            return filename[:100]  # تقصير الاسم
            
        except:
            return f"video_{int(time.time())}.mp4"
    
    async def download_file(self, url: str, retry_count: int = 3) -> Path:
        """تحميل ملف مع إعادة المحاولة"""
        for attempt in range(retry_count):
            try:
                filename = self.extract_filename(url)
                filepath = self.download_dir / filename
                
                # إذا كان الملف موجوداً
                if filepath.exists():
                    size_mb = filepath.stat().st_size / 1024 / 1024
                    if size_mb > 0.1:  # أكثر من 100KB
                        logger.info(f"📁 موجود مسبقاً: {filename} ({size_mb:.1f} MB)")
                        return filepath
                
                logger.info(f"📥 [{attempt+1}/{retry_count}] جاري تحميل: {filename}")
                
                connector = aiohttp.TCPConnector(ssl=self.ssl_context)
                timeout = aiohttp.ClientTimeout(total=3600)
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': '*/*',
                    'Accept-Encoding': 'gzip, deflate'
                }
                
                async with aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    headers=headers
                ) as session:
                    
                    async with session.get(url) as response:
                        if response.status == 200:
                            total_size = int(response.headers.get('content-length', 0))
                            
                            with open(filepath, 'wb') as f:
                                downloaded = 0
                                last_log = 0
                                
                                async for chunk in response.content.iter_chunked(8192):
                                    if chunk:
                                        f.write(chunk)
                                        downloaded += len(chunk)
                                        
                                        # تسجيل التقدم كل 10%
                                        if total_size > 0:
                                            percent = (downloaded / total_size) * 100
                                            if int(percent) >= last_log + 10:
                                                mb_downloaded = downloaded / 1024 / 1024
                                                mb_total = total_size / 1024 / 1024
                                                logger.info(f"   📊 {int(percent)}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)")
                                                last_log = int(percent)
                            
                            # التحقق من الملف
                            if filepath.exists() and filepath.stat().st_size > 0:
                                size_mb = filepath.stat().st_size / 1024 / 1024
                                self.stats['downloaded'] += 1
                                logger.info(f"✅ تم التحميل: {filename} ({size_mb:.1f} MB)")
                                return filepath
                            else:
                                raise Exception("الملف فارغ أو غير موجود")
                        else:
                            raise Exception(f"HTTP {response.status}")
                            
            except Exception as e:
                logger.warning(f"⚠️  محاولة {attempt+1} فشلت: {str(e)}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2)
                else:
                    raise Exception(f"فشل التحميل بعد {retry_count} محاولات: {str(e)}")
        
        raise Exception("فشل التحميل")
    
    async def upload_to_telegram(self, filepath: Path, is_video: bool = True):
        """رفع ملف إلى تليجرام"""
        try:
            filename = filepath.name
            size_mb = filepath.stat().st_size / 1024 / 1024
            
            logger.info(f"⬆️  جاري رفع: {filename} ({size_mb:.1f} MB)")
            
            file = await self.client.upload_file(
                filepath,
                progress_callback=self.upload_progress if size_mb > 5 else None
            )
            
            if is_video:
                attributes = [DocumentAttributeVideo(
                    duration=0, w=0, h=0, supports_streaming=True
                )]
                mime_type = "video/mp4"
            else:
                attributes = []
                mime_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
            
            self.stats['uploaded'] += 1
            
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
            return await self.upload_to_telegram(filepath, is_video)
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"❌ خطأ في الرفع: {str(e)}")
            raise
    
    def upload_progress(self, current: int, total: int):
        """عرض تقدم الرفع"""
        percent = (current / total) * 100
        if int(percent) % 20 == 0:
            mb_current = current / 1024 / 1024
            mb_total = total / 1024 / 1024
            logger.info(f"   📤 {int(percent)}% ({mb_current:.1f}/{mb_total:.1f} MB)")
    
    async def process_upload(self):
        """معالجة عملية الرفع"""
        try:
            # تحميل الشعار
            logo_path = None
            if self.logo_url:
                try:
                    logo_path = await self.download_file(self.logo_url, retry_count=2)
                except Exception as e:
                    logger.warning(f"⚠️  فشل تحميل الشعار: {str(e)}")
            
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
                raise Exception("لم يتم تحميل أي فيديو")
            
            logger.info(f"✅ جاهز للرفع: {len(video_paths)} ملف")
            
            # رفع حسب النوع
            if self.media_type == "أفلام" and video_paths:
                await self.send_movie(video_paths[0], logo_path)
            elif self.media_type == "مسلسلات":
                await self.send_series(video_paths, logo_path)
            
            # تنظيف
            self.cleanup_files(video_paths + ([logo_path] if logo_path else []))
            
        except Exception as e:
            logger.error(f"❌ خطأ في العملية: {str(e)}")
            raise
    
    async def send_movie(self, video_path: Path, logo_path: Path = None):
        """إرسال فيلم"""
        logger.info("🎬 جاري إرسال الفيلم...")
        
        media_items = []
        
        # الصورة إذا كانت موجودة
        if logo_path and logo_path.exists():
            try:
                logo_media = await self.upload_to_telegram(logo_path, is_video=False)
                media_items.append(InputSingleMedia(
                    media=logo_media,
                    message="",
                    entities=None
                ))
                logger.info("🖼️  تم إضافة الصورة")
            except:
                pass
        
        # الفيديو
        video_media = await self.upload_to_telegram(video_path, is_video=True)
        
        media_items.append(InputSingleMedia(
            media=video_media,
            message=self.caption if self.caption else "",
            entities=None
        ))
        
        # الإرسال
        result = await self.client(SendMultiMediaRequest(
            peer=self.channel,
            multi_media=media_items,
            silent=None,
            reply_to_msg_id=None,
            schedule_date=None
        ))
        
        logger.info(f"✅ تم نشر الفيلم! (Message ID: {result.id})")
    
    async def send_series(self, video_paths: list, logo_path: Path = None):
        """إرسال مسلسل"""
        logger.info(f"📺 جاري إرسال {len(video_paths)} حلقة...")
        
        # الصورة أولاً
        if logo_path and logo_path.exists():
            try:
                await self.client.send_file(
                    self.channel,
                    logo_path,
                    caption=self.caption if self.caption else "مسلسل جديد 🎬"
                )
                logger.info("✅ تم إرسال الصورة")
                await asyncio.sleep(1)
            except:
                pass
        
        # الحلقات في مجموعات
        for i in range(0, len(video_paths), 10):
            batch = video_paths[i:i+10]
            media_items = []
            
            logger.info(f"   📦 مجموعة {i//10 + 1}: {len(batch)} حلقة")
            
            for j, video_path in enumerate(batch):
                video_media = await self.upload_to_telegram(video_path, is_video=True)
                
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
                    reply_to_msg_id=None,
                    schedule_date=None
                ))
                
                logger.info(f"   ✅ تم نشر {len(media_items)} حلقة")
                
                # انتظار
                if i + 10 < len(video_paths):
                    await asyncio.sleep(3)
        
        logger.info(f"🎉 تم نشر {len(video_paths)} حلقة")
    
    def cleanup_files(self, files: list):
        """تنظيف الملفات"""
        for file in files:
            if file and file.exists():
                try:
                    file.unlink()
                except:
                    pass
    
    def print_stats(self):
        """طباعة الإحصائيات"""
        logger.info("📊 الإحصائيات النهائية:")
        logger.info(f"   📥 تم تنزيل: {self.stats['downloaded']}")
        logger.info(f"   📤 تم رفع: {self.stats['uploaded']}")
        logger.info(f"   ❌ أخطاء: {self.stats['errors']}")
    
    async def run(self):
        """تشغيل البرنامج"""
        self.print_banner()
        
        # التحقق
        if not self.validate_inputs():
            return False
        
        # الاتصال
        if not await self.create_telegram_client():
            return False
        
        # القناة
        if not await self.get_channel_entity():
            return False
        
        try:
            # التنفيذ
            await self.process_upload()
            
            # الإحصائيات
            self.print_stats()
            
            return True
            
        except KeyboardInterrupt:
            logger.info("⏹️  تم الإيقاف")
            return False
        except Exception as e:
            logger.error(f"❌ خطأ: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
        finally:
            # إغلاق
            if self.client:
                await self.client.disconnect()
                logger.info("🔌 تم إغلاق الاتصال")

async def main():
    """الدالة الرئيسية"""
    uploader = TelegramUploader()
    
    try:
        success = await uploader.run()
        return 0 if success else 1
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
