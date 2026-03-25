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

# פונקציה חסינה לזיהוי עמודות וקריאת נתונים
def load_and_map_df(file):
    try:
        # קריאה חסינת עיצובים עם calamine
        df = pd.read_excel(file, engine='calamine')
        df.columns = [str(c).strip() for c in df.columns]
        
        mapping = {}
        for col in df.columns:
            c_low = col.lower()
            # זיהוי מק"ט
            if 'מק"ט' in c_low or 'sku' in c_low: mapping['sku'] = col
            # זיהוי תיאור
            if any(x in c_low for x in ['תאור', 'תיאור', 'desc', 'שם מוצר']): mapping['desc'] = col
            # זיהוי מחיר (תעדוף למחיר קניה)
            if 'מחיר קניה' in c_low: mapping['price'] = col
            elif 'מחיר' in c_low and 'price' not in mapping: mapping['price'] = col
        
        if 'sku' not in mapping or 'price' not in mapping:
            st.error(f"חסרה עמודת מק\"ט או מחיר. מצאתי: {list(mapping.keys())}")
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
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        st.sidebar.success("✅ מחובר")
    except: st.sidebar.error("מפתח לא תקין")

if 'cart' not in st.session_state: st.session_state.cart = []
if 'inventory_df' not in st.session_state: st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מערכת הצעות מחיר אוטומטית")

tab1, tab2 = st.tabs(["🏢 המחסן שלי", "📧 חילוץ מספק (AI)"])

# --- טאב 1: המחסן ---
with tab1:
    uploaded = st.file_uploader("טען אקסל מלאי מעודכן", type=["xlsx"])
    if uploaded:
        df = load_and_map_df(uploaded)
        if df is not None:
            st.session_state.inventory_df = df
            st.success(f"נטענו {len(df)} פריטים")

    if not st.session_state.inventory_df.empty:
        inv = st.session_state.inventory_df
        search = st.selectbox("🔍 חפש מוצר במלאי:", [""] + inv['search'].tolist())
        if search:
            row = inv[inv['search'] == search].iloc[0]
            m = st.session_state.mapping
            st.info(f"מחיר קניה במחסן: ${row[m['price']]}")
            if st.button("➕ הוסף מהמחסן"):
                st.session_state.cart.append({
                    "sku": row[m['sku']], "desc": row[m.get('desc', m['sku'])], 
                    "price": row[m['price']], "source": "מחסן"
                })
                st.toast("נוסף!")

# --- טאב 2: ספקים ---
with tab2:
    col_f, col_t = st.columns(2)
    with col_f:
        supplier_pdf = st.file_uploader("גרור קובץ PDF מהספק", type=["pdf"])
    with col_t:
        pasted_text = st.text_area("או הדבק טקסט מהמייל:")
    
    if st.button("🚀 נתח נתונים והוסף"):
        content = ""
        if supplier_pdf: content = extract_pdf_text(supplier_pdf)
        elif pasted_text: content = pasted_text
        
        if model and content:
            with st.spinner("AI מנתח..."):
                try:
                    prompt = f"Extract items as JSON list: [{{'sku','desc','price'}}] from this text: {content}"
                    res = model.generate_content(prompt)
                    items = json.loads(res.text.replace('```json', '').replace('```', '').strip())
                    for i in items:
                        i['source'] = 'ספק'
                        st.session_state.cart.append(i)
                    st.success(f"חולצו {len(items)} פריטים")
                except: st.error("שגיאה בניתוח הנתונים")
        else: st.warning("נא להזין מפתח API ותוכן")

# --- תצוגה סופית ---
if st.session_state.cart:
    st.divider()
    st.header("📄 הצעת המחיר המתגבשת")
    margin = st.slider("אחוז רווח (%)", 0, 30, 10)
    
    final = pd.DataFrame(st.session_state.cart)
    # ניקוי מחיר מסימנים כמו $
    final['cost'] = final['price'].apply(lambda x: float(str(x).replace('$','').replace(',','')) if x else 0)
    final['מחיר ללקוח'] = final['cost'].apply(lambda x: round(x * (1 + margin/100), 2))
    
    st.dataframe(final[['sku', 'desc', 'source', 'מחיר ללקוח']], use_container_width=True)
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🗑️ נקה הכל"):
            st.session_state.cart = []
            st.rerun()
    with c2:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            final[['sku', 'desc', 'מחיר ללקוח']].to_excel(writer, index=False)
        st.download_button("📥 הורד אקסל מוכן", data=output.getvalue(), file_name="Customer_Quote.xlsx")
