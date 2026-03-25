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

# פונקציה לזיהוי עמודות (מעודכן לפי הקובץ שלך)
def load_and_map_df(file):
    try:
        df = pd.read_excel(file, engine='calamine')
        df.columns = [str(c).strip() for c in df.columns]
        
        mapping = {}
        for col in df.columns:
            c_low = col.lower()
            if 'מק"ט' in c_low or 'sku' in c_low: mapping['sku'] = col
            if any(x in c_low for x in ['תאור', 'תיאור', 'desc', 'מוצר']): mapping['desc'] = col
            # תיקון ספציפי לעמודה שלך
            if 'מחיר מוצג לסוכן' in col or 'מחיר קניה' in col: mapping['price'] = col
            elif 'מחיר' in c_low and 'price' not in mapping: mapping['price'] = col
            
        if 'sku' not in mapping or 'price' not in mapping:
            st.error(f"לא זיהיתי עמודת מחיר. נמצאו: {list(df.columns)}")
            return None
            
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
        model = genai.GenerativeModel('gemini-1.5-flash')
        st.sidebar.success("✅ AI מחובר")
    except: st.sidebar.error("מפתח לא תקין")

if 'cart' not in st.session_state: st.session_state.cart = []
if 'inventory_df' not in st.session_state: st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מערכת הצעות מחיר - קובי")

tab1, tab2 = st.tabs(["🏢 המלאי שלי", "📧 חילוץ מספק (AI)"])

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
            st.info(f"מחיר קניה: {cost}")
            if st.button("➕ הוסף להצעה"):
                st.session_state.cart.append({
                    "sku": row[m['sku']], 
                    "desc": row[m.get('desc', m['sku'])], 
                    "price": cost
                })
                st.toast("נוסף!")

with tab2:
    col_a, col_b = st.columns(2)
    with col_a: sup_pdf = st.file_uploader("טען PDF מהספק", type=["pdf"])
    with col_b: pasted = st.text_area("או הדבק טקסט מהמייל:")
    
    if st.button("🚀 חלץ נתונים"):
        content = extract_pdf_text(sup_pdf) if sup_pdf else pasted
        if model and content:
            with st.spinner("AI מנתח..."):
                try:
                    res = model.generate_content(f"Return JSON list [{{'sku','desc','price'}}] from: {content}")
                    items = json.loads(res.text.replace('```json', '').replace('```', '').strip())
                    for i in items: st.session_state.cart.append(i)
                    st.success("הנתונים חולצו בהצלחה!")
                except: st.error("ה-AI לא הצליח לעבד את הטקסט")

if st.session_state.cart:
    st.divider()
    st.header("📄 הצעה ללקוח")
    margin = st.slider("אחוז רווח (%)", 0, 40, 15)
    
    final_df = pd.DataFrame(st.session_state.cart)
    # ניקוי המרת מחיר למספר
    final_df['cost'] = final_df['price'].apply(lambda x: float(str(x).replace('$','').replace(',','')) if x else 0)
    final_df['מחיר ללקוח'] = final_df['cost'].apply(lambda x: round(x * (1 + margin/100), 2))
    
    st.table(final_df[['sku', 'desc', 'מחיר ללקוח']])
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ נקה הצעה"):
            st.session_state.cart = []
            st.rerun()
    with col2:
        # ייצוא לאקסל
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            final_df[['sku', 'desc', 'מחיר ללקוח']].to_excel(writer, index=False)
        st.download_button("📥 הורד הצעה (Excel)", data=output.getvalue(), file_name="quote.xlsx")
