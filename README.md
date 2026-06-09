# 🤖 Telegram Bot — One-Click Deploy

## 🚀 التشغيل الأول (Setup Mode)

```bash
python installer.py
```

سيطلب منك البيانات مرة واحدة ثم يُشغّل البوت تلقائياً.

## ⚙️ المتطلبات

```
python >= 3.10
pip install -r requirements.txt
```

## 🔑 متغيرات البيئة

| المتغير | الوصف |
|---------|-------|
| BOT_TOKEN | توكن البوت من @BotFather |
| API_ID | من my.telegram.org |
| API_HASH | من my.telegram.org |
| ADMIN_ID | معرفك الرقمي في تيليجرام |

## 📁 بنية المشروع

```
bot.py           ← نقطة الدخول الرئيسية
installer.py     ← معالج الإعداد الأول
requirements.txt ← المتطلبات
src/
  handlers/      ← معالجات الأوامر
  keyboards.py   ← لوحات المفاتيح
  states.py      ← حالات FSM
  database.py    ← قاعدة البيانات
  ...
```

## 🌐 الاستضافة

يعمل على أي بيئة تدعم Python 3.10+:
- VPS (Ubuntu / Debian / CentOS)
- Replit
- Railway
- Render
- Heroku
