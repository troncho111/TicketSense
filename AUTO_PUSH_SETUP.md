# הגדרת דחיפה אוטומטית ל-GitHub

## מה זה עושה?

כל פעם שתעשה `git commit`, הקוד יידחף אוטומטית ל-GitHub.

## איך להפעיל?

### Windows:
```bash
.\setup-auto-push.bat
```

### Linux/Mac:
```bash
chmod +x setup-auto-push.sh
./setup-auto-push.sh
```

## איך זה עובד?

הסקריפט יוצר Git hook (`.git/hooks/post-commit`) שרץ אוטומטית אחרי כל commit ודוחף את השינויים ל-GitHub.

## בדיקה

לבדוק שזה עובד:
```bash
git commit --allow-empty -m "Test auto-push"
```

אם הכל תקין, תראה:
```
🚀 Auto-pushing to GitHub...
To https://github.com/troncho111/TicketSense.git
   ... -> main
```

## הערות

- זה יעבוד רק על המחשב שבו הפעלת את הסקריפט
- אם אתה עובד על כמה מחשבים, תצטרך להפעיל את זה על כל אחד
- אם אתה לא רוצה auto-push, פשוט תמחק את `.git/hooks/post-commit`

## GitHub Actions

בנוסף, יש GitHub Actions workflows שרצים אוטומטית על כל push:
- **auto-push.yml** - בודק שהקוד עובד (tests)
- **deploy-railway.yml** - פריסה אוטומטית ל-Railway (דורש RAILWAY_TOKEN ב-Secrets)
