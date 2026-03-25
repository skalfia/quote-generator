import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

# הגדרות עמוד
st.set_page_config(page_title="ניהול הצעות מחיר - קובי", layout="wide")

# פונקציה חסינה לקריאת אקסל - מתעלמת מעיצובים לחלוטין
def load_inventory_bulletproof(file):
    try:
        # שימוש במנוע calamine שמתעלם מסטייל ועיצובים שגורמים לקריסה
        df = pd.read_excel(file, engine='calamine')
        # ניקוי רווחים משמות העמודות
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        # ניסיון אחרון עם מנוע בסיסי אם הראשון נכשל
        try:
            df = pd.read_excel(file, engine='openpyxl', data_only=True)
            return df
        except:
            st.error(f"שגיאה קריטית בקריאת הקובץ: {e}")
            return None

# הגדרות AI - שימוש במודל יציב
st.sidebar.title("🛠️ הגדרות מערכת")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")

model = None
if api_key:
    try:
        genai.configure(api_key=api_key)
        # שימוש בגרסה היציבה ביותר למניעת שגיאות 404
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
    except Exception as e:
        st.sidebar.error(f"שגיאה בחיבור: {e}")

# ניהול זיכרון (Session State)
if 'cart' not in st.session_state: st.session_state.cart = []
if 'inventory_df' not in st.session_state: st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מערכת הצעות מחיר אוטומטית")

# בדיקת חיבור ירוקה
if api_key and model:
    st.sidebar.success("✅ המערכת מוכנה לעבודה")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🏢 המחסן שלי (המלאי היומי)")
    uploaded_inv = st.file_uploader("גרור את קובץ האקסל כמו שהוא (בלי לנקות עיצובים)", type=["xlsx"])
    
    if uploaded_inv:
        df = load_inventory_bulletproof(uploaded_inv)
        if df is not None:
            st.session_state.inventory_df = df
            st.success(f"נטענו {len(df)} פריטים בהצלחה!")

    if not st.session_state.inventory_df.empty:
        inv = st.session_state.inventory_df
        # זיהוי עמודות
        col_sku = 'מק"ט'
        col_desc = 'תאור מוצר'
        col_price = 'מחיר קניה'
        
        inv['search'] = inv[col_sku].astype(str) + " | " + inv[col_desc].astype(str)
        search = st.selectbox("🔍 חפש מוצר במלאי:", [""] + inv['search'].tolist())
        
        if search:
            row = inv[inv['search'] == search].iloc[0]
            with st.container(border=True):
                st.write(f"**{row[col_desc]}**")
                st.markdown(f"### מחיר קניה: ${row[col_price]}")
                if st.button("➕ הוסף להצעה"):
                    st.session_state.cart.append({
                        "sku": row[col_sku], 
                        "desc": row[col_desc], 
                        "price": row[col_price],
                        "source": "מחסן"
                    })
                    st.toast("נוסף!")

with col2:
    st.subheader("📧 חילוץ מהצעה/מייל")
    pasted = st.text_area("הדבק כאן את תוכן המייל מהספק:", height=200)
    
    if st.button("🚀 נתח והוסף אוטומטית"):
        if not model:
            st.error("נא להזין מפתח API")
        elif not pasted:
            st.warning("התיבה ריקה")
        else:
            with st.spinner("ה-AI מחלץ נתונים..."):
                try:
                    prompt = f"Extract products as a JSON list with 'sku', 'desc', 'price' (numbers only). Text: {pasted}"
                    res = model.generate_content(prompt)
                    clean_res = res.text.replace('```json', '').replace('```', '').strip()
                    items = json.loads(clean_res)
                    for item in items:
                        st.session_state.cart.append({
                            "sku": item.get('sku', 'N/A'),
                            "desc": item.get('desc', 'N/A'),
                            "price": item.get('price', 0),
                            "source": "ספק"
                        })
                    st.success("הפריטים חולצו והתווספו!")
                except:
                    st.error("ה-AI לא הצליח לקרוא את הפורמט. נסה להדביק שוב.")

# --- תצוגה וניהול רווח ---
if st.session_state.cart:
    st.divider()
    st.header("📄 הצעת המחיר שלך")
    margin = st.slider("אחוז רווח מבוקש (%)", 0, 30, 10)
    
    final_df = pd.DataFrame(st.session_state.cart)
    final_df['מחיר ללקוח'] = final_df['price'].apply(lambda x: round(float(str(x).replace('$','')) * (1 + margin/100), 2))
    
    st.dataframe(final_df[['sku', 'desc', 'source', 'מחיר ללקוח']], use_container_width=True)
    
    if st.button("🗑️ נקה הכל"):
        st.session_state.cart = []
        st.rerun()
