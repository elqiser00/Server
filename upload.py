import asyncio, os, subprocess, sys, logging
        
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)
        
from telethon import TelegramClient
from telethon.sessions import StringSession
        
async def download_file(url, out):
    """تحميل الملفات"""
    try:
        logger.info(f"📥 تحميل: {url}")
                
        # استخدام curl
        cmd = [
            "curl", "-L",
            "--insecure",
            "--connect-timeout", "30",
            "--max-time", "300",
            "--retry", "2",
            "--output", out,
            url
        ]
                
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
        if result.returncode == 0 and os.path.exists(out):
            size = os.path.getsize(out)
            if size > 0:
                logger.info(f"✅ تم تحميل {out} - {size/1024/1024:.2f} MB")
                return True
                
        logger.error(f"❌ فشل التحميل")
        return False
                
    except Exception as e:
        logger.error(f"❌ خطأ: {e}")
        return False

async def main():
    try:
        # قراءة المتغيرات
        API_ID = int(os.environ['TELEGRAM_API_ID'])
        API_HASH = os.environ['TELEGRAM_API_HASH']
        SESSION = os.environ['TELEGRAM_SESSION_STRING']
        CHANNEL = os.environ['CHANNEL_LINK']
        MOVIE = os.environ['MOVIE_NAME']
        POSTER_URL = os.environ['POSTER_URL']
        VIDEO_URL = os.environ['VIDEO_URL']
                
        logger.info("=" * 50)
        logger.info("🚀 بدء رفع الفيلم")
        logger.info(f"🎬 {MOVIE}")
        logger.info("=" * 50)
                
        # تحميل الملفات
        logger.info("📥 جاري تحميل الملفات...")
                
        # تحميل الصورة
        if not await download_file(POSTER_URL, "poster.jpg"):
            raise Exception("فشل تحميل الصورة")
                
        # تحميل الفيديو
        if not await download_file(VIDEO_URL, "video.mp4"):
            raise Exception("فشل تحميل الفيديو")
                
        # الاتصال بالتليجرام
        logger.info("🔗 الاتصال بالتليجرام...")
        client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
        await client.connect()
                
        if not await client.is_user_authorized():
            raise Exception("جلسة غير صالحة")
                
        me = await client.get_me()
        logger.info(f"✅ متصل بـ: {me.first_name}")
                
        # الحصول على القناة
        channel = await client.get_entity(CHANNEL)
        logger.info(f"📢 القناة: {channel.title}")
        
        # **الحل: إرسال الملفات بشكل منفصل**
        
        # إرسال الصورة أولاً
        logger.info("🖼️ إرسال الصورة...")
        await client.send_file(
            entity=channel,
            file="poster.jpg",
            caption=f"🎬 {MOVIE}",
            parse_mode='html'
        )
        
        # إرسال الفيديو ثانياً
        logger.info("🎥 إرسال الفيديو...")
        await client.send_file(
            entity=channel,
            file="video.mp4",
            caption=f"🎥 {MOVIE}\n✅ فيلم كامل\n📊 الحجم: {os.path.getsize('video.mp4')/1024/1024:.2f} MB",
            parse_mode='html',
            supports_streaming=True
        )
        
        logger.info("✅ تم الرفع بنجاح!")
                
        await client.disconnect()
                
        # تنظيف
        os.remove("poster.jpg")
        os.remove("video.mp4")
        
        logger.info("🏁 العملية اكتملت!")
                
    except Exception as e:
        logger.error(f"❌ خطأ: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
