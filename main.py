#!/usr/bin/env python3
"""
Telegram Media Uploader Bot - النسخة المحسنة للجلسات
"""

import os
import sys
import asyncio
import logging
import json
import tempfile
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
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('uploader.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class TelegramUploader:
    def __init__(self):
        # تحميل البيانات
        self.load_config()
        
        # إعداد SSL
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        # مجلدات
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)
        
        # العميل
        self.client = None
        self.channel = None
        
        # جلسة مؤقتة
        self.temp_session_file = None
    
    def load_config(self):
        """تحميل الإعدادات"""
        # بيانات التليجرام
        self.api_id = os.getenv('TELEGRAM_API_ID', '')
        self.api_hash = os.getenv('TELEGRAM_API_HASH', '')
        self.phone = os.getenv('TELEGRAM_PHONE', '')
        self.password = os.getenv('TELEGRAM_PASSWORD', '')
        self.session_string = os.getenv('TELEGRAM_SESSION_STRING', '')
        
        # المدخلات
        self.channel_url = os.getenv('INPUT_CHANNEL_URL', '')
        self.media_type = os.getenv('INPUT_MEDIA_TYPE', 'أفلام')
        self.logo_url = os.getenv('INPUT_LOGO_URL', '')
        self.caption = os.getenv('INPUT_CAPTION', '')
        
        # روابط الفيديو
        video_paths_input = os.getenv('INPUT_VIDEO_PATHS', '')
        self.video_urls = []
        if video_paths_input:
            for url in video_paths_input.split(','):
                url = url.strip()
                if url and url.startswith(('http://', 'https://')):
                    self.video_urls.append(url)
        
        # التحقق من الأساسيات
        if not all([self.api_id, self.api_hash, self.phone]):
            logger.error("❌ بيانات التليجرام الأساسية مفقودة!")
            sys.exit(1)
    
    def print_header(self):
        """طباعة رأس البرنامج"""
        print("\n" + "="*60)
        print("🚀 TELEGRAM UPLOADER")
        print("="*60)
        print(f"📢 القناة: {self.channel_url}")
        print(f"🎬 النوع: {self.media_type}")
        print(f"📁 الملفات: {len(self.video_urls)}")
        if self.caption:
            print(f"📝 الكبشر: {self.caption}")
        print("="*60 + "\n")
    
    async def create_session_from_string(self):
        """إنشاء جلسة من السلسلة"""
        if not self.session_string:
            return False
        
        try:
            logger.info("🔐 محاولة استخدام سلسلة الجلسة...")
            
            # إنشاء ملف جلسة مؤقت من السلسلة
            self.temp_session_file = tempfile.NamedTemporaryFile(
                suffix='.session', 
                delete=False,
                mode='w'
            )
            
            # حفظ السلسلة في ملف
            session_data = self.session_string.strip()
            if not session_data.startswith('1'):
                logger.warning("⚠️  سلسلة الجلسة قديمة أو غير صالحة")
                return False
            
            # كتابة البيانات الخام
            with open(self.temp_session_file.name, 'wb') as f:
                # تحويل من نص إلى بايتات
                try:
                    import base64
                    # محاولة فك الترميز base64
                    session_bytes = base64.b64decode(session_data)
                    f.write(session_bytes)
                except:
                    # إذا لم تكن base64، نكتبها كنص
                    f.write(session_data.encode('utf-8'))
            
            # إنشاء العميل
            self.client = TelegramClient(
                self.temp_session_file.name,
                api_id=int(self.api_id),
                api_hash=self.api_hash
            )
            
            await self.client.connect()
            
            # التحقق من الجلسة
            if await self.client.is_user_authorized():
                me = await self.client.get_me()
                logger.info(f"✅ تم الاتصال كـ: {me.first_name}")
                return True
            else:
                logger.warning("⚠️  الجلسة غير مفعلة")
                return False
                
        except Exception as e:
            logger.error(f"❌ خطأ في سلسلة الجلسة: {str(e)}")
            return False
    
    async def create_session_interactive(self):
        """إنشاء جلسة تفاعلية (للتطوير فقط)"""
        logger.info("🔄 محاولة تسجيل الدخول...")
        
        # إنشاء ملف جلسة مؤقت
        session_file = tempfile.NamedTemporaryFile(
            suffix='.session',
            delete=False
        )
        session_file.close()
        
        try:
            self.client = TelegramClient(
                session_file.name,
                api_id=int(self.api_id),
                api_hash=self.api_hash
            )
            
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                # في GitHub Actions، لا يمكننا التسجيل تفاعلياً
                if os.getenv('GITHUB_ACTIONS') == 'true':
                    logger.error("❌ لا يمكن تسجيل الدخول في GitHub Actions")
                    logger.error("💡 استخدم TELEGRAM_SESSION_STRING المولدة محلياً")
                    return False
                
                # محاولة باستخدام كلمة المرور إذا كانت موجودة
                if self.password:
                    try:
                        await self.client.sign_in(self.phone, self.password)
                        logger.info("✅ تم تسجيل الدخول بكلمة المرور")
                    except:
                        logger.error("❌ فشل تسجيل الدخول بكلمة المرور")
                        return False
                else:
                    logger.error("❌ لا توجد وسيلة لتسجيل الدخول")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ خطأ في تسجيل الدخول: {str(e)}")
            return False
    
    async def connect_to_telegram(self):
        """الاتصال بتليجرام"""
        try:
            logger.info("🔗 جاري الاتصال بالتليجرام...")
            
            # المحاولة الأولى: استخدام سلسلة الجلسة
            if self.session_string:
                if await self.create_session_from_string():
                    return True
            
            # المحاولة الثانية: تسجيل الدخول
            if await self.create_session_interactive():
                return True
            
            logger.error("❌ فشل جميع محاولات الاتصال")
            return False
            
        except Exception as e:
            logger.error(f"❌ خطأ في الاتصال: {str(e)}")
            return False
    
    async def get_channel(self):
        """الحصول على القناة"""
        try:
            logger.info(f"🔍 البحث عن القناة: {self.channel_url}")
            
            # تنظيف الرابط
            channel_id = self.channel_url.strip()
            
            # إزالة https://t.me/
            if 't.me/' in channel_id:
                channel_id = channel_id.split('t.me/')[-1]
            
            # إزالة @ أو +
            if channel_id.startswith(('@', '+')):
                channel_id = channel_id[1:]
            
            logger.info(f"   المعرف: {channel_id}")
            
            # محاولات مختلفة
            attempts = [
                channel_id,
                f"@{channel_id}",
                f"https://t.me/{channel_id}",
                f"t.me/{channel_id}"
            ]
            
            for attempt in attempts:
                try:
                    self.channel = await self.client.get_entity(attempt)
                    logger.info(f"✅ تم العثور على: {self.channel.title}")
                    return True
                except:
                    continue
            
            logger.error("❌ لم أتمكن من إيجاد القناة")
            return False
            
        except Exception as e:
            logger.error(f"❌ خطأ في إيجاد القناة: {str(e)}")
            return False
    
    def extract_filename(self, url: str) -> str:
        """استخراج اسم الملف"""
        try:
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path)
            
            if not filename or filename == '/':
                # إنشاء اسم فريد
                import time
                import hashlib
                domain = parsed.netloc.replace('.', '_')
                timestamp = int(time.time())
                hash_str = hashlib.md5(url.encode()).hexdigest()[:6]
                filename = f"{domain}_{timestamp}_{hash_str}.mp4"
            
            # تنظيف
            filename = urllib.parse.unquote(filename)
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            
            # إضافة امتداد
            if '.' not in filename:
                filename += '.mp4'
            
            return filename[:100]
            
        except:
            return f"video_{int(time.time())}.mp4"
    
    async def download_file(self, url: str) -> Path:
        """تحميل ملف"""
        filename = self.extract_filename(url)
        filepath = self.download_dir / filename
        
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
                            
                            async for chunk in response.content.iter_chunked(8192):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    
                                    if total_size > 0 and downloaded % (1024*1024*10) == 0:
                                        percent = (downloaded / total_size) * 100
                                        mb = downloaded / 1024 / 1024
                                        logger.info(f"   📊 {int(percent)}% ({mb:.1f} MB)")
                        
                        size_mb = filepath.stat().st_size / 1024 / 1024
                        logger.info(f"✅ تم التحميل: {filename} ({size_mb:.1f} MB)")
                        return filepath
                    else:
                        raise Exception(f"HTTP {response.status}")
                        
        except Exception as e:
            logger.error(f"❌ خطأ في التحميل: {str(e)}")
            if filepath.exists():
                filepath.unlink()
            raise
    
    async def upload_file(self, filepath: Path, is_video: bool = True):
        """رفع ملف"""
        try:
            filename = filepath.name
            size_mb = filepath.stat().st_size / 1024 / 1024
            
            logger.info(f"⬆️  جاري رفع: {filename} ({size_mb:.1f} MB)")
            
            file = await self.client.upload_file(filepath)
            
            if is_video:
                attributes = [DocumentAttributeVideo(
                    duration=0, w=0, h=0, supports_streaming=True
                )]
                mime_type = "video/mp4"
            else:
                attributes = []
                mime_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
            
            return InputMediaUploadedDocument(
                file=file,
                mime_type=mime_type,
                attributes=attributes,
                force_file=False
            )
            
        except FloodWaitError as e:
            wait_time = e.seconds
            logger.warning(f"⏳ انتظر {wait_time} ثانية...")
            await asyncio.sleep(wait_time)
            return await self.upload_file(filepath, is_video)
        except Exception as e:
            logger.error(f"❌ خطأ في الرفع: {str(e)}")
            raise
    
    async def send_movie(self, video_path: Path, logo_url: str = None):
        """إرسال فيلم"""
        try:
            logger.info("🎬 إرسال الفيلم...")
            
            media_items = []
            
            # الصورة إذا كانت موجودة
            if logo_url:
                try:
                    logo_path = await self.download_file(logo_url)
                    logo_media = await self.upload_file(logo_path, is_video=False)
                    media_items.append(InputSingleMedia(
                        media=logo_media,
                        message="",
                        entities=None
                    ))
                    logo_path.unlink()
                    logger.info("🖼️  تم إضافة الصورة")
                except Exception as e:
                    logger.warning(f"⚠️  فشل إضافة الصورة: {str(e)}")
            
            # الفيديو
            video_media = await self.upload_file(video_path, is_video=True)
            
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
            
            logger.info(f"✅ تم النشر! (ID: {result.id})")
            
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال الفيلم: {str(e)}")
            raise
    
    async def cleanup(self):
        """تنظيف"""
        if self.temp_session_file and os.path.exists(self.temp_session_file.name):
            try:
                os.unlink(self.temp_session_file.name)
            except:
                pass
        
        if self.client:
            await self.client.disconnect()
            logger.info("🔌 تم إغلاق الاتصال")
    
    async def run(self):
        """تشغيل البرنامج"""
        self.print_header()
        
        # الاتصال
        if not await self.connect_to_telegram():
            return False
        
        # القناة
        if not await self.get_channel():
            return False
        
        try:
            # تحميل الفيديو
            if not self.video_urls:
                logger.error("❌ لا توجد روابط فيديو")
                return False
            
            video_path = await self.download_file(self.video_urls[0])
            
            # الإرسال
            if self.media_type == "أفلام":
                await self.send_movie(video_path, self.logo_url)
            else:
                logger.info("📺 إرسال المسلسل...")
                # هنا يمكنك إضافة كود المسلسل
            
            # تنظيف
            if video_path.exists():
                video_path.unlink()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ خطأ: {str(e)}")
            return False
        finally:
            await self.cleanup()

async def main():
    """الدالة الرئيسية"""
    uploader = TelegramUploader()
    
    try:
        success = await uploader.run()
        return 0 if success else 1
    except KeyboardInterrupt:
        logger.info("⏹️  تم الإيقاف")
        return 1
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
