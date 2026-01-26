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
import mimetypes

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
        
        # قراءة إدخالات المستخدم
        self.channel_url = self.get_input("أدخل رابط القناة (مثال: @channel_name أو https://t.me/channel_name): ")
        self.media_type = self.get_choice("اختر نوع المحتوى:", ["أفلام", "مسلسلات"])
        self.caption = self.get_input("أدريد الكبشر (وصف البوست): ", required=False)
        
        # تهيئة العميل
        self.client = None
        self.channel_entity = None
        
        # إعدادات SSL
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
    def get_input(self, prompt: str, required: bool = True) -> str:
        """الحصول على إدخال من المستخدم"""
        while True:
            value = input(prompt).strip()
            if not value and required:
                print("هذا الحقل مطلوب!")
                continue
            return value
    
    def get_choice(self, prompt: str, options: List[str]) -> str:
        """الحصول على اختيار من المستخدم"""
        print(prompt)
        for i, option in enumerate(options, 1):
            print(f"{i}. {option}")
        
        while True:
            try:
                choice = int(input("اختر رقم: "))
                if 1 <= choice <= len(options):
                    return options[choice - 1]
                print("اختيار غير صحيح!")
            except ValueError:
                print("الرجاء إدخال رقم!")
    
    def validate_data(self) -> bool:
        """التحقق من صحة جميع البيانات"""
        print("جاري التحقق من البيانات...")
        
        # التحقق من بيانات التليجرام
        if not all([self.api_id, self.api_hash, self.phone]):
            print("❌ بيانات التليجرام غير كاملة!")
            return False
        
        # التحقق من رابط القناة
        if not self.channel_url:
            print("❌ رابط القناة مطلوب!")
            return False
        
        # استخراج معرف القناة من الرابط
        if 't.me/' in self.channel_url:
            channel_id = self.channel_url.split('t.me/')[-1].replace('@', '')
        else:
            channel_id = self.channel_url.replace('@', '')
        
        if not channel_id:
            print("❌ رابط القناة غير صالح!")
            return False
        
        print("✅ جميع البيانات صحيحة!")
        return True
    
    async def download_logo(self, logo_url: str) -> Optional[Path]:
        """تحميل الشعار من الرابط"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(logo_url, ssl=self.ssl_context) as response:
                    if response.status == 200:
                        # استخراج امتداد الملف
                        content_type = response.headers.get('Content-Type', '')
                        extension = mimetypes.guess_extension(content_type) or '.jpg'
                        
                        # حفظ الملف
                        logo_path = Path(f"Logo{extension}")
                        with open(logo_path, 'wb') as f:
                            f.write(await response.read())
                        
                        logger.info(f"✅ تم تحميل الشعار: {logo_path}")
                        return logo_path
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل الشعار: {e}")
        return None
    
    async def upload_media(self, file_path: Path, is_video: bool = True) -> Optional[InputMediaUploadedDocument]:
        """رفع ملف وسائط إلى التليجرام"""
        try:
            logger.info(f"جاري رفع الملف: {file_path.name}")
            
            # رفع الملف
            file = await self.client.upload_file(file_path)
            
            if is_video:
                # رفع كفيديو
                attributes = [
                    self.client.build_attribute(DocumentAttributeVideo(
                        duration=0,
                        w=0,
                        h=0
                    ))
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
                force_file=False
            )
        except Exception as e:
            logger.error(f"❌ خطأ في رفع الملف {file_path.name}: {e}")
            return None
    
    async def send_movie_post(self, video_path: Path, logo_path: Optional[Path]):
        """إرسال بوست فيلم مع صورة"""
        try:
            media_items = []
            
            # رفع الفيديو
            video_media = await self.upload_media(video_path, is_video=True)
            if video_media:
                media_items.append(InputSingleMedia(
                    media=video_media,
                    message="",
                    entities=None
                ))
            
            # رفع الصورة إذا كانت موجودة
            if logo_path and logo_path.exists():
                # تحقق من حجم الصورة
                file_size = logo_path.stat().st_size
                
                if file_size < 10 * 1024 * 1024:  # أقل من 10MB
                    photo_media = await self.upload_media(logo_path, is_video=False)
                    if photo_media:
                        # إضافة الصورة في البداية إذا كانت صغيرة
                        media_items.insert(0, InputSingleMedia(
                            media=photo_media,
                            message="",
                            entities=None
                        ))
            
            # إرسال الوسائط المتعددة
            if media_items:
                await self.client(SendMultiMediaRequest(
                    peer=self.channel_entity,
                    multi_media=media_items,
                    silent=None,
                    reply_to_msg_id=None,
                    schedule_date=None
                ))
                
                # إرسال الكبشر إذا كان هناك صورة كبيرة
                if logo_path and logo_path.exists() and logo_path.stat().st_size >= 10 * 1024 * 1024:
                    await self.client.send_message(
                        self.channel_entity,
                        self.caption if self.caption else ""
                    )
                
                logger.info("✅ تم نشر البوست بنجاح!")
                
        except FloodWaitError as e:
            logger.warning(f"⏳ انتظر {e.seconds} ثانية قبل المحاولة مرة أخرى")
            await asyncio.sleep(e.seconds)
            await self.send_movie_post(video_path, logo_path)
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال البوست: {e}")
    
    async def send_series_post(self, video_files: List[Path], logo_path: Optional[Path]):
        """إرسال بوست مسلسل (حلقات متعددة)"""
        try:
            media_items = []
            
            # رفع كل ملف فيديو
            for video_path in video_files[:10]:  # حد أقصى 10 ملفات
                video_media = await self.upload_media(video_path, is_video=True)
                if video_media:
                    # استخدام اسم الملف ككبشر
                    file_caption = video_path.stem
                    media_items.append(InputSingleMedia(
                        media=video_media,
                        message=file_caption,
                        entities=None
                    ))
            
            # إرسال الوسائط المتعددة
            if media_items:
                await self.client(SendMultiMediaRequest(
                    peer=self.channel_entity,
                    multi_media=media_items,
                    silent=None,
                    reply_to_msg_id=None,
                    schedule_date=None
                ))
                
                # إرسال الكبشر الرئيسي إذا كان موجودًا
                if self.caption:
                    await self.client.send_message(
                        self.channel_entity,
                        self.caption
                    )
                
                logger.info(f"✅ تم نشر {len(media_items)} حلقة بنجاح!")
                
        except FloodWaitError as e:
            logger.warning(f"⏳ انتظر {e.seconds} ثانية قبل المحاولة مرة أخرى")
            await asyncio.sleep(e.seconds)
            await self.send_series_post(video_files, logo_path)
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال البوست: {e}")
    
    async def process_files(self):
        """معالجة الملفات المطلوبة"""
        # تحميل الشعار
        logo_url = self.get_input("أدخل رابط الشعار (Logo): ")
        logo_path = await self.download_logo(logo_url) if logo_url else None
        
        if self.media_type == "أفلام":
            # معالجة الأفلام
            video_path_str = self.get_input("أدخل مسار ملف الفيديو: ")
            video_path = Path(video_path_str)
            
            if not video_path.exists():
                print(f"❌ ملف الفيديو غير موجود: {video_path}")
                return
            
            # تحويل إلى MP4 إذا لزم الأمر
            if video_path.suffix.lower() != '.mp4':
                new_path = video_path.with_suffix('.mp4')
                print(f"⚠️  سيتم تحويل الملف إلى MP4: {new_path.name}")
                # هنا يمكن إضافة كود التحويل باستخدام ffmpeg
                video_path = new_path
            
            await self.send_movie_post(video_path, logo_path)
            
        else:  # مسلسلات
            # معالجة المسلسلات
            base_path_str = self.get_input("أدخل المسار الأساسي للمسلسل: ")
            base_path = Path(base_path_str)
            
            if not base_path.exists():
                print(f"❌ المسار غير موجود: {base_path}")
                return
            
            # البحث عن ملفات الفيديو
            video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv']
            video_files = []
            
            for ext in video_extensions:
                video_files.extend(list(base_path.glob(f'*{ext}')))
                video_files.extend(list(base_path.glob(f'*{ext.upper()}')))
            
            if not video_files:
                print("❌ لم يتم العثور على ملفات فيديو!")
                return
            
            # عرض الملفات للاختيار
            print(f"\nتم العثور على {len(video_files)} ملف فيديو:")
            for i, file in enumerate(video_files[:20], 1):  # عرض أول 20 ملف فقط
                print(f"{i}. {file.name}")
            
            choice = self.get_choice(
                "\nكيف تريد معالجة الملفات:",
                ["رفع أول 10 ملفات", "اختيار ملفات معينة", "تسمية كل ملف"]
            )
            
            if choice == "رفع أول 10 ملفات":
                selected_files = video_files[:10]
            elif choice == "اختيار ملفات معينة":
                selected_indices = input("أدخل أرقام الملفات (مفصولة بفواصل): ").split(',')
                selected_files = []
                for idx in selected_indices:
                    try:
                        selected_files.append(video_files[int(idx.strip()) - 1])
                    except (ValueError, IndexError):
                        pass
            else:  # تسمية كل ملف
                selected_files = video_files[:10]
                # هنا يمكن إضافة كود إعادة تسمية الملفات
            
            # تأكيد أسماء الملفات
            print("\nالملفات المختارة للرفع:")
            for file in selected_files:
                print(f"- {file.name}")
            
            confirm = input("\nهل تريد المتابعة؟ (نعم/لا): ").strip().lower()
            if confirm in ['نعم', 'yes', 'y']:
                await self.send_series_post(selected_files, logo_path)
    
    async def setup_client(self):
        """إعداد عميل التليجرام"""
        try:
            # إنشاء العميل
            self.client = TelegramClient(
                session='telegram_session',
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
            if 't.me/' in self.channel_url:
                channel_id = self.channel_url.split('t.me/')[-1].replace('@', '')
            else:
                channel_id = self.channel_url.replace('@', '')
            
            self.channel_entity = await self.client.get_entity(channel_id)
            logger.info(f"✅ تم العثور على القناة: {self.channel_entity.title}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ خطأ في إعداد العميل: {e}")
            return False
    
    async def run(self):
        """تشغيل البرنامج الرئيسي"""
        print("=" * 50)
        print("Telegram Media Uploader v1.0")
        print("=" * 50)
        
        # التحقق من البيانات
        if not self.validate_data():
            print("❌ فشل التحقق من البيانات!")
            return
        
        # إعداد العميل
        if not await self.setup_client():
            print("❌ فشل إعداد العميل!")
            return
        
        # معالجة الملفات
        try:
            await self.process_files()
        except Exception as e:
            logger.error(f"❌ خطأ غير متوقع: {e}")
        finally:
            # إغلاق العميل
            if self.client:
                await self.client.disconnect()
                logger.info("✅ تم إغلاق الاتصال")

# دالة رئيسية للعمل مع GitHub Actions
async def github_actions_main():
    """الدالة الرئيسية للعمل مع GitHub Actions"""
    uploader = TelegramMediaUploader()
    
    # قراءة المتغيرات من GitHub Actions
    uploader.channel_url = os.getenv('CHANNEL_URL', '')
    uploader.media_type = os.getenv('MEDIA_TYPE', 'أفلام')
    uploader.caption = os.getenv('CAPTION', '')
    
    # التحقق من البيانات
    if not uploader.validate_data():
        sys.exit(1)
    
    # إعداد العميل
    if not await uploader.setup_client():
        sys.exit(1)
    
    # معالجة الملفات من GitHub
    logo_url = os.getenv('LOGO_URL')
    video_paths = os.getenv('VIDEO_PATHS', '').split(',')
    
    if uploader.media_type == "أفلام" and video_paths and video_paths[0]:
        logo_path = await uploader.download_logo(logo_url) if logo_url else None
        video_path = Path(video_paths[0].strip())
        await uploader.send_movie_post(video_path, logo_path)
    elif uploader.media_type == "مسلسلات" and video_paths:
        logo_path = await uploader.download_logo(logo_url) if logo_url else None
        video_files = [Path(p.strip()) for p in video_paths if p.strip()]
        await uploader.send_series_post(video_files[:10], logo_path)
    
    # إغلاق العميل
    if uploader.client:
        await uploader.client.disconnect()

if __name__ == "__main__":
    # التحقق إذا كان يعمل في GitHub Actions
    if os.getenv('GITHUB_ACTIONS') == 'true':
        asyncio.run(github_actions_main())
    else:
        # وضع التفاعلي
        uploader = TelegramMediaUploader()
        asyncio.run(uploader.run())
