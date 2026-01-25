import asyncio, os, subprocess, sys, logging, ssl, certifi
from telethon import TelegramClient, types
from telethon.sessions import StringSession

# تعطيل تحذيرات SSL
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def download_file(url, out):
    """تحميل الملفات مع التعامل مع مشاكل SSL"""
    try:
        logger.info(f"📥 جاري تحميل {url}")
        
        # استخدام wget مع --no-check-certificate للتحايل على مشاكل SSL
        if 'downet.net' in url:
            # للموقع الذي به مشاكل SSL
            cmd = ["wget", "--no-check-certificate", "-O", out, url]
        else:
            cmd = ["wget", "-O", out, url]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            logger.error(f"❌ wget فشل: {result.stderr}")
            
            # محاولة باستخدام curl إذا فشل wget
            logger.info("🔄 جرب باستخدام curl...")
            cmd = ["curl", "-L", "--insecure", "-o", out, url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                logger.error(f"❌ curl فشل أيضًا: {result.stderr}")
                return False
        
        if not os.path.exists(out):
            logger.error("❌ الملف لم يتم تحميله")
            return False
        
        file_size = os.path.getsize(out) / (1024*1024)
        logger.info(f"✅ تم تحميل {out} - الحجم: {file_size:.2f} MB")
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("⏰ تجاوز الوقت المسموح للتحميل")
        return False
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
        return False

def check_video(path):
    """فحص الفيديو"""
    if not os.path.exists(path):
        raise Exception("الملف غير موجود")
    
    size = os.path.getsize(path)
    if size < 5 * 1024 * 1024:  # أقل من 5 ميجابايت
        raise Exception(f"الملف صغير جداً: {size/1024/1024:.2f} MB")
    
    logger.info(f"📊 حجم الفيديو: {size/1024/1024:.2f} MB")
    
    try:
        # فحص الفيديو باستخدام ffprobe
        cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=codec_name,duration,width,height,bit_rate",
               "-of", "csv=p=0", path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.stdout:
            parts = result.stdout.strip().split(',')
            if len(parts) >= 4:
                codec, duration, width, height = parts[0], parts[1], parts[2], parts[3]
                logger.info(f"🎥 معلومات الفيديو: {codec}, {duration}s, {width}x{height}")
        
    except Exception as e:
        logger.warning(f"⚠️ فحص الفيديو: {e}")
        # نستمر رغم فشل الفحص

async def main():
    # قراءة المتغيرات البيئية
    API_ID = int(os.environ['TELEGRAM_API_ID'])
    API_HASH = os.environ['TELEGRAM_API_HASH']
    SESSION = os.environ['TELEGRAM_SESSION_STRING']
    CHANNEL = os.environ['CHANNEL_LINK']
    MOVIE = os.environ['MOVIE_NAME']
    POSTER_URL = os.environ['POSTER_URL']
    VIDEO_URL = os.environ['VIDEO_URL']
    
    POSTER = "poster.jpg"
    VIDEO = "video.mp4"
    
    logger.info("🚀 بدء عملية الرفع...")
    logger.info(f"🎬 الفيلم: {MOVIE}")
    logger.info(f"📢 القناة: {CHANNEL}")
    
    # تحميل الملفات
    logger.info("⬇️ جاري تحميل الملفات...")
    
    # تحميل الصورة
    logger.info(f"🖼️ تحميل الصورة من: {POSTER_URL}")
    if not await download_file(POSTER_URL, POSTER):
        raise Exception("❌ فشل تحميل الصورة")
    
    # تحميل الفيديو
    logger.info(f"🎥 تحميل الفيديو من: {VIDEO_URL}")
    if not await download_file(VIDEO_URL, VIDEO):
        raise Exception("❌ فشل تحميل الفيديو")
    
    # فحص الفيديو
    check_video(VIDEO)
    
    # الاتصال بالتليجرام
    logger.info("🔗 جاري الاتصال بالتليجرام...")
    client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await client.connect()
    
    if not await client.is_user_authorized():
        raise Exception("❌ جلسة تليجرام غير صالحة")
    
    me = await client.get_me()
    logger.info(f"✅ تم الاتصال بـ {me.username} ({me.id})")
    
    # الحصول على القناة
    logger.info(f"🔍 جاري العثور على القناة...")
    try:
        channel = await client.get_entity(CHANNEL)
        logger.info(f"📢 القناة: {channel.title} (ID: {channel.id})")
    except Exception as e:
        logger.error(f"❌ خطأ في العثور على القناة: {e}")
        raise Exception(f"تأكد من رابط القناة وأن البوت عضو فيها: {CHANNEL}")
    
    # رفع الملفات
    logger.info("⬆️ جاري رفع الملفات إلى التليجرام...")
    
    try:
        # رفع الصورة
        logger.info("🖼️ رفع الصورة...")
        photo = await client.upload_file(
            POSTER,
            part_size_kb=512,
            file_size=os.path.getsize(POSTER)
        )
        logger.info("✅ تم رفع الصورة")
        
        # رفع الفيديو
        logger.info("🎥 رفع الفيديو...")
        video = await client.upload_file(
            VIDEO,
            part_size_kb=512,
            file_size=os.path.getsize(VIDEO)
        )
        logger.info("✅ تم رفع الفيديو")
        
        # إنشاء الوسائط
        media = [
            types.InputMediaUploadedPhoto(
                file=photo,
                caption=f"🎬 {MOVIE}"
            ),
            types.InputMediaUploadedDocument(
                file=video,
                mime_type="video/mp4",
                attributes=[
                    types.DocumentAttributeVideo(
                        supports_streaming=True,
                        duration=0,
                        w=0,
                        h=0
                    )
                ],
                caption=f"🎥 {MOVIE}\n✅ فيلم كامل\n📊 الحجم: {os.path.getsize(VIDEO)/1024/1024:.2f} MB"
            )
        ]
        
        # إرسال الرسالة
        logger.info("📤 جاري إرسال الوسائط...")
        message = await client.send_message(
            channel,
            file=media
        )
        
        logger.info(f"✅ تم الرفع بنجاح! الرسالة ID: {message.id}")
        
        # عرض رابط الرسالة
        if hasattr(channel, 'username') and channel.username:
            message_link = f"https://t.me/{channel.username}/{message.id}"
        else:
            message_link = f"https://t.me/c/{str(channel.id)[4:]}/{message.id}"
        
        logger.info(f"🔗 رابط الرسالة: {message_link}")
        
    except Exception as e:
        logger.error(f"❌ خطأ أثناء الرفع: {e}")
        raise
    
    finally:
        await client.disconnect()
        logger.info("👋 تم قطع الاتصال")
    
    # تنظيف الملفات المؤقتة
    for file in [POSTER, VIDEO]:
        if os.path.exists(file):
            os.remove(file)
            logger.info(f"🗑️ تم حذف {file}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
        print("\n" + "="*50)
        print("🎉 تمت العملية بنجاح!")
        print("="*50)
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n❌ خطأ: {e}")
        print("="*50)
        sys.exit(1)
