import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

# הגדרות עיצוב
st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

# הגדרת ה-AI (Gemini)
st.sidebar.title("הגדרות מערכת")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

# אתחול הזיכרון
if 'cart' not in st.session_state:
    st.session_state.cart = []
if 'inventory_df' not in st.session_state:
    st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מחולל הצעות מחיר חכם")

# חלוקה לטורים
col_inv, col_quote = st.columns([1, 1])

# --- צד ימין: המחסן (לפי המבנה ששלחת) ---
with col_inv:
    st.header("🏢 המחסן שלי")
    uploaded_inv = st.file_uploader("טען קובץ מלאי (Excel)", type=["xlsx"])
    
    if uploaded_inv:
        st.session_state.inventory_df = pd.read_excel(uploaded_inv)
        st.success(f"נטענו {len(st.session_state.inventory_df)} פריטים")

    if not st.session_state.inventory_df.empty:
        # יצירת רשימת חיפוש חכמה
        inv = st.session_state.inventory_df
        inv['search_str'] = inv['מק\"ט'].astype(str) + " | " + inv['תאור מוצר'].astype(str)
        
        selected = st.selectbox("חפש מוצר במלאי:", options=[""] + inv['search_str'].tolist())
        
        if selected:
            row = inv[inv['search_str'] == selected].iloc[0]
            st.info(f"מלאי זמין: {row['יתרה מחסני']} | מחיר קניה: {row['מחיר קניה']}")
            if st.button("➕ הוסף להצעה"):
                st.session_state.cart.append({
                    "מק\"ט": row['מק\"ט'],
                    "תיאור": row['תאור מוצר'],
                    "מחיר קניה": row['מחיר קניה'],
                    "מקור": "מלאי פנימי"
                })
                st.toast("נוסף!")

# --- צד שמאל: עיבוד מיילים מהספקים (AI) ---
with col_quote:
    st.header("📧 חילוץ מהיר ממייל ספק")
    email_raw = st.text_area("הדבק כאן את תוכן המייל (C-Data, CMS וכו'):", height=150)
    
    if st.button("🚀 עבד והוסף להצעה"):
        if not api_key:
            st.error("חובה להכניס API Key בתפריט הצד")
        else:
            prompt = f"""
            Extract products from this email. Return ONLY a JSON list of objects with:
            "sku", "description", "price" (number only).
            Text: {email_raw}
            """
            response = model.generate_content(prompt)
            try:
                # ניקוי הטקסט ל-JSON
                clean_txt = response.text.replace('```json', '').replace('```', '').strip()
                new_items = json.loads(clean_txt)
                for item in new_items:
                    st.session_state.cart.append({
                        "מק\"ט": item['sku'],
                        "תיאור": item['description'],
                        "מחיר קניה": item['price'],
                        "מקור": "ספק חיצוני"
                    })
                st.success("המוצרים חולצו ונוספו בהצלחה!")
            except:
                st.error("ה-AI לא הצליח לקרוא את המבנה. נסה שוב.")

# --- סיכום הצעת המחיר (למטה) ---
st.divider()
if st.session_state.cart:
    st.header("📄 הצעת המחיר הסופית")
    df_final = pd.DataFrame(st.session_state.cart)
    
    profit = st.slider("אחוז רווח (%)", 0, 10, 10)
    df_final['מחיר ללקוח'] = df_final['מחיר קניה'].apply(lambda x: round(float(x) * (1 + profit/100), 2))
    
    st.table(df_final[['מק\"ט', 'תיאור', 'מקור', 'מחיר ללקוח']])
    
    # ייצוא לאקסל
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False)
    
    st.download_button("📥 הורד אקסל למנהלי תיקים", data=output.getvalue(), file_name="Quote.xlsx")
    if st.button("🗑️ נקה הכל"):
        st.session_state.cart = []
        st.rerun()