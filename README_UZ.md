# Korxona hisob-kitob Telegram boti

## Imkoniyatlar
- Xodimning Telegram ID si orqali kirish va admin tasdig'i
- Kirim va chiqim yozuvlari
- UZS va USD alohida hisoblanadi (valyuta konvertatsiyasi yo'q)
- Balans va umumiy hisobot
- Xodimning oxirgi 10 ta yozuvi
- Admin: xodimlarni tasdiqlash/bloklash, foydalanuvchilarni ko'rish, CSV eksport
- SQLite ma'lumotlar bazasi

## 1. Telegram bot tokenini olish
1. Telegramda `@BotFather` ni oching.
2. `/newbot` yuboring va bot nomi hamda username tanlang.
3. BotFather bergan tokenni maxfiy saqlang. Uni hech kimga yubormang.

## 2. Admin Telegram ID sini topish
Telegramda `@userinfobot` kabi ID ko'rsatuvchi botdan o'zingizning raqamli Telegram ID ingizni bilib oling. ID ni token bilan adashtirmang.

## 3. O'rnatish (kompyuter yoki server)
Python 3.10+ o'rnating. Ushbu papkada terminal ochib:

```bash
python -m venv .venv
```

Windows:
```powershell
.venv\Scripts\activate
pip install -r requirements.txt
$env:BOT_TOKEN="BOTFATHER_BERGAN_TOKEN"
$env:ADMIN_IDS="123456789"
python bot.py
```

Linux/macOS:
```bash
source .venv/bin/activate
pip install -r requirements.txt
export BOT_TOKEN="BOTFATHER_BERGAN_TOKEN"
export ADMIN_IDS="123456789"
python bot.py
```

Bir nechta admin kerak bo'lsa: `ADMIN_IDS="123456789,987654321"`.

## 4. Ishlatish
1. Botni ishga tushirgach Telegramda botni oching va `/start` bosing.
2. Admin ID si `ADMIN_IDS` da ko'rsatilgan bo'lsa, admin bo'lib kiradi.
3. Xodim `/start` bosganda, adminlarga tasdiqlash so'rovi keladi.
4. Admin so'rov tugmasi orqali tasdiqlaydi yoki `/pending` bilan kutayotganlarni ko'radi.
5. Kirim/chiqim qo'shing, valyuta va kategoriya tanlang.
6. Admin `/export` bilan barcha yozuvlarni CSV ko'rinishida olishi mumkin.

## Admin buyruqlari
- `/admin` — yordam
- `/pending` — ruxsat kutayotganlar
- `/users` — foydalanuvchilar ro'yxati
- `/approve USER_ID` — xodimni tasdiqlash
- `/disable USER_ID` — bloklash
- `/export` — CSV eksport

## Muhim xavfsizlik eslatmalari
- Bu boshlang'ich MVP; real moliyaviy hisobda ishlatishdan oldin sinovdan o'tkazing.
- Bot doimiy ishlashi uchun kompyuter o'chmay turishi yoki 24/7 server kerak.
- `hisob_bot.db` faylini muntazam zaxiralang va unga kirishni cheklang.
- Tokenni kodga yozmang va ommaga chiqarmang. Token oshkor bo'lsa, BotFather orqali yangilang.
- Hozirgi versiyada UZS va USD alohida ko'rsatiladi; dollarni so'mga avtomatik aylantirmaydi.
- Xodimlar o'z yozuvlarini ko'radi; admin umumiy balans va barcha yozuvlarni ko'radi.
- Hisob-kitobni buxgalteriya yoki soliq hisoboti o'rnida ishlatishdan oldin mutaxassis tekshiruvidan o'tkazing.
