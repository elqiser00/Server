#!/usr/bin/env python3
"""
Telegram Media Uploader Bot
لرفع الأفلام والمسلسلات على قناة التليجرام
"""

import os
import sys
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import urllib.parse
import ssl
import aiohttp
from telethon import TelegramClient
from telethon.errors import RPCError, FloodWaitError
from telethon.tl.types import InputMediaUploadedDocument, InputMediaUploadedPhoto
from telethon.tl.functions.messages import SendMultiMediaRequest
from telethon.tl.types import InputSingleMedia, InputMediaUploadedDocument
from telethon.tl.types import DocumentAttributeVideo
import mimetypes
import re

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TelegramMediaUploader:
    def __init__(self):
        # قراءة المتغيرات من البيئة
        self.api_id = os.getenv('TELEGRAM_API_ID')
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.phone = os.getenv('TELEGRAM_PHONE')
        self.password = os.getenv('TELEGRAM_PASSWORD')
        self.session_string = os.getenv('TELEGRAM_SESSION_STRING')
        self.repo_token = os.getenv('REPO_TOKEN')
        
        # متغيرات إضافية لـ GitHub Actions
        self.is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
        
        # تهيئة العميل
        self.client = None
        self.channel_entity = None
        
        # إعدادات SSL
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        # مجلد التحميل المؤقت
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)
    
    def extract_filename_from_url(self, url: str) -> str:
        """استخراج اسم الملف من الرابط"""
        try:
            parsed = urllib.parse.urlparse(url)
            path = parsed.path
            
            if '/' in path:
                filename = path.split('/')[-1]
            else:
                filename = path
            
            # تنظيف اسم الملف
            filename = urllib.parse.unquote(filename)
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            
            # إذا لم يكن هناك امتداد، نضيف .mp4
            if '.' not in filename:
                filename += '.mp4'
                
            return filename
        except:
            return "video.mp4"
    
    def is_url(self, text: str) -> bool:
        """التحقق إذا كان النص هو رابط"""
        return text.startswith(('http://', 'https://', 'ftp://'))
    
    async def download_file(self, url: str, filename: Optional[str] = None) -> Optional[Path]:
        """تحميل ملف من رابط"""
        try:
            if not filename:
                filename = self.extract_filename_from_url(url)
            
            filepath = self.download_dir / filename
            
            logger.info(f"📥 جاري تحميل: {url}")
            logger.info(f"📁 سيحفظ كـ: {filepath.name}")
            
            # إعداد SSL لتجاهل التحقق
            conn = aiohttp.TCPConnector(ssl=self.ssl_context)
            
            async with aiohttp.ClientSession(connector=conn) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        # الحصول على الحجم الكلي
                        total_size = int(response.headers.get('content-length', 0))
                        
                        with open(filepath, 'wb') as f:
                            downloaded = 0
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                                downloaded += len(chunk)
                                
                                # عرض التقدم
                                if total_size > 0:
                                    percent = (downloaded / total_size) * 100
                                    if int(percent) % 10 == 0:
                                        logger.info(f"📊 التقدم: {percent:.1f}% ({downloaded/1024/1024:.1f}MB / {total_size/1024/1024:.1f}MB)")
                        
                        logger.info(f"✅ تم التحميل: {filepath.name} ({filepath.stat().st_size/1024/1024:.2f} MB)")
                        return filepath
                    else:
                        logger.error(f"❌ فشل التحميل: {response.status}")
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل الملف: {str(e)}")
        return None
    
    def get_input(self, prompt: str, required: bool = True, default: str = "") -> str:
        """الحصول على إدخال من المستخدم"""
        # في حالة GitHub Actions، نقرأ من المتغيرات
        if self.is_github_actions:
            env_var = prompt.split(":")[0].replace(" ", "_").upper()
            value = os.getenv(f"INPUT_{env_var}", default)
            if not value and required:
                logger.error(f"❌ المتغير {env_var} مطلوب!")
                return ""
            return value
        
        # في الوضع التفاعلي
        while True:
            value = input(prompt).strip()
            if not value and required:
                print("هذا الحقل مطلوب!")
                continue
            return value or default
    
    def get_choice(self, prompt: str, options: List[str], default: int = 1) -> str:
        """الحصول على اختيار من المستخدم"""
        # في حالة GitHub Actions
        if self.is_github_actions:
            env_var = prompt.split(":")[0].replace(" ", "_").upper()
            choice_str = os.getenv(f"INPUT_{env_var}", str(default))
            try:
                choice = int(choice_str)
                if 1 <= choice <= len(options):
                    return options[choice - 1]
            except:
                pass
            return options[default - 1]
        
        # في الوضع التفاعلي
        print(prompt)
        for i, option in enumerate(options, 1):
            print(f"{i}. {option}")
        
        while True:
            try:
                choice = int(input(f"اختر رقم (1-{len(options)}): "))
                if 1 <= choice <= len(options):
                    return options[choice - 1]
                print(f"اختيار غير صحيح! يجب أن يكون بين 1 و {len(options)}")
            except ValueError:
                print("الرجاء إدخال رقم!")
    
    def validate_data(self) -> bool:
        """التحقق من صحة جميع البيانات"""
        logger.info("جاري التحقق من البيانات...")
        
        # التحقق من بيانات التليجرام
        required_vars = ['TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_PHONE']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            logger.error(f"❌ بيانات التليجرام غير كاملة! المفقود: {', '.join(missing_vars)}")
            return False
        
        # التحقق من رابط القناة
        self.channel_url = self.get_input("رابط القناة", required=True)
        if not self.channel_url:
            logger.error("❌ رابط القناة مطلوب!")
            return False
        
        logger.info("✅ جميع البيانات صحيحة!")
        return True
    
    async def download_logo(self, logo_url: str) -> Optional[Path]:
        """تحميل الشعار من الرابط"""
        if not logo_url:
            return None
            
        try:
            logger.info(f"🎨 جاري تحميل الشعار من: {logo_url}")
            
            # إعداد SSL لتجاهل التحقق
            conn = aiohttp.TCPConnector(ssl=self.ssl_context)
            
            async with aiohttp.ClientSession(connector=conn) as session:
                async with session.get(logo_url) as response:
                    if response.status == 200:
                        # استخراج امتداد الملف
                        content_type = response.headers.get('Content-Type', '')
                        if 'image/' in content_type:
                            extension = mimetypes.guess_extension(content_type) or '.jpg'
                        else:
                            # محاولة استخراج الامتداد من الرابط
                            parsed_url = urllib.parse.urlparse(logo_url)
                            path = parsed_url.path
                            if '.' in path:
                                extension = '.' + path.split('.')[-1].split('?')[0]
                            else:
                                extension = '.jpg'
                        
                        # تنظيف الامتداد
                        extension = extension.lower()
                        if extension not in ['.jpg', '.jpeg', '.png', '.webp']:
                            extension = '.jpg'
                        
                        # حفظ الملف
                        logo_path = self.download_dir / f"logo{extension}"
                        with open(logo_path, 'wb') as f:
                            f.write(await response.read())
                        
                        logger.info(f"✅ تم تحميل الشعار: {logo_path.name} ({logo_path.stat().st_size/1024:.1f} KB)")
                        return logo_path
                    else:
                        logger.error(f"❌ فشل تحميل الشعار: {response.status}")
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل الشعار: {str(e)}")
        return None
    
    async def upload_media(self, file_path: Path, is_video: bool = True) -> Optional[InputMediaUploadedDocument]:
        """رفع ملف وسائط إلى التليجرام"""
        try:
            if not file_path.exists():
                logger.error(f"❌ الملف غير موجود: {file_path}")
                return None
                
            file_size = file_path.stat().st_size
            logger.info(f"⬆️  جاري رفع: {file_path.name} ({file_size/1024/1024:.2f} MB)")
            
            # رفع الملف
            file = await self.client.upload_file(
                file_path,
                progress_callback=self.upload_progress if file_size > 10*1024*1024 else None
            )
            
            if is_video:
                # رفع كفيديو
                attributes = [
                    DocumentAttributeVideo(
                        duration=0,
                        w=0,
                        h=0,
                        supports_streaming=True
                    )
                ]
                mime_type = "video/mp4"
            else:
                # رفع كصورة
                attributes = []
                mime_type = "image/jpeg"
            
            return InputMediaUploadedDocument(
                file=file,
                mime_type=mime_type,
                attributes=attributes,
                force_file=not is_video
            )
        except FloodWaitError as e:
            logger.warning(f"⏳ انتظر {e.seconds} ثانية بسبب FloodWait")
            await asyncio.sleep(e.seconds)
            return await self.upload_media(file_path, is_video)
        except Exception as e:
            logger.error(f"❌ خطأ في رفع الملف {file_path.name}: {str(e)}")
            return None
    
    def upload_progress(self, current: int, total: int):
        """عرض تقدم الرفع"""
        percent = (current / total) * 100
        if int(percent) % 10 == 0:
            logger.info(f"📤 رفع: {percent:.1f}% ({current/1024/1024:.1f}MB / {total/1024/1024:.1f}MB)")
    
    async def send_movie_post(self, video_path: Path, logo_path: Optional[Path]):
        """إرسال بوست فيلم مع صورة"""
        try:
            media_items = []
            caption_sent = False
            
            # رفع الفيديو
            video_media = await self.upload_media(video_path, is_video=True)
            if not video_media:
                logger.error("❌ فشل رفع الفيديو")
                return
            
            # رفع الصورة إذا كانت موجودة
            if logo_path and logo_path.exists():
                file_size = logo_path.stat().st_size
                
                if file_size < 10 * 1024 * 1024:  # أقل من 10MB
                    # رفع الصورة
                    photo_media = await self.upload_media(logo_path, is_video=False)
                    if photo_media:
                        # إضافة الصورة أولاً
                        media_items.append(InputSingleMedia(
                            media=photo_media,
                            message="",
                            entities=None
                        ))
                        logger.info("🖼️  تم إضافة الصورة في نفس البوست")
                else:
                    logger.info("⚠️  الصورة كبيرة جدًا، سيتم إرسالها في رسالة منفصلة")
            
            # إضافة الفيديو مع الكبشر
            media_items.append(InputSingleMedia(
                media=video_media,
                message=self.caption if self.caption else "",
                entities=None
            ))
            caption_sent = True
            
            # إرسال الوسائط المتعددة
            if media_items:
                result = await self.client(SendMultiMediaRequest(
                    peer=self.channel_entity,
                    multi_media=media_items,
                    silent=None,
                    reply_to_msg_id=None,
                    schedule_date=None
                ))
                
                # إرسال الصورة الكبيرة في رسالة منفصلة
                if logo_path and logo_path.exists() and logo_path.stat().st_size >= 10 * 1024 * 1024:
                    await self.client.send_file(
                        self.channel_entity,
                        logo_path,
                        caption=self.caption if (self.caption and not caption_sent) else ""
                    )
                
                logger.info(f"✅ تم نشر فيلم بنجاح! (رقم البوست: {result.id})")
                
        except FloodWaitError as e:
            logger.warning(f"⏳ انتظر {e.seconds} ثانية قبل المحاولة مرة أخرى")
            await asyncio.sleep(e.seconds)
            await self.send_movie_post(video_path, logo_path)
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال فيلم: {str(e)}")
    
    async def send_series_post(self, video_files: List[Path], logo_path: Optional[Path]):
        """إرسال بوست مسلسل (حلقات متعددة)"""
        try:
            if not video_files:
                logger.error("❌ لا توجد ملفات فيديو")
                return
            
            # إرسال الصورة أولاً إذا كانت موجودة
            if logo_path and logo_path.exists():
                await self.client.send_file(
                    self.channel_entity,
                    logo_path,
                    caption=self.caption if self.caption else ""
                )
                logger.info("✅ تم إرسال الصورة")
            
            # إرسال الحلقات في مجموعات (تليجرام يسمح بـ 10 ملفات كحد أقصى)
            total_episodes = 0
            for i in range(0, len(video_files), 10):
                batch = video_files[i:i + 10]
                media_items = []
                
                # رفع كل ملف فيديو في الدفعة
                for video_path in batch:
                    video_media = await self.upload_media(video_path, is_video=True)
                    if video_media:
                        # استخدام اسم الملف كوصف
                        file_caption = f"الحلقة {i + len(media_items) + 1}: {video_path.stem}"
                        media_items.append(InputSingleMedia(
                            media=video_media,
                            message=file_caption,
                            entities=None
                        ))
                
                # إرسال الدفعة
                if media_items:
                    await self.client(SendMultiMediaRequest(
                        peer=self.channel_entity,
                        multi_media=media_items,
                        silent=None,
                        reply_to_msg_id=None,
                        schedule_date=None
                    ))
                    
                    total_episodes += len(media_items)
                    logger.info(f"✅ تم نشر {len(media_items)} حلقة (المجموع: {total_episodes})")
                    
                    # انتظار بين الدفعات لتجنب FloodWait
                    if i + 10 < len(video_files):
                        logger.info("⏳ انتظار 5 ثواني قبل الرفع التالي...")
                        await asyncio.sleep(5)
                
            logger.info(f"🎉 تم نشر جميع الحلقات ({total_episodes} حلقة)")
                
        except FloodWaitError as e:
            logger.warning(f"⏳ انتظر {e.seconds} ثانية قبل المحاولة مرة أخرى")
            await asyncio.sleep(e.seconds)
            await self.send_series_post(video_files, logo_path)
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال مسلسل: {str(e)}")
    
    async def process_files(self):
        """معالجة الملفات المطلوبة"""
        # تحميل الشعار
        logo_url = self.get_input("رابط الشعار", required=False)
        logo_path = await self.download_logo(logo_url)
        
        # الحصول على نوع المحتوى
        media_type_options = ["أفلام", "مسلسلات"]
        self.media_type = self.get_choice("نوع المحتوى", media_type_options)
        
        # الحصول على الكبشر
        self.caption = self.get_input("الكبشر", required=False)
        
        # الحصول على مسارات/روابط الملفات
        if self.is_github_actions:
            # في GitHub Actions، نقرأ من متغير البيئة
            video_paths_input = os.getenv('INPUT_VIDEO_PATHS', '')
            video_paths_list = [p.strip() for p in video_paths_input.split(',') if p.strip()]
        else:
            # في الوضع التفاعلي
            video_paths_input = self.get_input("أدخل روابط/مسارات الملفات (مفصولة بفواصل): ", required=True)
            video_paths_list = [p.strip() for p in video_paths_input.split(',') if p.strip()]
        
        if not video_paths_list:
            logger.error("❌ لم يتم توفير أي ملفات!")
            return
        
        logger.info(f"📋 عدد الملفات/الروابط: {len(video_paths_list)}")
        
        # معالجة كل ملف/رابط
        downloaded_files = []
        
        for item in video_paths_list:
            if self.is_url(item):
                # تحميل من رابط
                logger.info(f"🌐 معالجة رابط: {item}")
                downloaded_file = await self.download_file(item)
                if downloaded_file:
                    downloaded_files.append(downloaded_file)
            else:
                # استخدام مسار محلي
                local_path = Path(item)
                if local_path.exists():
                    downloaded_files.append(local_path)
                    logger.info(f"📁 الملف المحلي: {local_path.name}")
                else:
                    logger.error(f"❌ الملف غير موجود: {item}")
        
        if not downloaded_files:
            logger.error("❌ لا توجد ملفات صالحة للرفع")
            return
        
        logger.info(f"✅ جاهز للرفع: {len(downloaded_files)} ملف")
        
        if self.media_type == "أفلام":
            # رفع أول فيلم فقط
            await self.send_movie_post(downloaded_files[0], logo_path)
        else:  # مسلسلات
            await self.send_series_post(downloaded_files, logo_path)
        
        # تنظيف الملفات المؤقتة
        self.cleanup_downloads(downloaded_files)
        if logo_path:
            logo_path.unlink(missing_ok=True)
    
    def cleanup_downloads(self, files: List[Path]):
        """حذف الملفات المؤقتة"""
        for file in files:
            try:
                if file.exists():
                    file.unlink()
                    logger.info(f"🧹 تم حذف: {file.name}")
            except:
                pass
    
    async def setup_client(self):
        """إعداد عميل التليجرام"""
        try:
            # إنشاء العميل
            session_name = 'telegram_session'
            if self.session_string:
                session_name = self.session_string
            
            self.client = TelegramClient(
                session=session_name,
                api_id=int(self.api_id),
                api_hash=self.api_hash
            )
            
            # الاتصال
            await self.client.start(
                phone=self.phone,
                password=self.password if self.password else None
            )
            
            logger.info("✅ تم الاتصال بالتليجرام بنجاح")
            
            # الحصول على كيان القناة
            channel_id = self.channel_url
            
            # تنظيف الرابط
            if 't.me/' in channel_id:
                channel_id = channel_id.split('t.me/')[-1]
            if channel_id.startswith('+'):
                channel_id = channel_id[1:]
            if channel_id.startswith('@'):
                channel_id = channel_id[1:]
            
            logger.info(f"🔍 البحث عن القناة: {channel_id}")
            self.channel_entity = await self.client.get_entity(channel_id)
            logger.info(f"✅ تم العثور على القناة: {self.channel_entity.title}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ خطأ في إعداد العميل: {str(e)}")
            return False
    
    async def run(self):
        """تشغيل البرنامج الرئيسي"""
        print("=" * 60)
        print("🚀 Telegram Media Uploader v2.0")
        print("=" * 60)
        
        # التحقق من البيانات
        if not self.validate_data():
            logger.error("❌ فشل التحقق من البيانات!")
            return
        
        # إعداد العميل
        if not await self.setup_client():
            logger.error("❌ فشل إعداد العميل!")
            return
        
        # معالجة الملفات
        try:
            await self.process_files()
        except KeyboardInterrupt:
            logger.info("⏹️  تم إيقاف البرنامج بواسطة المستخدم")
        except Exception as e:
            logger.error(f"❌ خطأ غير متوقع: {str(e)}")
        finally:
            # إغلاق العميل
            if self.client:
                await self.client.disconnect()
                logger.info("✅ تم إغلاق الاتصال")

async def main():
    """الدالة الرئيسية"""
    uploader = TelegramMediaUploader()
    await uploader.run()

if __name__ == "__main__":
    asyncio.run(main())
