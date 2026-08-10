# סיכום מלא — מחקר ועריכת נכסי התמונות של GCRTS

**תאריך מצב:** 9 באוגוסט 2026  
**משחק:** Twilight Syndrome, מזהה `SLPS00102`  
**סביבת הרצה:** PCSX-Redux  
**מטרת העבודה:** להבין כיצד התמונות ומרכיבי הממשק נטענים ומוצגים, לאפשר חילוץ ועריכה שלהם, להזריק גרסה ערוכה באופן הפיך, ולחבר את הנכסים המוצגים בזמן אמת ל־Asset Inspector.

## תקציר מנהלים

הוכח מסלול עריכה הפיך ומלא עבור תמונת הרקע של התפריט הראשי. התמונה חולצה מקובץ המשחק, פוענחה לחמישה חלקי TIM, הורכבה ל־PNG בגודל 320×240, נערכה, קודדה מחדש לגודל המדויק של המקור והוזרקה זמנית דרך PCSX-Redux. גם ריבוע לבן וגם הכיתוב `TRANSLATED WITH GCRTS` נשארו חלק קבוע מהתמונה לאחר Hard Reset.

בנוסף זוהו 32 נכסי תפריט נפרדים, ובהם START, SETTINGS/PREPARE וכותרת Photos. START ו־SETTINGS נערכו, קודדו והוצגו במשחק בהצלחה.

נבנתה מערכת Asset Inspector להצגה, חילוץ, החלפת PNG, עריכת פיקסלים/פלטה, בדיקת תקציב גודל ובניית פלט. נבנה גם Visual Inspector שמזהה נכסים חיים באמצעות RAM, VRAM ופקודות GPU. הזיהוי אינו תלוי עוד בתבנית של צילום מסך. מעבר בין התפריט הראשי לדף Photos יוצר ומזהה דפי runtime לפי הרכב הנכסים שנקראו ונמשכו בפועל.

## 1. מה נמצא בקבצי המשחק

### רקע הכיתה

- מקור בדיסק: `DAT/SINKOU/PROGDAT.BIN;1`
- עותק עבודה: `sdb_main_menu_asset/PROGDAT.BIN`
- גודל הקובץ: 69,663 בתים
- התמונה מורכבת מבלוקים 0–4.
- כל בלוק הוא רצועה אנכית בגודל 64×240.
- חמש הרצועות מתחברות לתמונה אחת בגודל 320×240.
- הפורמט המפוענח הוא PlayStation TIM סטנדרטי, 8bpp indexed.
- לכל רצועה CLUT של 256 צבעי BGR555/STP.

קבוצות נוספות ב־PROGDAT:

- בלוקים 5–9: שכבה/גרסת כיתה נוספת; התפקיד המדויק עדיין לא הוכח במלואו.
- בלוקים 10–14: רקע שולחן התמונות/ה־Spoils, גם הוא חמש רצועות היוצרות 320×240.

### ספרייטים וכיתובי תפריט

- מקור בדיסק: `DAT/SINKOU/MENUDAT.BIN;1`
- עותק עבודה: `sdb_main_menu_asset/MENUDAT.BIN`
- מכיל 32 זרמי TIM דחוסים נפרדים.
- רובם נכסי טקסט קטנים בפורמט TIM 4bpp indexed עם פלטה של 16 צבעים.
- בלוק 7: START, בגודל 100×24.
- בלוק 8: PREPARE/SETTINGS, בגודל 100×24.
- בלוק 9: Photos, בגודל 64×32.

המסקנה החשובה: הנכס שנבחר למחקר התפריט הראשי אינו SDB2/MS ואינו רשומת CDB נפרדת. הוא אוסף זרמים דחוסים שתוצאתם קובצי TIM. לכן שדות כמו frame count, delta frames או SDB tile graph אינם חלים על תמונה זו.

## 2. פורמט הדחיסה והקידוד מחדש

אושר codec המשחק הבא:

- `00..7F`: רצף literal.
- `80..BF`: חזרה על אותו byte.
- `C0..DF`: LZ back-reference.
- `E0..EF`: רצף arithmetic/delta.
- `FF`: סוף הזרם.

התגלה שב־PROGDAT לא מספיק שקובץ ערוך יהיה קטן מהמקור. גבולות הבלוקים קבועים בפועל. ניסוי שבו בלוק 0 התקצר הזיז את בלוק 1 וגרם לשאר התמונה להפוך ללבנה/פגומה.

לכן נבנה encoder דטרמיניסטי עם הרחבה שקולה: אם הזרם החדש קטן מדי, ניתן להחליף tokens דחוסים בייצוג literal שקול, בלי לשנות את הפלט המפוענח, עד להשגת הגודל המקורי המדויק.

## 3. ניסויי העריכה שהצליחו

### ריבוע לבן

- נערך אזור בגודל 20×20 ברצועה הראשונה.
- הפיקסלים הוחלפו באינדקס פלטה קיים ובהיר.
- קובץ הפלט נשאר בגודל המקורי המדויק.
- לאחר הזרקה ו־Hard Reset הריבוע נשאר חלק מהרקע לאורך זמן.

הניסוי הפריד בין שני סוגי הזרקה:

- כתיבה ישירה ל־framebuffer הופיעה לפריים אחד ונמחקה כשהמשחק צייר מחדש.
- עריכת TIM בתוך PROGDAT הופיעה בכל ציור מחדש ולכן הייתה חלק אמיתי מהנכס.

### `TRANSLATED WITH GCRTS`

- הטקסט נכתב בחלק העליון של התמונה.
- העריכה חצתה גבולות בין כמה רצועות TIM.
- כל חמש הרצועות קודדו בחזרה לגודליהן המקוריים.
- התוצאה שרדה Hard Reset ונשארה יציבה במשחק.
- קובץ: `sdb_main_menu_asset/PROGDAT_translated_with_gcrts_exact.BIN`.
- תצוגה מקדימה: `sdb_main_menu_asset/PROGDAT_translated_with_gcrts_320x240.png`.

### START ו־SETTINGS

- MENUDAT בלוקים 7 ו־8 פוענחו ונערכו.
- הטקסטים האנגליים נבנו תוך שמירת פורמט ה־TIM ותקציב הגודל.
- שניהם נבדקו חזותית ב־PCSX-Redux.
- מצב הבחירה במשחק ממשיך לשנות את צבע הכיתוב, משום שהעריכה השתמשה באינדקסים קיימים בפלטה.

## 4. מה נבנה בתוכנה

### Asset Inspector

הכלי מסוגל:

- לפתוח את MENUDAT ואת PROGDAT.
- להציג thumbnail ופרטי כל בלוק.
- להציג מקור, offset, גודל דחוס, גודל מפוענח, ממדים ופורמט פיקסלים.
- להציג ולערוך CLUT.
- לייצא PNG.
- להחליף PNG תוך שמירה על מגבלות הפורמט והפלטה.
- לבצע pixel edit ו־palette edit.
- להציג תקציב encoded מול allocation.
- לבנות קובץ פלט בלי לדרוס את המקור.
- לבדוק זמנית ב־PCSX-Redux ולשחזר את המקור.
- לטפל ברקע מורכב של 320×240 כחמישה strips שהם נכס לוגי אחד.

### Visual Inspector

הכלי מציג צילום חי של המשחק ועליו אובייקטים ניתנים לבחירה. בחירה בנכס יכולה לפתוח ישירות את ה־Asset Inspector הנכון ואת הבלוק הנכון.

בתחילת הדרך היו rectangles ידניים לפי screenshots. הם נשמרו כראיות וכ־fallback בלבד. המנגנון הראשי כיום הוא runtime-driven:

1. קריאת RAM ו־VRAM מ־PCSX-Redux דרך Web API.
2. אימות byte-for-byte שהקוד הטעון הוא פרופיל `PROG.EXE` הידוע.
3. קריאת ארבעת שורשי ה־Ordering Table שהוכחו.
4. פירוש חבילות GPU מסוג textured polygon.
5. התאמת UV/TPAGE לאזור VRAM.
6. התאמה מדויקת בין שורות ה־TIM המקודדות לבין תוכן ה־VRAM.
7. הפקת Asset ID ומלבן המסך שבו הוא נמשך.

אם פרופיל הקוד אינו תואם, המערכת מחזירה אפס נכסים חיים. היא אינה משתמשת בכתובות ישנות או בניחוש.

### מודל מצב runtime

נבנו המצבים:

`UNKNOWN → LOADED → DECOMPRESSED → UPLOADED_TO_VRAM → DRAWN_THIS_FRAME`

המודל כולל זהות קנונית, מופע runtime, ראיות, VRAM overwrite וירידה ממצב DRAWN כאשר הנכס כבר אינו נמשך. החיבור המלא לשלב LOADED/DECOMPRESSED עדיין חסר transport בטוח, אבל שלב VRAM/GPU/DRAWN עובד בפועל.

### דפי runtime

דף אינו screenshot שמור. הוא הרכב יציב של Asset IDs פעילים.

- `runtime.page.1`: `main_menu.start`, `main_menu.prepare`, `progdat.group0`.
- `runtime.page.2`: `category.photos`, `progdat.group2`.

המעבר ל־Photos יצר את page 2. החזרה לתפריט הראשי זיהתה מחדש את page 1 ולא יצרה duplicate. המידע ומספר התצפיות נשמרים ב־`runtime_pages.json`.

### בחירה משותפת בין הכלים

בחירה בנכס נשמרת ב־`project_selection.json`. כך Asset Inspector ו־Visual Inspector יכולים להתייחס לאותו Asset ID גם כאשר הם תהליכים נפרדים. כרטיסים בדף Assets יכולים לקבל סימון `[DRAWN]` כאשר הנכס מזוהה בזמן אמת.

## 5. ממצאי PCSX-Redux ו־VRAM

### Web API שנבדק

- קריאת RAM מלאה.
- קריאת VRAM מלאה.
- כתיבה חלקית ל־VRAM לצורכי ניסוי.
- temporary CD patch לקובץ PROGDAT או MENUDAT.
- מסלול clear ל־temporary patches.

לא נבנה מחדש BIN/CUE פיזי, ולא שונה image הדיסק המקורי.

### רקע הכיתה

התמונה הסופית הופיעה בשני framebuffers, בקירוב:

- `(0,0)–(319,239)`
- `(0,256)–(319,495)`

### הוכחת Photos block 9

- MENUDAT block 9 נמצא בהתאמה מדויקת ב־VRAM word coordinates `(640,96)`.
- גודל texture: 16 VRAM words × 32 שורות, כלומר 64×32 בפורמט 4bpp.
- אותרו חבילות `POLY_GT4` בשני buffers בכתובות `0x80075D6C` ו־`0x80077020`.
- TPAGE: 10.
- UV: `(0,96,64,32)`.
- גבולות על המסך: `(40,24,64,32)`.
- בדף Photos הוא מסווג `DRAWN_THIS_FRAME`.
- לאחר חזרה לתפריט הוא עדיין resident ב־VRAM, אבל אין primitive פעיל שמפנה אליו; לכן אינו מוצג כנכס נמשך.

### שורשי GPU/Ordering Table

מניתוח קוד חי נמצא ש־GPU DMA מופעל סביב `0x80049670`, וש־`$a0` הוא שורש ה־Ordering Table שנכתב קודם ב־`0x80049650`. ארבעת השורשים המאומתים הם:

- `0x80076A24`
- `0x80076A64`
- `0x80075770`
- `0x800757B0`

השימוש בהם מותנה בהתאמה מדויקת של קוד `0x80049630` מול `PROG.EXE`.

## 6. ניסויים שלא עבדו ומה למדנו

### כתיבה ל־framebuffer

השינוי הופיע לפריים ונעלם. זו הוכחה שהמשחק מצייר את הנכס מחדש ושיש לערוך את המקור או את texture staging, לא את הפלט הסופי.

### Lua WebServer

בגרסת Lua של PCSX-Redux השדה `WebServer` היה `nil`; לכן endpoint מותאם אישית מתוך Lua לא היה זמין בדרך שנוסתה.

### Lua breakpoints ו־GPU callbacks

נוסו callbacks על כתיבת GPU DMA וגם execution breakpoint. בחלק מהמקרים נאספו כתובות מועילות, אבל האמולטור נסגר לאחר זמן. גם קריאת I/O מתוך callback הייתה בלתי בטוחה.

החלטה סופית:

- אין להשתמש ב־persistent Lua breakpoints ב־workflow הרגיל.
- `gcrts_runtime_probe.lua` נשאר stub מושבת בלבד.
- המנגנון הפעיל קורא snapshots מבחוץ ואינו מזריק hooks לקוד המשחק.

המעבר הזה הוא הסיבה שהמערכת הנוכחית יציבה יותר ואינה תלויה ב־Lua Console.

## 7. בטיחות ושחזור

- קובצי המקור נשמרים ללא שינוי בתיקיית המקור.
- הפלט נבנה לקובץ נפרד.
- לפני injection נבדקים hash, מבנה וגודל.
- PROGDAT דורש exact consumed size לכל stream.
- ההזרקה ל־PCSX-Redux היא זמנית ואינה rebuild של הדיסק.
- ניתן לנקות temporary CD patches ואז לבצע Hard Reset.
- כתובות runtime מתקבלות רק לאחר אימות הפרופיל הפעיל.

## 8. מה הוכח ומה עדיין פתוח

### הוכח

- זיהוי מדויק של PROGDAT ו־MENUDAT.
- פענוח TIM 4bpp, 8bpp ו־16bpp הרלוונטיים.
- חילוץ ל־PNG והרכבת תמונות מרצועות.
- עריכת פיקסלים, טקסט ופלטה.
- re-encode דטרמיניסטי ושמירת exact size.
- temporary runtime/disc-file injection הפיך.
- עריכות יציבות לאחר Hard Reset.
- התאמת TIM ל־VRAM ול־GPU primitive.
- קבלת bounds אמיתיים על המסך.
- הבחנה בין resident ב־VRAM לבין drawn כעת.
- זיהוי דפים לפי הרכב נכסים בזמן אמת.
- מעבר ישיר מנכס חזותי ל־Asset Inspector.

### עדיין פתוח

- מקור הקריאה המדויק ברמת CPU עבור כל archive load.
- compressed source pointer ו־decompressed destination pointer בזמן טעינה.
- גודל decompressed שנלכד חי מתוך פונקציית הפענוח.
- call chain מלא מה־archive loader עד upload ל־VRAM.
- transport tracing יציב שאינו משתמש ב־Lua breakpoints.
- תמיכה מלאה וכללית ב־SDB2/MS, לרבות frames ו־deltas.
- persistent reinsertion ל־BIN/CUE ובדיקה על חומרה אמיתית.
- זיהוי אוטומטי של סוגי תוכן נוספים כגון סרטים ואודיו.

אסור לדווח על הנקודות האלה כאילו הושלמו. מסלול התמונה של התפריט הוכח ברמת קובץ, codec, TIM, עריכה, injection, VRAM ו־GPU; קטע ה־CPU loader/decompress runtime נשאר שלב המחקר הבא.

## 9. בדיקות ומצב נוכחי

- בדיקת regression מלאה אחרונה: **348 passed, 6 warnings, 0 failures**.
- שני דפי runtime שמורים ונבדקו במעבר הלוך וחזור.
- Visual Inspector ו־Asset Inspector משתמשים באותו קטלוג נכסים ובאותה בחירה משותפת.
- מנגנון Lua המסוכן אינו חלק מהמסלול הפעיל.

## 10. קבצים מרכזיים להמשך עבודה

- `gcrts/asset_inspector_ui.py` — ממשק Asset Inspector.
- `gcrts/visual_inspector_ui.py` — Visual Inspector ומעקב חי.
- `gcrts/runtime_visual_provider.py` — איסוף RAM/VRAM, OT והתאמת נכסים.
- `gcrts/vram_asset_detector.py` — התאמת TIM מדויקת ל־VRAM.
- `gcrts/psx_ordering_table.py` — parser לחבילות GPU.
- `gcrts/gpu_asset_correlation.py` — חיבור primitive לנכס VRAM.
- `gcrts/runtime_pages.py` — גילוי ושמירת דפים לפי composition.
- `runtime_pages.json` — דפי runtime שהתגלו.
- `project_selection.json` — הבחירה המשותפת בין הכלים.
- `IMAGE_ASSET_STATUS.md` — פירוט טכני של נכסי התמונה והעריכות.
- `SDB_MAIN_MENU_ASSET_REPORT.md` — יומן הניסוי הממוקד של רקע התפריט.
- `CURRENT_SYSTEM_STATUS.md` — מצב המערכת הרחב.
- `RUNTIME_ASSET_TRACKER.md` — ארכיטקטורת המעקב החי.
- `RUNTIME_PAGE_DISCOVERY.md` — מודל דפי runtime.

## מסקנה

הפרויקט עבר ממיפוי ידני של rectangles בתצלומים למערכת שמסוגלת לזהות נכסי תמונה שנמשכים בפועל, לקשר אותם למקור בדיסק ולפתוח אותם לעריכה. עבור התפריט הראשי ודף Photos כבר קיימת שרשרת עובדת של חילוץ, פענוח, עריכה, קידוד, הזרקה, זיהוי VRAM/GPU ובחירה דרך ה־Inspector. השלב הבא הוא להשלים את החלק המוקדם של השרשרת — archive read ו־decompression pointers — באמצעות מנגנון tracing יציב שאינו מסכן את PCSX-Redux.
