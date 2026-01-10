# כל הלוגיקה מאחורי השיבוץ - Allocation Logic

## 📋 סיכום כללי

**זה לא AI** - זה **Rule-Based System** (מערכת מבוססת כללים).
המערכת עובדת לפי כללים ברורים וקבועים, ללא למידה או החלטות "אינטליגנטיות".

---

## 🎯 תהליך השיבוץ - Step by Step

### שלב 1: קריאת נתונים
1. קורא הזמנות מ-Google Sheets (Orders Sheet)
2. קורא כרטיסים מ-Google Sheets (Tickets Sheet)
3. בודק אילו הזמנות כבר שובצו (עמודה K לא ריקה)

### שלב 2: מיון הזמנות
- **עדיפות ראשונה (ABSOLUTE PRIORITY)**: הזמנות עם בלוק ספציפי (למשל: "CATEGORY 1 304")
- **עדיפות שנייה**: הזמנות לפי קטגוריה (מסודרות לפי priority_order)

### שלב 3: לכל הזמנה - מציאת בלוקים מותרים

#### 3.1 בדיקת בלוק ספציפי
אם הקטגוריה מכילה מספר בלוק בסוף (למשל: "CATEGORY 1 304"):
- משתמש **רק** בבלוק הזה
- **דילוג על כל המיפוי** - זה בלוק ספציפי!

#### 3.2 מיפוי קטגוריה → בלוקים
- קורא את `category_mapping/{source}.json`
- מחפש התאמה גמישה (flexible matching):
  - התאמה מדויקת
  - התאמה חלקית
  - עיבוד של קיצורים (CAT1 → CATEGORY 1)

#### 3.3 הוספת Upgrade Options
- מוסיף בלוקים מקטגוריות טובות יותר (upgrade)
- בודק הגבלות (למשל: Shortside → Lateral חסום)
- משתמש ב-`category_hierarchy.json` לקביעת היררכיה

#### 3.4 מיון בלוקים לפי Exclusivity
1. **בלוקים Exclusive** (רק המקור הנוכחי) - ראשונים
2. **בלוקים Shared** (מספר מקורות) - אחר כך
3. **בתוך כל קבוצה**: מיון לפי מספר בלוק (גבוה = זול = ראשון)

### שלב 4: סינון כרטיסים (Candidates)

לכל כרטיס, בודק:
1. ✅ **Game Match**: האם המשחק תואם? (flexible matching - מחפש שמות קבוצות)
2. ✅ **Block Match**: האם הבלוק מותר? (כולל TixStock translations)
3. ✅ **Not Assigned**: האם הכרטיס לא שובץ כבר? (עמודה K ריקה)

אם כל התנאים מתקיימים → הופך ל-**Candidate**

### שלב 5: סיווג כרטיסים (Seat Classification)

המערכת מסווגת כל כרטיס ל:
- **SINGLE**: כרטיס בודד (אין כרטיסים סמוכים)
- **PAIR**: זוג כרטיסים צמודים (diff = 2)
- **"N together"**: 3+ כרטיסים צמודים
- **SCH**: Single Center Half (כרטיסים עם פער מושב אחד, diff = 4)
- **SCH-N**: SCH עם N פערים

**איך זה עובד:**
1. מקבץ לפי (game, block, row)
2. מפריד לפי parity (זוגי/אי-זוגי)
3. מחפש רצפים עם diff = 2 (צמודים)
4. מחפש SCH עם diff = 4 (פער מושב אחד)
5. מחפש SCH diagonal (שורה אחרת, מושב ±2/0)

### שלב 6: שיבוץ לפי סוג הזמנה

#### 6.1 SINGLE (1 כרטיס)

**חוקים:**
1. **IRON RULE**: אם יש SINGLE אמיתי → משתמש רק בו
2. **Specific Block Order**: אם הזמנה לבלוק ספציפי → יכול לפרק PAIR
3. **Fallback**: אם אין SINGLE → לפי `single_rule`:
   - `strict_single_only = true` → דחייה
   - `strict_single_only = false` → משתמש ב-PAIR או SCH

#### 6.2 MULTIPLE (2+ כרטיסים)

**חוקים:**
1. **STRICT RULE**: כל הכרטיסים חייבים להיות באותו בלוק ושורה
2. **Adjacent Rule**: 
   - צמודים = diff 2 ✅
   - SCH gap = diff 4 ✅ (רק אם המקור מאפשר SCH)
   - Gap גדול יותר = diff 6+ ❌ (אף פעם לא!)
3. **Max 1 SCH gap**: מותר מקסימום פער SCH אחד

**Priority לפי מקור:**
- **livefootballtickets**: רק PAIR (לא SCH)
- **footballticketnet**: SCH לפני PAIR
- **sportsevents365**: SCH לפני PAIR
- **goldenseat**: PAIR לפני SCH (הפוך!)
- **tixstock**: רק PAIR (לא SCH)

**מיון:**
1. Strictly adjacent (ללא SCH gaps) - עדיפות ראשונה
2. With SCH gap (1 פער) - עדיפות שנייה (רק אם מותר)
3. בתוך כל קבוצה: מיון לפי מספר בלוק (גבוה = זול)

---

## 📜 כל הכללים (Rules)

### Iron Rules (לא ניתן לשנות!)

1. **Specific Block Priority**: הזמנות עם בלוק ספציפי = עדיפות מוחלטת
2. **Don't Break Groups**: לא לפרק PAIR/SCH/Group אם יש SINGLE
3. **Never Reassign**: לא לשבץ כרטיס שכבר שובץ (עמודה K)
4. **Game Must Match**: כרטיס חייב להיות לאותו משחק
5. **Block Must Be Allowed**: כרטיס חייב להיות בבלוק מותר
6. **No Large Gaps**: diff 6+ = אף פעם לא מותר

### Configurable Rules (ניתן לשנות ב-`seating_rules.json`)

#### Single Rule
```json
"single_rule": {
  "strict_single_only": false,
  "behavior_if_no_single": "USE_PAIR"
}
```

#### SCH Allowance (לפי מקור)
```json
"sources": {
  "livefootballtickets": {"allow_sch": false},
  "footballticketnet": {"allow_sch": true},
  "goldenseat": {"allow_sch": true, "sch_priority": "last"}
}
```

#### Pairing Priority
```json
"pairing_priority": {
  "when_allow_sch": ["SCH", "PAIR"],      // SCH לפני PAIR
  "when_disallow_sch": ["PAIR"],          // רק PAIR
  "goldenseat_priority": ["PAIR", "SCH"]  // PAIR לפני SCH
}
```

#### Protection Rules
```json
"protection": {
  "do_not_break_groups_for_smaller_orders": true,
  "protect_group_sizes": [4, 5, 6]
}
```

### Business Rules (ניתן לשנות ב-`category_hierarchy.json`)

#### Category Hierarchy
- Level 1 = הכי טוב (CATEGORY 1 PLATINUM)
- Level 11 = הכי גרוע (CATEGORY 4)

#### Upgrade Rules
- מוסיף בלוקים מקטגוריות טובות יותר
- **חסימה**: Shortside (CAT3/CAT4) → Lateral (CAT2 LATERAL) = חסום

#### Block Exclusivity
- בלוקים Exclusive = רק מקור אחד יכול להשתמש
- בלוקים Shared = מספר מקורות

---

## 🤖 האם יש AI?

**לא!** זה **Rule-Based System** בלבד.

### מה זה אומר?
- ❌ אין Machine Learning
- ❌ אין Neural Networks
- ❌ אין "למידה" או "התאמה אוטומטית"
- ✅ רק כללים ברורים וקבועים
- ✅ רק לוגיקה מוגדרת מראש

### למה זה טוב?
- ✅ צפוי וברור
- ✅ ניתן לשליטה מלאה
- ✅ ניתן לדיבוג קל
- ✅ מהיר (אין חישובים כבדים)

### למה זה פחות טוב?
- ❌ לא "חושב" מעבר לכללים
- ❌ לא מתאים עצמו אוטומטית
- ❌ דורש עדכון ידני של כללים

---

## 💡 דרכים לשיפור - המלצות

### 1. הוספת Machine Learning (ML)

**מה זה יעשה:**
- למידה מניסיון עבר - אילו שיבוצים הצליחו?
- חיזוי הצלחת שיבוץ לפני ביצוע
- אופטימיזציה של סדר הזמנות

**איך לממש:**
```python
# דוגמה: Reinforcement Learning
# המערכת לומדת מהתוצאות ומשפרת עצמה
from sklearn.ensemble import RandomForestClassifier

# איסוף נתונים: הזמנה -> תוצאה (הצליח/נכשל)
# אימון מודל: חיזוי הצלחת שיבוץ
# שימוש: דירוג הזמנות לפי הסתברות הצלחה
```

**יתרונות:**
- ✅ לומד מהניסיון
- ✅ משפר עצמו אוטומטית
- ✅ יכול למצוא דפוסים שאנחנו לא רואים

**חסרונות:**
- ❌ מורכב ליישום
- ❌ דורש הרבה נתונים
- ❌ פחות ברור (black box)

### 2. אופטימיזציה מתמטית

**מה זה יעשה:**
- חישוב השילוב המיטבי של כל ההזמנות
- לא רק "הזמנה אחר הזמנה" אלא "כל ההזמנות יחד"
- מיקסום מספר שיבוצים מוצלחים

**איך לממש:**
```python
# דוגמה: Linear Programming / Constraint Satisfaction
from ortools.sat.python import cp_model

# משתני החלטה: איזה כרטיס לכל הזמנה
# אילוצים: כללים עסקיים
# מטרה: מקסימום שיבוצים מוצלחים
```

**יתרונות:**
- ✅ מיטבי (optimal) - לא רק "טוב"
- ✅ לוקח בחשבון את כל ההזמנות יחד

**חסרונות:**
- ❌ מורכב ליישום
- ❌ יכול להיות איטי עם הרבה הזמנות

### 3. שיפור הכללים הקיימים

#### 3.1 Dynamic Priority
**מה:** עדיפות דינמית לפי:
- זמן הזמנה (הזמנות ישנות יותר = עדיפות)
- ערך הזמנה (הזמנות יקרות יותר = עדיפות)
- מקור הזמנה (מקורות מסוימים = עדיפות)

```python
def calculate_dynamic_priority(order):
    base = get_category_level(order.category)
    age_bonus = (datetime.now() - order.created_at).days * 0.1
    value_bonus = order.price * 0.01
    return base - age_bonus - value_bonus
```

#### 3.2 Smart Block Selection
**מה:** לא רק "exclusive first", אלא:
- בלוקים עם הכי הרבה כרטיסים פנויים
- בלוקים שמתאימים למספר הזמנות
- בלוקים עם הכי פחות "בזבוז" (unused tickets)

```python
def calculate_block_score(block, orders):
    available = count_available_tickets(block)
    demand = sum(o.qty for o in orders if block_allowed(o, block))
    utilization = min(available, demand) / available if available > 0 else 0
    return utilization * available  # Prefer blocks with high utilization
```

#### 3.3 Predictive Matching
**מה:** חיזוי אילו הזמנות יגיעו בעתיד:
- אם יש הזמנות שכבר "בדרך" → שמור להם כרטיסים
- אם יש דפוסים (למשל: בימי שישי יש יותר הזמנות) → תכנן מראש

#### 3.4 Multi-Pass Optimization
**מה:** במקום run אחד:
- **Pass 1**: שיבוץ "קל" (SINGLE, PAIR ברור)
- **Pass 2**: שיבוץ "מורכב" (SCH, groups)
- **Pass 3**: Re-optimization (האם אפשר לשפר?)

### 4. שיפורים טכניים

#### 4.1 Caching
```python
# Cache תוצאות חישובים יקרים
@lru_cache(maxsize=1000)
def calculate_block_exclusivity(source, block):
    # חישוב יקר
    pass
```

#### 4.2 Parallel Processing
```python
# עיבוד מספר הזמנות במקביל
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=4) as executor:
    results = executor.map(process_order, orders)
```

#### 4.3 Better Data Structures
```python
# שימוש ב-Set/Dict במקום List לחיפוש מהיר
available_tickets_by_block = defaultdict(list)
for ticket in tickets:
    available_tickets_by_block[ticket.block].append(ticket)
```

### 5. שיפורים ב-UX/Business

#### 5.1 Feedback Loop
- איסוף נתונים על שיבוצים שלא הצליחו
- ניתוח למה נכשלו
- שיפור כללים בהתאם

#### 5.2 A/B Testing
- השוואה בין אסטרטגיות שיבוץ שונות
- מדידת הצלחה (מספר שיבוצים, שביעות רצון)
- בחירת האסטרטגיה הטובה ביותר

#### 5.3 Real-time Monitoring
- Dashboard עם מדדים בזמן אמת
- התראות על בעיות
- המלצות אוטומטיות לשיפור

---

## 🎯 המלצות עיקריות לשיפור

### קצר טווח (קל ליישום):
1. ✅ **Dynamic Priority** - עדיפות לפי זמן/ערך
2. ✅ **Better Logging** - לוגים מפורטים יותר לניתוח
3. ✅ **Statistics Dashboard** - מדדים על הצלחת שיבוץ

### בינוני טווח (בינוני ליישום):
1. ✅ **Multi-Pass Optimization** - מספר passes לשיפור
2. ✅ **Smart Block Selection** - בחירת בלוקים חכמה יותר
3. ✅ **Feedback Collection** - איסוף נתונים על כשלונות

### ארוך טווח (קשה ליישום):
1. ✅ **Machine Learning** - למידה מהניסיון
2. ✅ **Mathematical Optimization** - חישוב מיטבי
3. ✅ **Predictive Analytics** - חיזוי עתידי

---

## 📊 דוגמאות קונקרטיות לשיפור

### דוגמה 1: Priority לפי זמן
```python
# במקביל לקטגוריה, לקחת בחשבון זמן הזמנה
orders_sorted = sorted(orders, key=lambda o: (
    get_category_level(o.category),
    (datetime.now() - o.created_at).total_seconds()  # ישן יותר = עדיפות
))
```

### דוגמה 2: Smart SCH Usage
```python
# במקום "SCH רק אם אין PAIR", לבדוק:
# - כמה SCH יש?
# - כמה PAIR יש?
# - אם יש הרבה SCH וקצת PAIR → תשתמש ב-SCH כדי לשמור PAIR
if len(sch_candidates) > len(pair_candidates) * 2:
    # יש הרבה SCH → תשתמש בהם
    use_sch_first = True
```

### דוגמה 3: Lookahead
```python
# לא רק הזמנה הנוכחית, אלא גם הבאות
# אם יש הזמנה ל-4 כרטיסים אחר כך → אל תפרק קבוצת 4
if has_upcoming_order_for_4_tickets():
    protect_groups_of_size_4()
```

---

## 🏁 סיכום

### מה יש עכשיו:
- ✅ Rule-Based System יציב וצפוי
- ✅ כללים ברורים וניתנים לשליטה
- ✅ עובד טוב למקרים רגילים

### מה חסר:
- ❌ למידה מהניסיון
- ❌ אופטימיזציה גלובלית
- ❌ התאמה דינמית

### מה כדאי להוסיף:
1. **קצר טווח**: Dynamic Priority, Better Logging
2. **בינוני טווח**: Multi-Pass, Smart Selection
3. **ארוך טווח**: ML, Optimization

**המלצה:** התחל בשיפורים קצרי טווח, אסוף נתונים, ואז תחליט אם להוסיף ML.
