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
from telethon.tl.types import DocumentAttributeFilename
import requests
import ssl
import urllib3

# تجاوز أخطاء SSL بشكل آمن عند الحاجة
if os.getenv('SKIP_SSL_VERIFY', 'false').lower() == 'true':
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    ssl._create_default_https_context = ssl._create_unverified_context

async def validate_and_download_file(url, save_dir, filename, keep_original_ext=False, force_ext=None):
    """تنزيل الملف مع التحقق من الصحة ومعالجة الأخطاء"""
    try:
        verify_ssl = os.getenv('SKIP_SSL_VERIFY', 'false').lower() != 'true'
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        if 'github.com' in url and os.getenv('REPO_TOKEN'):
            headers['Authorization'] = f'token {os.getenv("REPO_TOKEN")}'
        
        response = requests.get(url, stream=True, verify=verify_ssl, headers=headers, timeout=300)
        response.raise_for_status()
        
        # تحديد الامتداد تلقائياً
        if keep_original_ext:
            parsed_url = urlparse(url)
            ext = os.path.splitext(parsed_url.path)[1].lower()
            if not ext or len(ext) > 5:
                content_type = response.headers.get('content-type', '')
                ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or '.bin'
        else:
            ext = f'.{force_ext}' if force_ext else '.mp4'
        
        safe_filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filepath = Path(save_dir) / f"{safe_filename}{ext}"
        
        # تنزيل الملف بتتابع لتجنب استهلاك الذاكرة
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        if not filepath.exists() or filepath.stat().st_size == 0:
            raise Exception(f"فشل التنزيل: الملف {filepath.name} فارغ أو غير موجود")
        
        print(f"✓ تم تنزيل {filepath.name} بنجاح ({filepath.stat().st_size / 1024 / 1024:.2f} MB)")
        return str(filepath)
    
    except Exception as e:
        raise Exception(f"خطأ في تنزيل {url}: {str(e)}")

async def upload_to_telegram():
    # ============ التحقق من المتغيرات المطلوبة ============
    required_vars = ['MODE', 'CHANNEL', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION_STRING']
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise Exception(f"المتغيرات المطلوبة غير مكتملة: {', '.join(missing)}")
    
    mode = os.getenv('MODE', '').lower()
    channel = os.getenv('CHANNEL', '')
    caption = os.getenv('CAPTION', '')
    
    if mode not in ['movie', 'series']:
        raise Exception("الوضع غير صحيح! يجب أن يكون 'movie' أو 'series'")
    
    if not channel:
        raise Exception("رابط القناة مطلوب")
    
    # ============ إعداد عميل التيليجرام ============
    api_id = int(os.getenv('TELEGRAM_API_ID', '0'))
    api_hash = os.getenv('TELEGRAM_API_HASH', '')
    session_str = os.getenv('TELEGRAM_SESSION_STRING', '')
    
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    
    # ============ معالجة الملفات في مجلد مؤقت ============
    with tempfile.TemporaryDirectory() as tmp_dir:
        media_files = []
        
        try:
            if mode == 'movie':
                # ============ وضع الأفلام ============
                image_url = os.getenv('IMAGE_URL', '')
                video_url = os.getenv('VIDEO_URL', '')
                video_name = os.getenv('VIDEO_NAME', 'movie').strip() or 'movie'
                
                if not image_url or not video_url:
                    raise Exception("في وضع الأفلام: مطلوب رابط الصورة ورابط الفيديو")
                
                # تنزيل الصورة باسم تلقائي Logo مع الامتداد الأصلي
                image_path = await validate_and_download_file(
                    image_url, 
                    tmp_dir, 
                    'Logo', 
                    keep_original_ext=True
                )
                media_files.append(image_path)
                
                # تنزيل الفيديو مع تعديل الاسم مع الحفاظ على .mp4
                video_path = await validate_and_download_file(
                    video_url, 
                    tmp_dir, 
                    video_name, 
                    keep_original_ext=False,
                    force_ext='mp4'
                )
                media_files.append(video_path)
                
                print(f"🎬 وضع الأفلام: صورة + فيديو (الاسم: {video_name}.mp4)")
            
            else:  # mode == 'series'
                # ============ وضع المسلسلات ============
                try:
                    series_data = json.loads(os.getenv('SERIES_VIDEOS', '[]'))
                except json.JSONDecodeError:
                    raise Exception("بيانات المسلسلات غير صحيحة! يجب أن تكون بصيغة JSON صالحة")
                
                if not isinstance(series_data, list) or len(series_data) == 0:
                    raise Exception("مطلوب على الأقل ملف فيديو واحد للمسلسلات")
                
                if len(series_data) > 10:
                    print(f"⚠️ تم اكتشاف {len(series_data)} ملفات، سيتم رفع أول 10 ملفات فقط")
                    series_data = series_data[:10]
                
                for idx, item in enumerate(series_data, 1):
                    if not isinstance(item, dict) or 'url' not in item:
                        continue
                    
                    url = item['url'].strip()
                    name = item.get('name', f'Episode_{idx}').strip() or f'Episode_{idx}'
                    
                    if not url:
                        continue
                    
                    video_path = await validate_and_download_file(
                        url, 
                        tmp_dir, 
                        name, 
                        keep_original_ext=False,
                        force_ext='mp4'
                    )
                    media_files.append(video_path)
                    print(f"📺 تم إعداد الملف {idx}: {name}.mp4")
                
                print(f"📼 وضع المسلسلات: {len(media_files)} ملفات فيديو جاهزة للرفع")
            
            # ============ رفع الملفات على التيليجرام ============
            print(f"\n📤 جاري الرفع على القناة: {channel}")
            print(f"📝 الكابشن: {caption[:50]}..." if len(caption) > 50 else f"📝 الكابشن: {caption}")
            
            async with client:
                # التحقق من صحة القناة
                try:
                    entity = await client.get_entity(channel)
                except Exception as e:
                    raise Exception(f"فشل العثور على القناة {channel}: {str(e)}")
                
                # رفع الملفات كـ Media Group
                await client.send_file(
                    entity,
                    media_files,
                    caption=caption,
                    supports_streaming=True,
                    force_document=False,
                    parse_mode='html'
                )
            
            print("\n✅ تم الرفع بنجاح!")
            print(f"📊 ملخص العملية:")
            print(f"   - الوضع: {'فيلم' if mode == 'movie' else 'مسلسل'}")
            print(f"   - عدد الملفات: {len(media_files)}")
            print(f"   - القناة: {channel}")
        
        except Exception as e:
            print(f"\n❌ فشل العملية: {str(e)}", file=sys.stderr)
            sys.exit(1)
        finally:
            # تنظيف الملفات المؤقتة
            for file in media_files:
                try:
                    Path(file).unlink(missing_ok=True)
                except:
                    pass

if __name__ == "__main__":
    try:
        print("="*60)
        print("🚀 سكريبت رفع المحتوى على تيليجرام - GitHub Actions")
        print("="*60)
        print(f"⏰ الوقت: {os.getenv('GITHUB_RUN_ID', 'Local Run')}")
        print(f"🔧 الوضع: {os.getenv('MODE', 'غير محدد')}")
        print("="*60 + "\n")
        
        asyncio.run(upload_to_telegram())
        
    except KeyboardInterrupt:
        print("\n⚠️ تم إلغاء العملية يدوياً", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 خطأ فادح: {str(e)}", file=sys.stderr)
        sys.exit(1)
