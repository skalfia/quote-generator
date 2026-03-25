import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

st.set_page_config(page_title="ניהול מלאי והצעות מחיר - קובי", layout="wide")

def load_and_map_df(file):
    try:
        # קריאה עם calamine להתעלמות מעיצובים
        df = pd.read_excel(file, engine='calamine')
        # ניקוי בסיסי משמות העמודות
        df.columns = [str(c).strip() for c in df.columns]
        
        mapping = {}
        # מיפוי גמיש שנועל את העמודות שלך לפי מילות מפתח
        for col in df.columns:
            # זיהוי מק"ט (כולל גרש)
            if 'מק' in col or 'sku' in col.lower(): mapping['sku'] = col
            # זיהוי תיאור
            if 'תאור מוצר' in col or 'תיאור' in col or 'desc' in col.lower(): mapping['desc'] = col
            # זיהוי מחיר (כולל סימן דולר)
            if 'מחיר מוצג לסוכן' in col: mapping['price'] = col
        
        # גיבוי: אם לא מצאנו את הרוב, ננסה לפי האינדקסים שהיו ב-image_d0a1b2.png
        if len(mapping) < 2:
            st.warning("⚠️ לא הצלחתי לזהות עמודות באופן אוטומטי. מנסה לפי מיקומים קבועים.")
            # וודא שהאינדקסים האלו תואמים את האקסל שבתמונה הראשונה
            mapping['sku'] = df.columns[0]   # משפחה
            mapping['desc'] = df.columns[1]  # תאור משפחה
            # מחיר לכלכלה מופיע בדר"כ בסוף
            price_cols = [c for c in df.columns if 'מחיר' in c]
            mapping['price'] = price_cols[0] if price_cols else df.columns[-1]

        df['search'] = df[mapping['sku']].astype(str) + " | " + df[mapping['desc']].astype(str)
        st.session_state.mapping = mapping
        return df
    except Exception as e:
        st.error(f"שגיאה בקריאת האקסל: {e}")
        return None

# הגדרות AI
st.sidebar.title("🛠️ הגדרות")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")
model = None
if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    st.sidebar.success("✅ מחובר")

if 'cart' not in st.session_state: st.session_state.cart = []
if 'inventory_df' not in st.session_state: st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מערכת הצעות מחיר חכמה")

tab1, tab2 = st.tabs(["🏢 המחסן שלי", "📧 חילוץ מספק (AI)"])

with tab1:
    uploaded = st.file_uploader("טען אקסל מלאי מעודכן", type=["xlsx"])
    if uploaded:
        df = load_and_map_df(uploaded)
        if df is not None:
            st.session_state.inventory_df = df
            st.success("המלאי נטען!")

    if not st.session_state.inventory_df.empty:
        inv = st.session_state.inventory_df
        search = st.selectbox("🔍 חפש מוצר (מק\"ט או תיאור):", [""] + inv['search'].tolist())
        
        if search:
            row = inv[inv['search'] == search].iloc[0]
            m = st.session_state.mapping
            st.info(f"מחיר בסיס: ${row[m['price']]}")
            if st.button("➕ הוסף להצעה"):
                st.session_state.cart.append({
                    "sku": row[m['sku']], 
                    "desc": row[m['desc']], 
                    "price": row[m['price']]
                })
                st.toast("נוסף!")

with tab2:
    pasted = st.text_area("הדבק טקסט לניתוח:")
    if st.button("🚀 נתח והוסף"):
        if model and pasted:
            with st.spinner("AI מנתח..."):
                res = model.generate_content(f"Extract items as JSON list [{{'sku','desc','price'}}] from: {pasted}")
                try:
                    items = json.loads(res.text.replace('```json', '').replace('```', '').strip())
                    for i in items: st.session_state.cart.append(i)
                    st.success("חולץ והתווסף!")
                except: st.error("שגיאה בניתוח ה-AI")

# תצוגה
if st.session_state.cart:
    st.divider()
    margin = st.slider("אחוז רווח (%)", 0, 30, 10)
    final = pd.DataFrame(st.session_state.cart)
    final['מחיר סופי'] = final['price'].apply(lambda x: round(float(str(x).replace('$','')) * (1+margin/100), 2))
    st.table(final[['sku', 'desc', 'מחיר סופי']])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        final[['sku', 'desc', 'מחיר סופי']].to_excel(writer, index=False)
    st.download_button("📥 הורד אקסל מוכן", data=output.getvalue(), file_name="Quote.xlsx")
    
    if st.button("🗑️ נקה הכל"):
        st.session_state.cart = []
        st.rerun()
