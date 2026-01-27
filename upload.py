#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import tempfile
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors.rpcerrorlist import UserAlreadyParticipantError, InviteHashInvalidError, InviteHashExpiredError
import requests
import ssl
import urllib3

# تجاوز SSL عالمياً عند التفعيل
if os.getenv('SKIP_SSL_VERIFY', 'false').lower() == 'true':
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    ssl._create_default_https_context = ssl._create_unverified_context

# ⚠️ الحد الأقصى لحجم الفيديو: 2047 ميجابايت
MAX_VIDEO_SIZE_MB = 2047
MAX_VIDEO_SIZE_BYTES = MAX_VIDEO_SIZE_MB * 1024 * 1024

def sanitize_filename(filename):
    """تنقية اسم الملف مع الحفاظ على النقاط المهمة"""
    return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip().rstrip('.')

async def validate_and_download_file(url, save_dir, base_name, is_image=False):
    """تنزيل الملف مع فحص الحجم ومعالجة الأخطاء"""
    url = url.strip()
    
    if not url:
        raise Exception("❌ رابط فارغ بعد التنقية!")
    
    try:
        skip_ssl = os.getenv('SKIP_SSL_VERIFY', 'false').lower() == 'true'
        verify_ssl = not skip_ssl
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        if 'github.com' in url and os.getenv('REPO_TOKEN'):
            headers['Authorization'] = f'token {os.getenv("REPO_TOKEN")}'
        
        print(f"⬇️  جاري تنزيل: {url[:60]}...")
        print(f"   SSL Verification: {'معطل' if skip_ssl else 'مفعل'}")
        
        response = requests.get(
            url, 
            stream=True, 
            verify=verify_ssl,
            headers=headers, 
            timeout=900
        )
        response.raise_for_status()
        
        # تحديد الامتداد
        if is_image:
            ext = os.path.splitext(urlparse(url).path)[1].lower()
            if not ext or len(ext) > 5 or ext in ['.php', '.asp']:
                content_type = response.headers.get('content-type', '')
                ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or '.jpg'
            filepath = Path(save_dir) / f"Logo{ext}"
        else:
            base_name = sanitize_filename(base_name)
            if base_name.lower().endswith('.mp4'):
                base_name = base_name[:-4]
            filepath = Path(save_dir) / f"{base_name}.mp4"
        
        # تنزيل مع فحص الحجم أثناء التنزيل
        total_size = 0
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)
                    
                    if not is_image and total_size > MAX_VIDEO_SIZE_BYTES * 1.1:
                        f.close()
                        filepath.unlink(missing_ok=True)
                        raise Exception(
                            f"❌ توقف التنزيل: حجم الملف تجاوز {MAX_VIDEO_SIZE_MB} ميجابايت أثناء التنزيل!\n"
                            f"الحجم الحالي: {total_size / 1024 / 1024:.2f} ميجابايت"
                        )
        
        if total_size == 0:
            raise Exception("الملف فارغ بعد التنزيل")
        
        # فحص الحد الأقصى للفيديو
        if not is_image:
            file_size_mb = total_size / 1024 / 1024
            if total_size > MAX_VIDEO_SIZE_BYTES:
                filepath.unlink(missing_ok=True)
                raise Exception(
                    f"❌ حجم الفيديو '{filepath.name}' ({file_size_mb:.2f} ميجابايت) "
                    f"يتجاوز الحد المسموح (2047 ميجابايت).\n"
                    f"الحل: قسّم الفيديو إلى أجزاء أصغر أو استخدم جودة أقل."
                )
            print(f"✅ تم التنزيل: {filepath.name} ({file_size_mb:.2f} ميجابايت) ✓")
        else:
            print(f"✅ تم التنزيل: {filepath.name} ({total_size / 1024 / 1024:.2f} ميجابايت)")
        
        return str(filepath)
    
    except requests.exceptions.SSLError as e:
        raise Exception(
            f"❌ خطأ SSL: الموقع يستخدم شهادة غير موثوقة.\n"
            f"الحل: فعّل 'skip_ssl = true' في إعدادات الـ Workflow."
        )
    except Exception as e:
        if 'filepath' in locals() and Path(filepath).exists():
            Path(filepath).unlink(missing_ok=True)
        raise Exception(f"❌ فشل تنزيل {url[:50]}...: {str(e)}")

async def resolve_channel(client, channel_input):
    """
    معالجة ذكية لمعرفات القنوات:
    - يدعم @channelname
    - يدعم روابط الدعوة الكاملة (https://t.me/+Abc123)
    - يدعم كود الدعوة المباشر (+Abc123)
    - يتعامل تلقائياً مع حالة "العضو موجود مسبقاً"
    """
    channel_input = channel_input.strip()
    
    # الخطوة 1: محاولة الحصول المباشر (للمعرفات العادية)
    try:
        entity = await client.get_entity(channel_input)
        print(f"✅ تم العثور على القناة مباشرة: {getattr(entity, 'title', channel_input)}")
        return entity
    except Exception as e:
        print(f"ℹ️  المحاولة المباشرة فشلت: {str(e)[:60]}")
    
    # الخطوة 2: معالجة روابط الدعوة (بجميع أشكالها)
    if '+' in channel_input:
        try:
            # استخراج كود الدعوة من أي شكل من الأشكال
            if 't.me/+' in channel_input or 'telegram.me/+' in channel_input:
                hash_part = channel_input.split('+')[-1].split('?')[0].split('&')[0].strip('/')
            else:
                hash_part = channel_input.lstrip('+').split()[0].strip()
            
            if not hash_part or len(hash_part) < 5:
                raise Exception("كود الدعوة غير صالح (قصير جداً)")
            
            print(f"🔍 معالجة رابط الدعوة: +{hash_part}")
            
            # محاولة 1: استخدام الرابط الكامل للحصول على القناة دون انضمام
            full_url = f"https://t.me/joinchat/{hash_part}"
            try:
                entity = await client.get_entity(full_url)
                print(f"✅ تم العثور على القناة عبر الرابط الكامل: {getattr(entity, 'title', 'غير معروف')}")
                return entity
            except Exception as e:
                print(f"ℹ️  فشل المحاولة الأولى: {str(e)[:50]}")
            
            # محاولة 2: الانضمام (إذا لزم الأمر)
            try:
                print(f"🔗 محاولة الانضمام للقناة (إذا لزم)...")
                result = await client(ImportChatInviteRequest(hash_part))
                chat = result.chats[0] if result.chats else None
                if chat:
                    print(f"✅ تم الانضمام للقناة: {getattr(chat, 'title', 'بدون اسم')}")
                    return chat
            except UserAlreadyParticipantError:
                print("ℹ️  الحساب منضم للقناة مسبقاً - جاري البحث في القنوات المنضمة...")
                # البحث في القنوات المنضمة (بدون مسح جميع القنوات)
                async for dialog in client.iter_dialogs(limit=100):
                    if dialog.is_channel:
                        try:
                            # محاولة الحصول على رابط الدعوة لكل قناة (للتحقق من المطابقة)
                            # ملاحظة: هذه الطريقة قد لا تعمل مع جميع القنوات الخاصة
                            if dialog.entity.username is None:  # قناة خاصة
                                # نستخدم مقاربة بديلة: محاولة إرسال رسالة تجربة؟ لا نفعل ذلك لأمان المستخدم
                                # نعتمد على أن القناة ستظهر في أول 100 قناة منضمة
                                # ونفترض أن المستخدم يريد القناة الأخيرة التي انضم لها (الأعلى في القائمة)
                                # لكن هذا غير دقيق، لذا نستخدم حل أفضل:
                                # نعيد محاولة الرابط الكامل مرة أخرى بعد التأكد من الانضمام
                                pass
                        except:
                            pass
                
                # الحل الأكيد: إعادة محاولة الرابط الكامل بعد التأكد من الانضمام
                try:
                    entity = await client.get_entity(full_url)
                    print(f"✅ تم العثور على القناة (بعد التحقق من الانضمام المسبق): {getattr(entity, 'title', 'غير معروف')}")
                    return entity
                except Exception as e:
                    raise Exception(
                        "فشل العثور على القناة رغم أن الحساب منضم مسبقاً.\n"
                        "السبب المحتمل: رابط الدعوة انتهى صلاحيته أو تم تغييره.\n"
                        "الحل الفوري:\n"
                        "  1. افتح رابط الدعوة يدوياً في تطبيق تيليجرام وأنضم مرة أخرى\n"
                        "  2. استخدم معرف القناة العادي (@channel) إذا كانت عامة\n"
                        "  3. أعد إنشاء رابط دعوة جديد من إعدادات القناة"
                    )
            except (InviteHashInvalidError, InviteHashExpiredError) as e:
                raise Exception(
                    f"رابط الدعوة غير صالح أو منتهي الصلاحية!\n"
                    f"الحل: احصل على رابط دعوة جديد من مالك القناة."
                )
            except Exception as e:
                raise Exception(f"فشل الانضمام للقناة: {str(e)}")
        
        except Exception as e:
            raise Exception(
                f"فشل معالجة رابط الدعوة '{channel_input}': {str(e)}\n"
                "الحلول المطلوبة:\n"
                "  • إذا كانت القناة عامة: استخدم @channelname بدلاً من رابط الدعوة\n"
                "  • إذا كانت خاصة: تأكد من صحة رابط الدعوة وأنه لم ينتهِ صلاحيته"
            )
    
    # إذا فشلت جميع المحاولات
    raise Exception(
        f"فشل العثور على القناة '{channel_input}'\n"
        "التنسيقات المدعومة:\n"
        "  • للقنوات العامة: @yourchannel\n"
        "  • لروابط الدعوة: +Abc123 أو https://t.me/+Abc123"
    )

async def main():
    print("="*70)
    print("🚀 سكريبت رفع المحتوى على تيليجرام - الإصدار النهائي")
    print("="*70)
    print(f"⚠️  الحد الأقصى للفيديو: {MAX_VIDEO_SIZE_MB} ميجابايت")
    print("="*70)
    
    # التحقق من المتغيرات الأساسية
    required = ['MODE', 'CHANNEL', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION_STRING']
    missing = [v for v in required if not os.getenv(v, '').strip()]
    if missing:
        raise Exception(f"❌ المتغيرات الناقصة: {', '.join(missing)}")
    
    mode = os.getenv('MODE', '').strip().lower()
    channel = os.getenv('CHANNEL', '').strip()
    caption = os.getenv('CAPTION', '').replace('\\n', '\n').strip()
    
    if mode not in ['movie', 'series']:
        raise Exception("❌ الوضع غير مدعوم! اختر 'movie' أو 'series'")
    
    if not channel:
        raise Exception("❌ حقل القناة فارغ!")
    
    # إعداد العميل
    try:
        client = TelegramClient(
            StringSession(os.getenv('TELEGRAM_SESSION_STRING')),
            int(os.getenv('TELEGRAM_API_ID')),
            os.getenv('TELEGRAM_API_HASH')
        )
        await client.start()
        me = await client.get_me()
        print(f"✅ تم تسجيل الدخول كـ: {me.first_name} (@{me.username if me.username else 'لا يوجد يوزرنيم'})")
    except Exception as e:
        raise Exception(f"❌ فشل تسجيل الدخول: {str(e)}")
    
    # معالجة الملفات
    with tempfile.TemporaryDirectory() as tmp_dir:
        media = []
        try:
            if mode == 'movie':
                img_url = os.getenv('IMAGE_URL', '').strip()
                vid_url = os.getenv('VIDEO_URL', '').strip()
                vid_name = os.getenv('VIDEO_NAME', 'movie').strip() or 'movie'
                
                if not img_url or not vid_url:
                    raise Exception("❌ في وضع الأفلام: مطلوب رابط الصورة ورابط الفيديو")
                
                print("\n🎬 معالجة وضع الأفلام...")
                media.append(await validate_and_download_file(img_url, tmp_dir, 'Logo', is_image=True))
                media.append(await validate_and_download_file(vid_url, tmp_dir, vid_name, is_image=False))
                print(f"✅ جاهز للرفع: صورة + فيديو ({Path(media[1]).name})")
            
            else:  # series
                try:
                    series = json.loads(os.getenv('SERIES_VIDEOS', '[]'))
                except Exception as e:
                    raise Exception(f"❌ خطأ في تنسيق JSON: {str(e)}")
                
                if not isinstance(series, list) or not series:
                    raise Exception("❌ مطلوب على الأقل ملف فيديو واحد")
                
                if len(series) > 10:
                    print(f"⚠️  سيتم رفع أول 10 ملفات فقط (الحد الأقصى للتليجرام)")
                    series = series[:10]
                
                print(f"\n📼 معالجة {len(series)} ملف للمسلسلات...")
                for i, item in enumerate(series, 1):
                    if not isinstance(item, dict) or 'url' not in item:
                        print(f"⚠️  تخطي العنصر {i}: تنسيق غير صالح")
                        continue
                    
                    url = item['url'].strip()
                    name = item.get('name', f'الحلقة_{i}').strip() or f'الحلقة_{i}'
                    
                    if not url:
                        print(f"⚠️  تخطي العنصر {i}: رابط فارغ")
                        continue
                    
                    try:
                        media.append(await validate_and_download_file(url, tmp_dir, name, is_image=False))
                        print(f"✅ تمت إضافة: {Path(media[-1]).name}")
                    except Exception as e:
                        print(f"❌ فشل معالجة الملف {i} ({name}): {str(e)}")
                        if len(media) == 0:
                            raise Exception("فشل جميع ملفات المسلسلات - لا يمكن المتابعة")
                        else:
                            print("⚠️  سيتم الرفع بالملفات الناجحة فقط")
                            break
            
            # الرفع
            print(f"\n📤 جاري الرفع على القناة: {channel}")
            print(f"📝 الكابشن: {caption[:60] + '...' if len(caption) > 60 else caption}")
            
            entity = await resolve_channel(client, channel)
            
            await client.send_file(
                entity,
                media,
                caption=caption,
                supports_streaming=True,
                force_document=False,
                parse_mode='html'
            )
            
            print("\n" + "="*70)
            print("✅ تم الرفع بنجاح!")
            print("="*70)
            print(f"📊 ملخص:")
            print(f"   - الوضع: {'فيلم' if mode == 'movie' else 'مسلسل'}")
            print(f"   - الملفات: {len(media)}")
            print(f"   - القناة: {getattr(entity, 'title', channel)}")
            print(f"   - الحد الأقصى: {MAX_VIDEO_SIZE_MB} ميجابايت ✓")
            print("="*70)
        
        finally:
            for f in media:
                try:
                    Path(f).unlink(missing_ok=True)
                except:
                    pass
            await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  تم الإلغاء يدوياً", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"❌ خطأ: {str(e)}", file=sys.stderr)
        print(f"{'='*70}", file=sys.stderr)
        
        error_msg = str(e).lower()
        if "ssl" in error_msg or "certificate" in error_msg:
            print("\n💡 الحل:", file=sys.stderr)
            print("   • فعّل 'skip_ssl = true' في إعدادات الـ Workflow", file=sys.stderr)
        elif "2047" in error_msg or "size" in error_msg or "حجم" in error_msg:
            print("\n💡 الحل:", file=sys.stderr)
            print(f"   • قسّم الفيديو إلى أجزاء ≤ {MAX_VIDEO_SIZE_MB} ميجابايت", file=sys.stderr)
        elif "invite" in error_msg or "channel" in error_msg or "قناة" in error_msg:
            print("\n💡 الحل الفوري:", file=sys.stderr)
            print("   1. افتح هذا الرابط يدوياً في تيليجرام وأنضم للقناة:", file=sys.stderr)
            print(f"      https://t.me/+{os.getenv('CHANNEL', '').lstrip('+').strip()}", file=sys.stderr)
            print("   2. شغّل الـ Workflow مجدداً بنفس الإعدادات", file=sys.stderr)
            print("   3. إذا استمر الخطأ: استخدم معرف القناة العادي (@channel)", file=sys.stderr)
        
        sys.exit(1)
