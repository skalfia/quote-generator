import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import PyPDF2

st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

def load_and_map_df(file):
    try:
        df = pd.read_excel(file, engine='calamine')
        df.columns = [str(c).strip() for c in df.columns]
        
        # מיפוי עמודות לפי הצילום המדויק של קובי
        mapping = {
            'sku': 'מק"ט',
            'desc': 'תאור מוצר',
            'price': 'מחיר קניה מחשב $',
            'stock_main': 'יתרה מחסני',
            'stock_orders': 'הזמנות לקוח לאיסוף',
            'stock_purchase': 'כמות ברכש'
        }
        
        # בדיקה שכל העמודות קיימות
        for key, col in mapping.items():
            if col not in df.columns:
                st.error(f"חסרה עמודה בקובץ: {col}")
                return None

        # חישוב מלאי זמין: יתרה + רכש + הזמנות לקוח
        df['מלאי זמין'] = df[mapping['stock_main']].fillna(0) + \
                          df[mapping['stock_purchase']].fillna(0) + \
                          df[mapping['stock_orders']].fillna(0)
        
        df['search'] = df[mapping['sku']].astype(str) + " | " + df[mapping['desc']].astype(str)
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
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

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
        search = st.selectbox("🔍 חפש מוצר (מק"ט או תיאור):", [""] + inv['search'].tolist())
        if search:
            row = inv[inv['search'] == search].iloc[0]
            m = st.session_state.mapping
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("מחיר קניה", f"${row[m['price']]}")
            with col2:
                st.metric("מלאי זמין כולל", int(row['מלאי זמין']))
            
            if st.button("➕ הוסף להצעה"):
                st.session_state.cart.append({
                    "sku": row[m['sku']], 
                    "desc": row[m['desc']], 
                    "price": row[m['price']]
                })
                st.toast("המוצר נוסף לסל")

with tab2:
    pasted = st.text_area("הדבק טקסט מהמייל לניתוח:")
    if st.button("🚀 חלץ נתונים") and model and pasted:
        with st.spinner("AI מנתח..."):
            res = model.generate_content(f"Extract items as JSON list [{{'sku','desc','price'}}] from: {pasted}")
            try:
                items = json.loads(res.text.replace('```json', '').replace('```', '').strip())
                for i in items: st.session_state.cart.append(i)
                st.success("הנתונים חולצו!")
            except: st.error("שגיאה בפענוח ה-AI")

if st.session_state.cart:
    st.divider()
    st.header("📄 הצעה ללקוח")
    margin = st.slider("אחוז רווח (%)", 0, 50, 15)
    
    final_df = pd.DataFrame(st.session_state.cart)
    final_df['מחיר סופי'] = final_df['price'].apply(lambda x: round(float(x) * (1 + margin/100), 2))
    
    st.table(final_df[['sku', 'desc', 'מחיר סופי']])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        final_df[['sku', 'desc', 'מחיר סופי']].to_excel(writer, index=False)
    st.download_button("📥 הורד הצעת מחיר (Excel)", data=output.getvalue(), file_name="quote.xlsx")
    
    if st.button("🗑️ נקה הכל"):
        st.session_state.cart = []
        st.rerun()
