#!/usr/bin/env python3
"""
سكريبت التشغيل المحلي مع دعم ملف .env
"""

import os
from dotenv import load_dotenv

# تحميل المتغيرات من .env
load_dotenv()

# تعيين GITHUB_ACTIONS ك false
os.environ['GITHUB_ACTIONS'] = 'false'

# تشغيل البرنامج الرئيسي
from main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
