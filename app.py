import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

def clean_col(name):
    return " ".join(str(name).split()).strip()

def load_and_map_df(file):
    try:
        df = pd.read_excel(file, engine='calamine')
        df.columns = [clean_col(c) for c in df.columns]
        mapping = {}
        for col in df.columns:
            if 'מק' in col or 'sku' in col.lower(): mapping['sku'] = col
            if 'תאור מוצר' in col or 'תיאור' in col: mapping['desc'] = col
            if 'מחיר מוצג לסוכן' in col or 'מחיר קניה מחשב' in col: mapping['price'] = col
            if 'יתרה מחסני' in col: mapping['stock_main'] = col
            if 'כמות ברכש' in col: mapping['stock_purchase'] = col
            if 'הזמנות לקוח לאיסוף' in col: mapping['stock_orders'] = col
        
        # חישוב מלאי זמין
        df['מלאי זמין'] = df[mapping.get('stock_main', df.columns[0])].fillna(0) + \
                          df[mapping.get('stock_purchase', df.columns[0])].fillna(0) + \
                          df[mapping.get('stock_orders', df.columns[0])].fillna(0)
        
        df['search'] = df[mapping['sku']].astype(str) + " | " + df[mapping['desc']].astype(str)
        st.session_state.mapping = mapping
        return df
    except Exception as e:
        st.error(f"שגיאה: {e}")
        return None

# הגדרות API וחיווי
st.sidebar.title("🛠️ הגדרות")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")
model = None
if api_key:
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        st.sidebar.success("✅ API מחובר")
    except: st.sidebar.error("❌ מפתח לא תקין")

if 'cart' not in st.session_state: st.session_state.cart = []
if 'inventory_df' not in st.session_state: st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מערכת הצעות מחיר - קובי")

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
        search = st.selectbox('🔍 חפש מוצר:', [""] + inv['search'].tolist())
        if search:
            row = inv[inv['search'] == search].iloc[0]
            m = st.session_state.mapping
            
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("מחיר קניה", f"${row[m['price']]}")
            with c2: st.metric("מלאי זמין", int(row['מלאי זמין']))
            with c3: qty = st.number_input("כמות:", min_value=1, value=1)
            
            if st.button("➕ הוסף להצעה"):
                st.session_state.cart.append({
                    "סטטוס": "מלאי" if row['מלאי זמין'] > 0 else "רכש",
                    "תאור מוצר": row[m['desc']],
                    "כמות": qty,
                    "מקט / CONFIG": row[m['sku']],
                    "מחיר לסוכן": row[m['price']]
                })
                st.toast("נוסף!")

with tab2:
    pasted = st.text_area("הדבק טקסט מהמייל:")
    if st.button("🚀 חלץ והוסף") and model and pasted:
        with st.spinner("AI מנתח..."):
            try:
                prompt = f"Extract items as JSON [{{'sku','desc','price'}}] from: {pasted}"
                res = model.generate_content(prompt)
                items = json.loads(res.text.strip().replace('```json', '').replace('```', ''))
                for i in items:
                    st.session_state.cart.append({
                        "סטטוס": "רכש / ספק",
                        "תאור מוצר": i['desc'],
                        "כמות": 1,
                        "מקט / CONFIG": i['sku'],
                        "מחיר לסוכן": i['price']
                    })
                st.success("הנתונים חולצו!")
            except: st.error("שגיאה בניתוח")

# תצוגה לפי הפורמט שביקשת
if st.session_state.cart:
    st.divider()
    st.subheader("📋 הצעת מחיר סופית")
    
    final_df = pd.DataFrame(st.session_state.cart)
    
    # הצגת הטבלה בפורמט המבוקש
    st.table(final_df[["סטטוס", "תאור מוצר", "כמות", "מקט / CONFIG", "מחיר לסוכן"]])
    
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🗑️ נקה הצעה"):
            st.session_state.cart = []
            st.rerun()
    with col_b:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            final_df.to_excel(writer, index=False)
        st.download_button("📥 הורד אקסל בפורמט המבוקש", data=output.getvalue(), file_name="Customer_Quote.xlsx")
