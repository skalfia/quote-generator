import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import PyPDF2

# הגדרות עמוד
st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

# פונקציה לקריאת PDF
def extract_pdf_text(file):
    try:
        reader = PyPDF2.PdfReader(file)
        return " ".join([page.extract_text() for page in reader.pages])
    except: return ""

# פונקציה לזיהוי עמודות חכם (מותאם בדיוק לקובץ שלך)
def load_and_map_df(file):
    try:
        # קריאה חסינה שמתעלמת מעיצובים
        df = pd.read_excel(file, engine='calamine')
        df.columns = [str(c).strip() for c in df.columns]
        
        mapping = {}
        for col in df.columns:
            c_low = col.lower()
            if 'מק"ט' in c_low or 'sku' in c_low: mapping['sku'] = col
            if any(x in c_low for x in ['תאור', 'תיאור', 'desc', 'שם מוצר']): mapping['desc'] = col
            if 'מחיר קניה' in c_low: mapping['price'] = col
            elif 'מחיר' in c_low and 'price' not in mapping: mapping['price'] = col
        
        # אם לא מצאנו, נחפש לפי האינדקסים שהיו בשגיאה שלך
        if 'sku' not in mapping: mapping['sku'] = df.columns[4] if len(df.columns) > 4 else df.columns[0]
        if 'price' not in mapping: mapping['price'] = df.columns[10] if len(df.columns) > 10 else df.columns[-1]
            
        desc_col = mapping.get('desc', mapping['sku'])
        df['search'] = df[mapping['sku']].astype(str) + " | " + df[desc_col].astype(str)
        st.session_state.mapping = mapping
        return df
    except Exception as e:
        st.error(f"שגיאה: {e}")
        return None

# הגדרות AI
st.sidebar.title("🛠️ הגדרות")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")
model = None
if api_key:
    try:
        genai.configure(api_key=api_key)
        # שימוש במודל יציב למניעת שגיאת 404
        model = genai.GenerativeModel('gemini-1.5-flash')
        st.sidebar.success("✅ מחובר")
    except: st.sidebar.error("מפתח לא תקין")

if 'cart' not in st.session_state: st.session_state.cart = []
if 'inventory_df' not in st.session_state: st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מערכת הצעות מחיר אוטומטית")

tab1, tab2 = st.tabs(["🏢 המחסן שלי", "📧 חילוץ מספק (AI)"])

with tab1:
    uploaded = st.file_uploader("טען אקסל מלאי", type=["xlsx"])
    if uploaded:
        df = load_and_map_df(uploaded)
        if df is not None:
            st.session_state.inventory_df = df
            st.success(f"נטענו {len(df)} פריטים")

    if not st.session_state.inventory_df.empty:
        inv = st.session_state.inventory_df
        search = st.selectbox("🔍 חפש מוצר:", [""] + inv['search'].tolist())
        if search:
            row = inv[inv['search'] == search].iloc[0]
            m = st.session_state.mapping
            cost = row[m['price']]
            st.info(f"מחיר קניה: ${cost}")
            if st.button("➕ הוסף מהמלאי"):
                st.session_state.cart.append({
                    "sku": row[m['sku']], "desc": row[m.get('desc', m['sku'])], 
                    "price": cost, "source": "מחסן"
                })

with tab2:
    c_f, c_t = st.columns(2)
    with c_f: sup_pdf = st.file_uploader("PDF מהספק", type=["pdf"])
    with c_t: pasted = st.text_area("או הדבק טקסט:")
    
    if st.button("🚀 נתח נתונים"):
        content = extract_pdf_text(sup_pdf) if sup_pdf else pasted
        if model and content:
            with st.spinner("מנתח..."):
                try:
                    prompt = f"Extract items as JSON list [{{'sku','desc','price'}}] from: {content}"
                    res = model.generate_content(prompt)
                    items = json.loads(res.text.replace('```json', '').replace('```', '').strip())
                    for i in items:
                        i['source'] = 'ספק'
                        st.session_state.cart.append(i)
                    st.success("חולץ בהצלחה")
                except: st.error("שגיאה בניתוח")

if st.session_state.cart:
    st.divider()
    margin = st.slider("רווח (%)", 0, 30, 10)
    final = pd.DataFrame(st.session_state.cart)
    # ניקוי מחירים והכפלה ברווח
    final['cost_num'] = final['price'].apply(lambda x: float(str(x).replace('$','').replace(',','')) if x else 0)
    final['מחיר ללקוח'] = final['cost_num'].apply(lambda x: round(x * (1 + margin/100), 2))
    st.dataframe(final[['sku', 'desc', 'source', 'מחיר ללקוח']], use_container_width=True)
    
    if st.button("🗑️ נקה הכל"):
        st.session_state.cart = []
        st.rerun()
