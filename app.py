import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

def load_and_map_df(file):
    try:
        df = pd.read_excel(file, engine='calamine')
        # ניקוי אגרסיבי של שמות העמודות מרווחים כפולים וסימנים נסתרים
        df.columns = [" ".join(str(c).split()) for c in df.columns]
        
        mapping = {}
        for col in df.columns:
            if 'מק"ט' in col: mapping['sku'] = col
            if 'תאור מוצר' in col: mapping['desc'] = col
            if 'מחיר קניה מחשב' in col: mapping['price'] = col
            if 'יתרה מחסני' in col: mapping['stock_main'] = col
            if 'כמות ברכש' in col: mapping['stock_purchase'] = col
            if 'הזמנות לקוח לאיסוף' in col: mapping['stock_orders'] = col

        # וידוא עמודות חובה
        if 'sku' not in mapping or 'price' not in mapping:
            st.error(f"לא זיהיתי עמודות קריטיות. נמצאו: {list(df.columns)}")
            return None

        # המרת עמודות מלאי למספרים (למקרה שיש טקסט)
        for key in ['stock_main', 'stock_purchase', 'stock_orders']:
            if key in mapping:
                df[mapping[key]] = pd.to_numeric(df[mapping[key]], errors='coerce').fillna(0)

        # חישוב מלאי זמין לפי הנוסחה של קובי
        df['מלאי זמין'] = df[mapping.get('stock_main')].fillna(0) + \
                          df[mapping.get('stock_purchase')].fillna(0) + \
                          df[mapping.get('stock_orders')].fillna(0)
        
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
            st.success(f"נטענו {len(df)} פריטים בהצלחה!")

    if not st.session_state.inventory_df.empty:
        inv = st.session_state.inventory_df
        search = st.selectbox('🔍 חפש מוצר (מק"ט או תיאור):', [""] + inv['search'].tolist())
        if search:
            row = inv[inv['search'] == search].iloc[0]
            m = st.session_state.mapping
            
            c1, c2 = st.columns(2)
            with c1:
                price_val = row[m['price']]
                st.metric("מחיר קניה (באקסל)", f"${price_val}")
            with c2:
                st.metric("מלאי זמין כולל", int(row['מלאי זמין']))
            
            if st.button("➕ הוסף להצעה"):
                st.session_state.cart.append({
                    "sku": row[m['sku']], 
                    "desc": row[m['desc']], 
                    "price": row[m['price']]
                })
                st.toast("הפריט נוסף!")

with tab2:
    pasted = st.text_area("הדבק טקסט מהמייל:")
    if st.button("🚀 חלץ נתונים") and model and pasted:
        with st.spinner("AI מנתח..."):
            try:
                res = model.generate_content(f"Return JSON list [{{'sku','desc','price'}}] from: {pasted}")
                items = json.loads(res.text.replace('```json', '').replace('```', '').strip())
                for i in items: st.session_state.cart.append(i)
                st.success(f"חולצו {len(items)} פריטים!")
            except: st.error("שגיאה בניתוח הטקסט")

if st.session_state.cart:
    st.divider()
    st.header("📋 הצעה סופית")
    margin = st.slider("אחוז רווח (%)", 0, 50, 15)
    
    final_df = pd.DataFrame(st.session_state.cart)
    # המרת מחיר למספר לחישוב הרווח
    final_df['cost'] = pd.to_numeric(final_df['price'], errors='coerce').fillna(0)
    final_df['מחיר סופי ללקוח'] = final_df['cost'].apply(lambda x: round(x * (1 + margin/100), 2))
    
    st.table(final_df[['sku', 'desc', 'מחיר סופי ללקוח']])
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ נקה הצעה"):
            st.session_state.cart = []
            st.rerun()
    with col2:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            final_df[['sku', 'desc', 'מחיר סופי ללקוח']].to_excel(writer, index=False)
        st.download_button("📥 הורד אקסל ללקוח", data=output.getvalue(), file_name="quote_for_customer.xlsx")
