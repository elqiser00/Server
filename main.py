#!/usr/bin/env python3
"""
Telegram Media Uploader Bot - النسخة المحسنة
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
        logging.FileHandler('uploader.log')
    ]
)
logger = logging.getLogger(__name__)

class TelegramUploader:
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
        
        # مجلدات
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)
        
        self.session_dir = Path("sessions")
        self.session_dir.mkdir(exist_ok=True)
        
        # العميل
        self.client = None
        self.channel = None
    
    def print_banner(self):
        """طباعة بانر البرنامج"""
        print("\n" + "="*60)
        print("🚀 TELEGRAM MEDIA UPLOADER")
        print("="*60)
        print(f"📢 القناة: {self.channel_url}")
        print(f"🎬 النوع: {self.media_type}")
        print(f"📁 الملفات: {len(self.video_urls)}")
        if self.caption:
            print(f"📝 الوصف: {self.caption[:50]}...")
        print("="*60 + "\n")
    
    def validate_inputs(self) -> bool:
        """التحقق من صحة المدخلات"""
        logger.info("🔍 جاري التحقق من البيانات...")
        
        errors = []
        
        # بيانات التليجرام
        if not self.api_id:
            errors.append("TELEGRAM_API_ID")
        if not self.api_hash:
            errors.append("TELEGRAM_API_HASH")
        if not self.phone:
            errors.append("TELEGRAM_PHONE")
        
        if errors:
            logger.error(f"❌ بيانات التليجرام ناقصة: {', '.join(errors)}")
            logger.error("   ⚠️  تأكد من إضافة الأسرار في GitHub Secrets")
            return False
        
        # رابط القناة
        if not self.channel_url:
            logger.error("❌ رابط القناة مطلوب!")
            return False
        
        # روابط الفيديو
        if not self.video_urls:
            logger.error("❌ روابط الفيديو مطلوبة!")
            return False
        
        logger.info("✅ جميع البيانات صحيحة")
        return True
    
    async def setup_telegram_client(self) -> bool:
        """إعداد وتوصيل عميل التليجرام"""
        try:
            logger.info("🔗 جاري الاتصال بالتليجرام...")
            
            # اسم ملف الجلسة
            if self.session_string:
                session_name = self.session_string
            else:
                # استخدام رقم الهاتف كاسم للجلسة
                session_name = self.phone.replace('+', '').replace(' ', '')
            
            session_file = self.session_dir / f"{session_name}.session"
            
            logger.info(f"📁 جلسة: {session_file.name}")
            
            # إنشاء العميل
            self.client = TelegramClient(
                str(session_file),
                api_id=int(self.api_id),
                api_hash=self.api_hash,
                device_model="Telegram Uploader",
                system_version="Linux",
                app_version="1.0.0"
            )
            
            # الاتصال
            await self.client.connect()
            
            # التحقق إذا كنا بحاجة للمصادقة
            if not await self.client.is_user_authorized():
                logger.info("🔐 جاري تسجيل الدخول...")
                
                # إرسال الرمز
                await self.client.send_code_request(self.phone)
                
                if self.is_github:
                    # في GitHub Actions، نحتاج لطريقة مختلفة
                    logger.info("⚠️  في بيئة GitHub، تأكد من:")
                    logger.info("   1. استخدام TELEGRAM_SESSION_STRING")
                    logger.info("   2. أو تفعيل الجلسة مسبقاً محلياً")
                    return False
                else:
                    # في الوضع التفاعلي
                    code = input("📱 أدخل الرمز الذي وصلك على تليجرام: ").strip()
                    
                    try:
                        await self.client.sign_in(self.phone, code)
                        logger.info("✅ تم تسجيل الدخول")
                    except SessionPasswordNeededError:
                        if self.password:
                            await self.client.sign_in(password=self.password)
                            logger.info("✅ تم تسجيل الدخول بكلمة المرور")
                        else:
                            logger.error("❌ كلمة مرور الحساب مطلوبة!")
                            return False
            
            logger.info("✅ تم الاتصال بتليجرام بنجاح")
            
            # الحصول على معلومات المستخدم
            me = await self.client.get_me()
            logger.info(f"👤 المستخدم: {me.first_name} (@{me.username})")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ خطأ في الاتصال: {str(e)}")
            
            # نصائح استكشاف الأخطاء
            if "database" in str(e).lower() or "sqlite" in str(e).lower():
                logger.error("💡 الحل: حاول حذف ملفات الجلسة وإعادة المحاولة")
                logger.error("     rm -rf sessions/*.session")
            
            return False
    
    async def get_channel(self) -> bool:
        """الحصول على كيان القناة"""
        try:
            logger.info(f"🔍 جاري البحث عن القناة...")
            
            # تنظيف رابط القناة
            channel_id = self.channel_url.strip()
            
            # إزالة https://t.me/
            if 't.me/' in channel_id:
                channel_id = channel_id.split('t.me/')[-1]
            
            # إزالة الإشارة @
            if channel_id.startswith('@'):
                channel_id = channel_id[1:]
            
            # إزالة علامة الزائد
            if channel_id.startswith('+'):
                channel_id = channel_id[1:]
            
            logger.info(f"   المعرف النظيف: {channel_id}")
            
            # محاولة الحصول على القناة
            try:
                self.channel = await self.client.get_entity(channel_id)
            except:
                # محاولة أخرى مع @
                if not channel_id.startswith('@'):
                    try:
                        self.channel = await self.client.get_entity(f"@{channel_id}")
                    except:
                        self.channel = await self.client.get_entity(f"https://t.me/{channel_id}")
            
            logger.info(f"✅ تم العثور على القناة: {self.channel.title}")
            logger.info(f"   👥 المشاركين: {getattr(self.channel, 'participants_count', 'غير معروف')}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ خطأ في إيجاد القناة: {str(e)}")
            logger.error(f"   ⚠️  تأكد من:")
            logger.error(f"     1. الرابط صحيح: {self.channel_url}")
            logger.error(f"     2. الحساب عضو في القناة")
            logger.error(f"     3. الحساب لديه صلاحية النشر")
            return False
    
    def extract_filename(self, url: str) -> str:
        """استخراج اسم الملف من الرابط"""
        try:
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path)
            
            if not filename or filename == '/':
                # إنشاء اسم من الرابط
                domain = parsed.netloc.replace('.', '_')
                filename = f"{domain}_video.mp4"
            
            # تنظيف الاسم
            filename = urllib.parse.unquote(filename)
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            
            # إضافة امتداد إذا لم يكن موجود
            if '.' not in filename:
                filename += '.mp4'
            
            # تقصير إذا كان طويلاً
            if len(filename) > 100:
                name, ext = os.path.splitext(filename)
                filename = name[:95] + ext
            
            return filename
        except:
            return "video.mp4"
    
    async def download_file(self, url: str) -> Path:
        """تحميل ملف من رابط"""
        filename = self.extract_filename(url)
        filepath = self.download_dir / filename
        
        # إذا كان الملف موجود مسبقاً
        if filepath.exists():
            size_mb = filepath.stat().st_size / 1024 / 1024
            logger.info(f"📁 الملف موجود مسبقاً: {filename} ({size_mb:.1f} MB)")
            return filepath
        
        logger.info(f"📥 جاري تحميل: {filename}")
        logger.info(f"   🔗 من: {url[:80]}...")
        
        try:
            connector = aiohttp.TCPConnector(ssl=self.ssl_context)
            timeout = aiohttp.ClientTimeout(total=3600, sock_connect=30, sock_read=300)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
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
                            last_percent = 0
                            
                            async for chunk in response.content.iter_chunked(1024*512):  # 512KB chunks
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    
                                    if total_size > 0:
                                        percent = (downloaded / total_size) * 100
                                        if int(percent) >= last_percent + 10:
                                            mb_downloaded = downloaded / 1024 / 1024
                                            mb_total = total_size / 1024 / 1024
                                            logger.info(f"   📊 {int(percent)}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)")
                                            last_percent = int(percent)
                        
                        # التحقق من حجم الملف
                        if filepath.exists():
                            size_mb = filepath.stat().st_size / 1024 / 1024
                            if size_mb > 0:
                                logger.info(f"✅ تم التحميل: {filename} ({size_mb:.1f} MB)")
                                return filepath
                            else:
                                logger.error(f"❌ الملف فارغ: {filename}")
                                filepath.unlink(missing_ok=True)
                                raise Exception("الملف فارغ")
                        else:
                            logger.error(f"❌ فشل حفظ الملف: {filename}")
                            raise Exception("فشل الحفظ")
                    else:
                        logger.error(f"❌ فشل التحميل (HTTP {response.status})")
                        raise Exception(f"HTTP {response.status}")
                        
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل {filename}: {str(e)}")
            if filepath.exists():
                filepath.unlink(missing_ok=True)
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
                            # من الرابط
                            if '.' in self.logo_url:
                                ext = '.' + self.logo_url.split('.')[-1].split('?')[0]
                                if ext.lower() not in ['.jpg', '.jpeg', '.png', '.webp']:
                                    ext = '.jpg'
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
    
    async def upload_file(self, filepath: Path, is_video: bool = True):
        """رفع ملف إلى تليجرام"""
        try:
            filename = filepath.name
            size_mb = filepath.stat().st_size / 1024 / 1024
            
            logger.info(f"⬆️  جاري رفع: {filename} ({size_mb:.1f} MB)")
            
            # رفع الملف مع عرض التقدم للملفات الكبيرة
            if size_mb > 50:
                logger.info(f"   ⏳ قد يستغرق رفع الملف الكبير بعض الوقت...")
            
            file = await self.client.upload_file(
                filepath,
                progress_callback=self.upload_progress if size_mb > 10 else None
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
                mime_type = "image/jpeg"
            
            logger.info(f"✅ تم رفع: {filename}")
            
            return {
                'file': file,
                'mime_type': mime_type,
                'attributes': attributes,
                'is_video': is_video
            }
            
        except FloodWaitError as e:
            wait_time = e.seconds
            logger.warning(f"⏳ FloodWait: انتظر {wait_time} ثانية...")
            await asyncio.sleep(wait_time)
            return await self.upload_file(filepath, is_video)
        except Exception as e:
            logger.error(f"❌ خطأ في رفع {filepath.name}: {str(e)}")
            raise
    
    def upload_progress(self, current: int, total: int):
        """عرض تقدم الرفع"""
        percent = (current / total) * 100
        if int(percent) % 20 == 0:  # كل 20%
            mb_current = current / 1024 / 1024
            mb_total = total / 1024 / 1024
            logger.info(f"   📤 رفع: {int(percent)}% ({mb_current:.1f}/{mb_total:.1f} MB)")
    
    async def send_movie(self, video_path: Path, logo_path: Path = None):
        """إرسال فيلم"""
        try:
            logger.info("🎬 جاري إرسال الفيلم...")
            
            media_items = []
            
            # رفع الصورة إذا كانت موجودة
            if logo_path and logo_path.exists():
                logo_size = logo_path.stat().st_size
                if logo_size < 5 * 1024 * 1024:  # أقل من 5MB
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
                        logger.info("🖼️  تم إضافة الصورة مع الفيديو")
                else:
                    # إرسال الصورة منفصلة
                    await self.client.send_file(
                        self.channel,
                        logo_path,
                        caption=self.caption
                    )
                    logger.info("🖼️  تم إرسال الصورة منفصلة")
            
            # رفع الفيديو
            video_data = await self.upload_file(video_path, is_video=True)
            
            # إضافة الفيديو مع الوصف
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
            
            # إرسال الوسائط
            if media_items:
                result = await self.client(SendMultiMediaRequest(
                    peer=self.channel,
                    multi_media=media_items,
                    silent=None,
                    reply_to_msg_id=None,
                    schedule_date=None
                ))
                
                logger.info(f"✅ تم نشر الفيلم بنجاح! (ID: {result.id})")
                
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال الفيلم: {str(e)}")
            raise
    
    async def send_series(self, video_paths: list, logo_path: Path = None):
        """إرسال مسلسل"""
        try:
            logger.info(f"📺 جاري إرسال {len(video_paths)} حلقة...")
            
            # إرسال الصورة أولاً إذا كانت موجودة
            if logo_path and logo_path.exists():
                await self.client.send_file(
                    self.channel,
                    logo_path,
                    caption=self.caption if self.caption else "مسلسل جديد 🎬"
                )
                logger.info("✅ تم إرسال الصورة")
                await asyncio.sleep(1)
            
            # إرسال الحلقات في مجموعات
            total_sent = 0
            for i in range(0, len(video_paths), 10):
                batch = video_paths[i:i+10]
                media_items = []
                
                logger.info(f"   📦 مجموعة {i//10 + 1}: {len(batch)} حلقة")
                
                for j, video_path in enumerate(batch):
                    video_data = await self.upload_file(video_path, is_video=True)
                    
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
                    
                    total_sent += len(media_items)
                    logger.info(f"   ✅ تم نشر {len(media_items)} حلقة (المجموع: {total_sent})")
                    
                    # انتظار بين الدفعات
                    if i + 10 < len(video_paths):
                        await asyncio.sleep(2)
            
            logger.info(f"🎉 تم نشر جميع الحلقات ({total_sent} حلقة)")
            
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال المسلسل: {str(e)}")
            raise
    
    def cleanup_files(self, files: list):
        """حذف الملفات المؤقتة"""
        for file in files:
            if file and isinstance(file, Path) and file.exists():
                try:
                    file.unlink()
                    logger.debug(f"🧹 تم حذف: {file.name}")
                except:
                    pass
    
    async def run(self):
        """تشغيل البرنامج الرئيسي"""
        self.print_banner()
        
        # التحقق من البيانات
        if not self.validate_inputs():
            return False
        
        # الاتصال بتليجرام
        if not await self.setup_telegram_client():
            return False
        
        # الحصول على القناة
        if not await self.get_channel():
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
                    logger.error(f"❌ تخطي: {url} - {str(e)}")
                    continue
            
            if not video_paths:
                logger.error("❌ لم يتم تحميل أي فيديو!")
                return False
            
            logger.info(f"✅ جاهز للرفع: {len(video_paths)} ملف")
            
            # الإرسال حسب النوع
            if self.media_type == "أفلام":
                await self.send_movie(video_paths[0], logo_path)
            else:  # مسلسلات
                await self.send_series(video_paths, logo_path)
            
            # تنظيف الملفات
            self.cleanup_files(video_paths)
            if logo_path:
                self.cleanup_files([logo_path])
            
            logger.info("✨ تم الانتهاء بنجاح!")
            return True
            
        except KeyboardInterrupt:
            logger.info("⏹️  تم إيقاف العملية")
            return False
        except Exception as e:
            logger.error(f"❌ خطأ غير متوقع: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
        finally:
            # إغلاق الاتصال
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
        print("="*60 + "\n")
        sys.exit(0)
    else:
        print("\n" + "="*60)
        print("❌ فشلت عملية الرفع")
        print("="*60 + "\n")
        sys.exit(1)

if __name__ == "__main__":
    # تشغيل البرنامج
    asyncio.run(main())
