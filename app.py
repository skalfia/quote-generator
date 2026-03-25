import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

# הגדרות עמוד
st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

# פונקציה חסינה לזיהוי עמודות וקריאת נתונים
def load_and_map_df(file):
    try:
        # קריאה חסינת עיצובים
        df = pd.read_excel(file, engine='calamine')
        df.columns = [str(c).strip() for c in df.columns]
        
        # מנגנון זיהוי עמודות אוטומטי לפי מילות מפתח
        mapping = {}
        for col in df.columns:
            c_low = col.lower()
            if 'מק"ט' in c_low or 'sku' in c_low: mapping['sku'] = col
            if 'תאור' in c_low or 'תיאור' in c_low or 'desc' in c_low: mapping['desc'] = col
            if 'קניה' in c_low or 'מחיר' in c_low or 'cost' in c_low: mapping['price'] = col
        
        # בדיקה שמצאנו את המינימום הנדרש
        if 'sku' not in mapping or 'price' not in mapping:
            st.error(f"לא הצלחתי לזהות עמודות מק\"ט או מחיר. עמודות בקובץ: {list(df.columns)}")
            return None
            
        # יצירת עמודת חיפוש אחידה
        desc_col = mapping.get('desc', mapping['sku'])
        df['search'] = df[mapping['sku']].astype(str) + " | " + df[desc_col].astype(str)
        
        # שמירת המיפוי לזיכרון
        st.session_state.mapping = mapping
        return df
    except Exception as e:
        st.error(f"שגיאה בקריאת הקובץ: {e}")
        return None

# הגדרות AI
st.sidebar.title("🛠️ הגדרות")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")
if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    st.sidebar.success("✅ מחובר")
else:
    model = None

if 'cart' not in st.session_state: st.session_state.cart = []
if 'inventory_df' not in st.session_state: st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מערכת הצעות מחיר אוטומטית")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🏢 המחסן שלי")
    uploaded = st.file_uploader("גרור אקסל מלאי (בלי לנקות עיצובים)", type=["xlsx"])
    if uploaded:
        df = load_and_map_df(uploaded)
        if df is not None:
            st.session_state.inventory_df = df
            st.success(f"נטענו {len(df)} פריטים!")

    if not st.session_state.inventory_df.empty:
        inv = st.session_state.inventory_df
        search = st.selectbox("🔍 חפש מוצר:", [""] + inv['search'].tolist())
        if search:
            row = inv[inv['search'] == search].iloc[0]
            m = st.session_state.mapping
            st.info(f"מחיר קניה: ${row[m['price']]}")
            if st.button("➕ הוסף להצעה"):
                st.session_state.cart.append({
                    "sku": row[m['sku']], 
                    "desc": row[m.get('desc', m['sku'])], 
                    "price": row[m['price']]
                })
                st.toast("נוסף!")

with col2:
    st.subheader("📧 חילוץ מהצעה")
    pasted = st.text_area("הדבק טקסט מהמייל:")
    if st.button("🚀 נתח עם AI"):
        if model and pasted:
            with st.spinner("מנתח..."):
                try:
                    res = model.generate_content(f"Return JSON list: [{{'sku','desc','price'}}] from: {pasted}")
                    items = json.loads(res.text.replace('```json', '').replace('```', '').strip())
                    for i in items: st.session_state.cart.append(i)
                    st.success("חולץ בהצלחה!")
                except: st.error("שגיאה בניתוח ה-AI")

# הצגה וייצוא
if st.session_state.cart:
    st.divider()
    margin = st.slider("אחוז רווח (%)", 0, 30, 10)
    final = pd.DataFrame(st.session_state.cart)
    final['מחיר ללקוח'] = final['price'].apply(lambda x: round(float(str(x).replace('$','')) * (1+margin/100), 2))
    st.dataframe(final, use_container_width=True)
    
    if st.button("🗑️ נקה הכל"):
        st.session_state.cart = []
        st.rerun()
