# הוראות פריסה ל-Production

מדריך זה מסביר איך לפרוס את TicketSense.ai על פלטפורמות שונות.

## דרישות מוקדמות

1. **Google Service Account** - צריך ליצור Service Account ב-Google Cloud:
   - לך ל-[Google Cloud Console](https://console.cloud.google.com/)
   - צור פרויקט חדש (או השתמש בקיים)
   - לך ל-IAM & Admin > Service Accounts
   - צור Service Account חדש
   - הוסף Key (JSON) והורד את הקובץ
   - הפעל את Google Sheets API ו-Google Drive API
   - שתף את הגיליונות שלך עם כתובת ה-email של ה-Service Account

2. **Git Repository** - ודא שהקוד שלך ב-Git

## אפשרויות פריסה

### 1. Railway (מומלץ - פשוט ומהיר)

1. היכנס ל-[Railway](https://railway.app/)
2. לחץ על "New Project"
3. בחר "Deploy from GitHub repo"
4. בחר את ה-repository שלך
5. Railway יזהה אוטומטית את ה-Dockerfile
6. הוסף Environment Variables (אופציונלי):
   - `PORT` - Railway יקבע אוטומטית
7. לחץ על "Deploy"
8. לאחר הפריסה, פתח את האפליקציה והגדר את ה-Service Account JSON בהגדרות

**יתרונות:**
- פריסה אוטומטית מ-GitHub
- SSL אוטומטי
- חינם עם הגבלות מסוימות

### 2. Render

1. היכנס ל-[Render](https://render.com/)
2. לחץ על "New +" > "Web Service"
3. חבר את ה-GitHub repository שלך
4. הגדר:
   - **Name**: ticketsense (או שם אחר)
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. לחץ על "Create Web Service"
6. לאחר הפריסה, פתח את האפליקציה והגדר את ה-Service Account JSON

**יתרונות:**
- חינם עם הגבלות
- SSL אוטומטי
- פריסה אוטומטית

### 3. Heroku

1. היכנס ל-[Heroku](https://www.heroku.com/)
2. התקן את [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli)
3. הרץ:
   ```bash
   heroku login
   heroku create ticketsense-app
   git push heroku main
   ```
4. לאחר הפריסה:
   ```bash
   heroku open
   ```

**יתרונות:**
- יציב ומוכר
- תמיכה טובה

### 4. Docker (כל פלטפורמה)

1. בנה את ה-image:
   ```bash
   docker build -t ticketsense .
   ```

2. הרץ את הקונטיינר:
   ```bash
   docker run -p 8000:8000 ticketsense
   ```

3. לפריסה ב-production, השתמש ב-Docker Compose או Kubernetes

## הגדרת Google Service Account

לאחר הפריסה:

1. פתח את האפליקציה בכתובת שהוקצתה
2. לך ל-"הגדרות" (Settings)
3. הדבק את ה-JSON של ה-Service Account בשדה "Service Account JSON"
4. הזן את מזהי הגיליונות (Spreadsheet IDs)
5. לחץ "שמור"

**איך למצוא את Spreadsheet ID:**
- פתח את הגיליון ב-Google Sheets
- הכתובת תראה כך: `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`
- העתק את `SPREADSHEET_ID`

## בדיקת הפריסה

1. פתח את האפליקציה בדפדפן
2. לך ל-"הגדרות" והגדר את ה-Service Account
3. לך ל-"דשבורד" ולחץ "התחל" (הרץ ידני)
4. בדוק שהלוגים מופיעים וההקצאה עובדת

## פתרון בעיות

### שגיאת "Google Sheets not connected"
- ודא שה-Service Account JSON תקין
- ודא שהגיליונות משותפים עם כתובת ה-email של ה-Service Account
- ודא ש-Google Sheets API ו-Google Drive API מופעלים

### האפליקציה לא עולה
- בדוק את הלוגים בפלטפורמה (Railway/Render/Heroku)
- ודא שה-requirements.txt מעודכן
- ודא שה-PORT מוגדר נכון (Railway/Render קובעים אוטומטית)

### שגיאות כתיבה ל-Sheets
- ודא שה-Service Account יש לו הרשאות כתיבה
- בדוק שהעמודה K (column 11) קיימת בגיליון הכרטיסים

## הערות חשובות

- **אבטחה**: לעולם אל תעלה את `local_settings.json` ל-Git (הוא ב-.gitignore)
- **Backup**: שמור עותק של ה-Service Account JSON במקום בטוח
- **Logs**: הלוגים נשמרים בתיקיית `logs/` - בדוק אותם אם יש בעיות
