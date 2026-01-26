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
            logger.info(f"جاري تحميل الشعار من: {logo_url}")
            
            # إعداد SSL لتجاهل التحقق
            conn = aiohttp.TCPConnector(ssl=self.ssl_context)
            
            async with aiohttp.ClientSession(connector=conn) as session:
                async with session.get(logo_url) as response:
                    if response.status == 200:
                        # استخراج امتداد الملف من الرابط أو Content-Type
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
                        logo_path = Path(f"logo{extension}")
                        with open(logo_path, 'wb') as f:
                            f.write(await response.read())
                        
                        logger.info(f"✅ تم تحميل الشعار: {logo_path} ({logo_path.stat().st_size} بايت)")
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
                
            logger.info(f"جاري رفع الملف: {file_path.name} ({file_path.stat().st_size / 1024 / 1024:.2f} MB)")
            
            # رفع الملف
            file = await self.client.upload_file(file_path)
            
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
    
    async def send_movie_post(self, video_path: Path, logo_path: Optional[Path]):
        """إرسال بوست فيلم مع صورة"""
        try:
            media_items = []
            
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
                        logger.info("✅ تم إضافة الصورة في نفس البوست")
                else:
                    logger.info("⚠️  الصورة كبيرة جدًا، سيتم إرسالها في رسالة منفصلة")
            
            # إضافة الفيديو
            media_items.append(InputSingleMedia(
                media=video_media,
                message=self.caption if self.caption else "",
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
                
                # إرسال الصورة الكبيرة في رسالة منفصلة
                if logo_path and logo_path.exists() and logo_path.stat().st_size >= 10 * 1024 * 1024:
                    await self.client.send_file(
                        self.channel_entity,
                        logo_path,
                        caption=self.caption if self.caption else ""
                    )
                
                logger.info("✅ تم نشر فيلم بنجاح!")
                
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
            for i in range(0, len(video_files), 10):
                batch = video_files[i:i + 10]
                media_items = []
                
                # رفع كل ملف فيديو في الدفعة
                for video_path in batch:
                    video_media = await self.upload_media(video_path, is_video=True)
                    if video_media:
                        # استخدام اسم الملف كوصف
                        file_caption = video_path.stem
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
                    
                    logger.info(f"✅ تم نشر {len(media_items)} حلقة من الدفعة {i//10 + 1}")
                    
                    # انتظار بين الدفعات لتجنب FloodWait
                    if i + 10 < len(video_files):
                        await asyncio.sleep(5)
                
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
        
        if self.media_type == "أفلام":
            # معالجة الأفلام
            video_path_str = self.get_input("مسار ملف الفيديو", required=True)
            video_path = Path(video_path_str)
            
            if not video_path.exists():
                logger.error(f"❌ ملف الفيديو غير موجود: {video_path}")
                return
            
            # تحويل إلى MP4 إذا لزم الأمر
            if video_path.suffix.lower() != '.mp4':
                logger.warning(f"⚠️  الملف ليس بصيغة MP4: {video_path.suffix}")
                # هنا يمكن إضافة كود التحويل باستخدام ffmpeg
                # video_path = await self.convert_to_mp4(video_path)
            
            await self.send_movie_post(video_path, logo_path)
            
        else:  # مسلسلات
            # معالجة المسلسلات
            base_path_str = self.get_input("المسار الأساسي للمسلسل", required=True)
            base_path = Path(base_path_str)
            
            if not base_path.exists():
                logger.error(f"❌ المسار غير موجود: {base_path}")
                return
            
            # البحث عن ملفات الفيديو
            video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm']
            video_files = []
            
            for ext in video_extensions:
                video_files.extend(list(base_path.glob(f'*{ext}')))
                video_files.extend(list(base_path.glob(f'*{ext.upper()}')))
            
            if not video_files:
                logger.error("❌ لم يتم العثور على ملفات فيديو!")
                return
            
            logger.info(f"📁 تم العثور على {len(video_files)} ملف فيديو")
            
            if not self.is_github_actions:
                # عرض الملفات للاختيار في الوضع التفاعلي
                print(f"\nالملفات الموجودة:")
                for i, file in enumerate(video_files[:20], 1):
                    print(f"{i}. {file.name}")
                
                choice = self.get_choice(
                    "كيف تريد معالجة الملفات:",
                    ["رفع أول 10 ملفات", "رفع جميع الملفات", "اختيار ملفات معينة"]
                )
                
                if choice == "رفع أول 10 ملفات":
                    selected_files = video_files[:10]
                elif choice == "رفع جميع الملفات":
                    selected_files = video_files
                else:  # اختيار ملفات معينة
                    selected_indices = input("أدخل أرقام الملفات (مفصولة بفواصل): ").split(',')
                    selected_files = []
                    for idx in selected_indices:
                        try:
                            idx_num = int(idx.strip()) - 1
                            if 0 <= idx_num < len(video_files):
                                selected_files.append(video_files[idx_num])
                        except ValueError:
                            pass
            else:
                # في GitHub Actions، نرفع أول 10 ملفات
                selected_files = video_files[:10]
            
            # تأكيد
            if not self.is_github_actions:
                print(f"\nسيتم رفع {len(selected_files)} ملف:")
                for file in selected_files:
                    print(f"- {file.name}")
                
                confirm = input("\nهل تريد المتابعة؟ (نعم/لا): ").strip().lower()
                if confirm not in ['نعم', 'yes', 'y', '']:
                    logger.info("❌ تم إلغاء العملية")
                    return
            
            await self.send_series_post(selected_files, logo_path)
    
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
            if 't.me/' in self.channel_url:
                channel_id = self.channel_url.split('t.me/')[-1].replace('@', '')
            else:
                channel_id = self.channel_url.replace('@', '')
            
            self.channel_entity = await self.client.get_entity(channel_id)
            logger.info(f"✅ تم العثور على القناة: {self.channel_entity.title}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ خطأ في إعداد العميل: {str(e)}")
            return False
    
    async def run(self):
        """تشغيل البرنامج الرئيسي"""
        print("=" * 50)
        print("Telegram Media Uploader v1.0")
        print("=" * 50)
        
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
