# PRD: FinOps Context Truncation Mechanism

## תיאור המנגנון (Description)
מנגנון זה מגביל את גודל חלון ההקשר (Context Window) של הסוכנים כדי למנוע התפוצצות עלויות (Token limit explosion) במהלך דיבייט ארוך. 

## פלט/קלט (Inputs/Outputs)
- **קלט:** היסטוריית הדיבייט המלאה (Ledger).
- **פלט:** היסטוריה חתוכה הכוללת רק את ה-`LEDGER_WINDOW` (ברירת מחדל: 3) טענות אחרונות, בתוספת עוגן ה-V1 המוגן.

## אילוצים וחלופות (Constraints & Alternatives)
- נשקלה חלופה של סיכום דינמי של ההיסטוריה (Context Summarizer) אך היא נפסלה עקב עלות API נוספת וסיכון להזיות (Hallucinations) שיפגעו בדיוק הדיבייט.
- **אילוץ קשיח:** עוגן ה-V1 (הטענה הראשונה) לעולם לא ייחתך, כדי שהשופט יוכל למדוד סטייה סמנטית.

## קריטריוני הצלחה (Success Criteria)
- עלות הטוקנים לכל תור נשארת חסומה ב- $O(LEDGER\_WINDOW \times avg\_claim\_length)$, גם בדיבייט של 100 תורות.
