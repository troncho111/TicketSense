# פריסה מהירה - Quick Deploy Guide

## Railway (הכי פשוט - מומלץ!)

1. **היכנס ל-[Railway.app](https://railway.app/)**
2. **New Project** > **Deploy from GitHub repo**
3. בחר את ה-repo שלך
4. Railway יזהה את ה-Dockerfile אוטומטית
5. לחץ **Deploy**
6. לאחר הפריסה, פתח את האפליקציה והגדר את ה-Service Account JSON

**זמן פריסה: ~2 דקות**

---

## Render (חלופה טובה)

1. **היכנס ל-[Render.com](https://render.com/)**
2. **New +** > **Web Service**
3. חבר את ה-GitHub repo
4. הגדר:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. **Create Web Service**

---

## הגדרת Google Service Account

**לאחר הפריסה:**

1. פתח את האפליקציה
2. לך ל-**הגדרות**
3. הדבק את ה-JSON של Service Account בשדה "Service Account JSON"
4. הזן את מזהי הגיליונות
5. לחץ **שמור**

**איך ליצור Service Account:**
- [Google Cloud Console](https://console.cloud.google.com/)
- IAM & Admin > Service Accounts > Create Service Account
- Create Key (JSON) > Download
- הפעל Google Sheets API ו-Google Drive API
- שתף את הגיליונות עם כתובת ה-email של ה-Service Account

---

## בדיקה

1. פתח את האפליקציה
2. לך ל-**דשבורד**
3. לחץ **התחל** (הרץ ידני)
4. בדוק שהלוגים מופיעים

**אם יש בעיות - ראה [DEPLOYMENT.md](DEPLOYMENT.md) לפרטים מלאים**
