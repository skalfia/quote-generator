import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import PyPDF2

st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

def extract_pdf_text(file):
    try:
        reader = PyPDF2.PdfReader(file)
        return " ".join([page.extract_text() for page in reader.pages])
    except: return ""

def load_and_map_df(file):
    try:
        # שימוש במנוע calamine להתעלמות מעיצובים בעייתים
        df = pd.read_excel(file, engine='calamine')
        # ניקוי יסודי של שמות העמודות מרווחים ותווים נסתרים
        df.columns = [str(c).strip() for c in df.columns]
        
        mapping = {}
        for col in df.columns:
            # זיהוי מק"ט - מחפש את המילה בתוך הכותרת
            if 'מק"ט' in col: mapping['sku'] = col
            # זיהוי תיאור
            if 'תאור מוצר' in col or 'תיאור' in col: mapping['desc'] = col
            # זיהוי מחיר - התאמה מדויקת למה שרואים בתמונה שלך
            if 'מחיר קניה' in col or 'מחיר מוצג לסוכן' in col:
                mapping['price'] = col
        
        # גיבוי: אם לא מצאנו, ננסה לפי מיקום עמודה (מק"ט בדר"כ בראשונות, מחיר בסוף)
        if 'sku' not in mapping: mapping['sku'] = df.columns[0]
        if 'price' not in mapping:
            # מחפש כל עמודה שמכילה את המילה מחיר
            price_cols = [c for c in df.columns if 'מחיר' in c]
            mapping['price'] = price_cols[0] if price_cols else df.columns[-1]

        desc_col = mapping.get('desc', mapping['sku'])
        df['search'] = df[mapping['sku']].astype(str) + " | " + df[desc_col].astype(str)
        st.session_state.mapping = mapping
        return df
    except Exception as e:
        st.error(f"שגיאה בקריאה: {e}")
        return None

# הגדרות AI - מותאם לגרסה היציבה
st.sidebar.title("🛠️ הגדרות")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")
model = None
if api_key:
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        st.sidebar.success("✅ מחובר")
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
                    st.success("הנתונים חולצו!")
                except: st.error("שגיאה בניתוח ה-AI")

if st.session_state.cart:
    st.divider()
    margin = st.slider("אחוז רווח (%)", 0, 40, 15)
    final_df = pd.DataFrame(st.session_state.cart)
    
    # פונקציה לניקוי והמרת מחיר למספר
    def clean_price(p):
        try: return float(str(p).replace('$','').replace(',','').strip())
        except: return 0.0

    final_df['cost'] = final_df['price'].apply(clean_price)
    final_df['מחיר ללקוח'] = final_df['cost'].apply(lambda x: round(x * (1 + margin/100), 2))
    
    st.table(final_df[['sku', 'desc', 'מחיר ללקוח']])
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🗑️ נקה הכל"):
            st.session_state.cart = []
            st.rerun()
    with c2:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            final_df[['sku', 'desc', 'מחיר ללקוח']].to_excel(writer, index=False)
        st.download_button("📥 הורד הצעה (Excel)", data=output.getvalue(), file_name="quote.xlsx")
