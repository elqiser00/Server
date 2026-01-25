import asyncio, os, subprocess, sys, logging, ssl
from telethon import TelegramClient, types
from telethon.sessions import StringSession

# تعطيل تحقق SSL بالكامل
ssl._create_default_https_context = ssl._create_unverified_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def download_with_curl(url, out):
    """تحميل الملفات باستخدام curl مع إعدادات متقدمة"""
    try:
        logger.info(f"📥 جاري تحميل: {url}")
        
        # بناء أمر curl
        cmd = [
            "curl", "-L",
            "--insecure",           # تجاهل شهادات SSL
            "--connect-timeout", "30",  # 30 ثانية للاتصال
            "--max-time", "600",    # 10 دقائق كحد أقصى للتحميل
            "--retry", "3",         # 3 محاولات
            "--retry-delay", "5",   # 5 ثواني بين المحاولات
            "--compressed",         # قبول الضغط
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",  # user-agent مزيف
            "--output", out,
            url
        ]
        
        logger.info(f"🔧 تشغيل الأمر: {' '.join(cmd[:5])}...")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode == 0:
            if os.path.exists(out) and os.path.getsize(out) > 1024:  # أكبر من 1KB
                size_mb = os.path.getsize(out) / (1024 * 1024)
                logger.info(f"✅ تم تحميل {out} - الحجم: {size_mb:.2f} MB")
                return True
            else:
                logger.error("❌ الملف تم تحميله ولكن حجمه صغير جدًا")
                return False
        else:
            logger.error(f"❌ curl فشل مع كود الخطأ: {result.returncode}")
            if result.stderr:
                logger.error(f"📝 تفاصيل الخطأ: {result.stderr[:500]}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("⏰ تجاوز الوقت المسموح للتحميل")
        return False
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {str(e)}")
        return False

async def download_with_wget(url, out):
    """محاولة التحميل باستخدام wget"""
    try:
        logger.info(f"🔄 محاولة التحميل باستخدام wget: {url}")
        
        cmd = [
            "wget",
            "--no-check-certificate",  # تجاهل SSL
            "--timeout=60",
            "--tries=2",
            "--user-agent=Mozilla/5.0",
            "-O", out,
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            size_mb = os.path.getsize(out) / (1024 * 1024)
            logger.info(f"✅ wget نجح - الحجم: {size_mb:.2f} MB")
            return True
        else:
            logger.warning(f"⚠️ wget فشل: {result.stderr[:200]}")
            return False
            
    except Exception as e:
        logger.warning(f"⚠️ خطأ في wget: {str(e)}")
        return False

async def download_file(url, out):
    """محاولة التحميل بجميع الطرق"""
    # المحاولة الأولى: curl
    if await download_with_curl(url, out):
        return True
    
    # المحاولة الثانية: wget
    if await download_with_wget(url, out):
        return True
    
    # المحاولة الثالثة: Python مباشرة
    return await download_direct(url, out)

async def download_direct(url, out):
    """تحميل مباشر باستخدام Python"""
    import urllib.request
    try:
        logger.info(f"🎯 محاولة التحميل المباشر: {url}")
        
        # خدعة: إضافة headers لتجنب الحظر
        opener = urllib.request.build_opener()
        opener.addheaders = [
            ('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
            ('Accept', '*/*'),
            ('Accept-Language', 'en-US,en;q=0.9'),
            ('Referer', 'https://www.google.com/')
        ]
        urllib.request.install_opener(opener)
        
        # تجاهل SSL
        import ssl
        context = ssl._create_unverified_context()
        
        urllib.request.urlretrieve(url, out)
        
        if os.path.exists(out):
            size_mb = os.path.getsize(out) / (1024 * 1024)
            logger.info(f"✅ التحميل المباشر نجح - الحجم: {size_mb:.2f} MB")
            return True
        return False
        
    except Exception as e:
        logger.error(f"❌ التحميل المباشر فشل: {str(e)}")
        return False

def check_video(path):
    """فحص الفيديو بشكل أساسي"""
    if not os.path.exists(path):
        raise Exception("الملف غير موجود")
    
    size = os.path.getsize(path)
    logger.info(f"📊 حجم الملف: {size:,} بايت ({size/1024/1024:.2f} MB)")
    
    if size < 2 * 1024 * 1024:  # أقل من 2 ميجابايت
        logger.warning("⚠️ الملف صغير جداً، قد لا يكون فيديو حقيقي")
    
    # محاولة فحص الفيديو مع تجاهل الأخطاء
    try:
        cmd = ["ffprobe", "-v", "quiet", "-show_format", "-show_streams", path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.stdout:
            # البحث عن معلومات الفيديو
            if 'codec_type=video' in result.stdout:
                logger.info("🎥 تم اكتشاف تيار فيديو في الملف")
            else:
                logger.warning("⚠️ لم يتم اكتشاف تيار فيديو واضح")
    except Exception as e:
        logger.warning(f"⚠️ فحص الفيديو تخطى: {str(e)}")
    
    return True

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
    
    logger.info("=" * 60)
    logger.info("🚀 بدء عملية رفع الفيلم")
    logger.info(f"🎬 الفيلم: {MOVIE}")
    logger.info(f"📢 القناة: {CHANNEL}")
    logger.info("=" * 60)
    
    # 1. تحميل الصورة
    logger.info("\n" + "=" * 60)
    logger.info("📸 جاري تحميل الصورة...")
    logger.info(f"🔗 رابط الصورة: {POSTER_URL}")
    
    if not await download_file(POSTER_URL, POSTER):
        raise Exception("❌ فشل تحميل الصورة")
    
    # 2. تحميل الفيديو
    logger.info("\n" + "=" * 60)
    logger.info("🎥 جاري تحميل الفيديو...")
    logger.info(f"🔗 رابط الفيديو: {VIDEO_URL}")
    
    if not await download_file(VIDEO_URL, VIDEO):
        raise Exception("❌ فشل تحميل الفيديو بعد تجربة جميع الطرق")
    
    # 3. فحص الفيديو
    logger.info("\n" + "=" * 60)
    logger.info("🔍 جاري فحص الفيديو...")
    check_video(VIDEO)
    
    # 4. الاتصال بالتليجرام
    logger.info("\n" + "=" * 60)
    logger.info("🔗 جاري الاتصال بحساب التليجرام...")
    
    client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await client.connect()
    
    if not await client.is_user_authorized():
        raise Exception("❌ جلسة تليجرام غير صالحة")
    
    me = await client.get_me()
    logger.info(f"✅ تم الاتصال بـ @{me.username} ({me.first_name})")
    
    # 5. التحقق من القناة
    logger.info(f"🔍 جاري البحث عن القناة: {CHANNEL}")
    try:
        channel = await client.get_entity(CHANNEL)
        logger.info(f"📢 تم العثور على القناة: {channel.title}")
    except Exception as e:
        logger.error(f"❌ خطأ في العثور على القناة: {str(e)}")
        logger.info("💡 تأكد من:")
        logger.info("   1. رابط القناة صحيح")
        logger.info("   2. الحساب عضو في القناة")
        logger.info("   3. الحساب لديه صلاحية النشر")
        raise
    
    # 6. رفع الملفات
    logger.info("\n" + "=" * 60)
    logger.info("⬆️ جاري رفع الملفات إلى التليجرام...")
    
    try:
        # رفع الصورة
        logger.info("🖼️ رفع الصورة...")
        photo = await client.upload_file(
            POSTER,
            part_size_kb=512,
            file_name="poster.jpg"
        )
        logger.info("✅ تم رفع الصورة")
        
        # رفع الفيديو
        logger.info("🎥 رفع الفيديو (قد يستغرق وقتاً)...")
        video = await client.upload_file(
            VIDEO,
            part_size_kb=512,
            file_name=f"{MOVIE}.mp4"
        )
        logger.info("✅ تم رفع الفيديو")
        
        # 7. إرسال الرسالة
        logger.info("📤 جاري إرسال الرسالة...")
        
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
        
        message = await client.send_message(
            entity=channel,
            file=media,
            parse_mode='html'
        )
        
        # 8. عرض النتيجة
        logger.info("\n" + "=" * 60)
        logger.info("🎉 تم الرفع بنجاح!")
        logger.info(f"📝 معرف الرسالة: {message.id}")
        
        try:
            if hasattr(channel, 'username') and channel.username:
                message_link = f"https://t.me/{channel.username}/{message.id}"
            else:
                message_link = f"https://t.me/c/{str(abs(channel.id))}/{message.id}"
            logger.info(f"🔗 رابط الرسالة: {message_link}")
        except:
            pass
        
    except Exception as e:
        logger.error(f"❌ خطأ أثناء الرفع: {str(e)}")
        raise
    
    finally:
        await client.disconnect()
        logger.info("👋 تم قطع الاتصال")
        
        # تنظيف الملفات
        for file in [POSTER, VIDEO]:
            if os.path.exists(file):
                os.remove(file)
                logger.info(f"🗑️ تم حذف {file}")
    
    logger.info("\n" + "=" * 60)
    logger.info("🏁 العملية اكتملت بنجاح!")
    logger.info("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
        print("\n" + "🎉🎉🎉 تم الرفع بنجاح! 🎉🎉🎉")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n⚠️ تم إيقاف العملية بواسطة المستخدم")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌❌❌ فشل الرفع: {str(e)} ❌❌❌")
        sys.exit(1)
