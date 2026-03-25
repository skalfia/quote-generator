import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

def load_and_map_df(file):
    try:
        # שימוש במנוע calamine למהירות ויציבות
        df = pd.read_excel(file, engine='calamine')
        # ניקוי רווחים כפולים וסימנים נסתרים משמות העמודות
        df.columns = [" ".join(str(c).split()) for c in df.columns]
        
        mapping = {}
        for col in df.columns:
            if 'מק"ט' in col: mapping['sku'] = col
            if 'תאור מוצר' in col: mapping['desc'] = col
            if 'מחיר קניה מחשב' in col: mapping['price'] = col
            if 'יתרה מחסני' in col: mapping['stock_main'] = col
            if 'כמות ברכש' in col: mapping['stock_purchase'] = col
            if 'הזמנות לקוח לאיסוף' in col: mapping['stock_orders'] = col

        # בדיקה שמצאנו את עמודות החובה (מק"ט ומחיר)
        if 'sku' not in mapping or 'price' not in mapping:
            st.error(f"לא זיהיתי עמודות קריטיות. נמצאו: {list(df.columns)}")
            return None

        # המרת עמודות מלאי למספרים בצורה בטוחה
        for key in ['stock_main', 'stock_purchase', 'stock_orders']:
            if key in mapping:
                df[mapping[key]] = pd.to_numeric(df[mapping[key]], errors='coerce').fillna(0)

        # חישוב מלאי זמין (יתרה + רכש + הזמנות לקוח)
        df['מלאי זמין'] = df[mapping.get('stock_main', 0)].fillna(0) + \
                          df[mapping.get('stock_purchase', 0)].fillna(0) + \
                          df[mapping.get('stock_orders', 0)].fillna(0)
        
        # יצירת עמודת חיפוש משולבת
        df['search'] = df[mapping['sku']].astype(str) + " | " + df[mapping['desc']].astype(str)
        st.session_state.mapping = mapping
        return df
    except Exception as e:
        st.error(f"שגיאה בטעינת האקסל: {e}")
        return None

# הגדרות AI
st.sidebar.title("🛠️ הגדרות")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")
model = None
if api_key:
    genai.configure(api_key=api_key)
    # שימוש במודל יציב
    model = genai.GenerativeModel('gemini-1.5-flash')

if 'cart' not in st.session_state: st.session_state.cart = []
if 'inventory_df' not in st.session_state: st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מערכת הצעות מחיר - קובי")

tab1, tab2 = st.tabs(["🏢 המלאי שלי", "📧 חילוץ מספק (AI)"])

with tab1:
    uploaded = st.file_uploader("טען אקסל מלאי מעודכן", type=["xlsx"])
    if uploaded:
        df = load_and_map_df(uploaded)
        if df is not None:
            st.session_state.inventory_df = df
            st.success(f"נטענו {len(df)} פריטים בהצלחה!")

    if not st.session_state.inventory_df.empty:
        inv = st.session_state.inventory_df
        # שימוש במרכאות בודדות בחוץ כדי למנוע את השגיאה מהצילום הקודם
        search = st.selectbox('🔍 חפש מוצר (מק"ט או תיאור):', [""] + inv['search'].tolist())
        
        if search:
            row = inv[inv['search'] == search].iloc[0]
            m = st.session_state.mapping
            
            c1, c2 = st.columns(2)
            with c1:
                st.metric("מחיר קניה", f"${row[m['price']]}")
            with c2:
                st.metric("מלאי זמין כולל", int(row['מלאי זמין']))
            
            if st.button("➕ הוסף להצעה"):
                st.session_state.cart.append({
                    "sku": row[m['sku']], 
                    "desc": row[m['desc']], 
                    "price": row[m['price']]
                })
                st.toast("הפריט נוסף לסל")

with tab2:
    pasted = st.text_area("הדבק טקסט מהמייל לניתוח:")
    if st.button("🚀 חלץ נתונים") and model and pasted:
        with st.spinner("AI מנתח את הנתונים..."):
            try:
                prompt = f"Extract items as a clean JSON list with keys 'sku', 'desc', 'price'. Text: {pasted}"
                res = model.generate_content(prompt)
                items = json.loads(res.text.replace('```json', '').replace('```', '').strip())
                for i in items: st.session_state.cart.append(i)
                st.success(f"חולצו {len(items)} פריטים!")
            except: st.error("שגיאה בניתוח ה-AI. וודא שהטקסט ברור.")

# תצוגת ההצעה הסופית
if st.session_state.cart:
    st.divider()
    st.header("📋 הצעה ללקוח")
    margin = st.slider("אחוז רווח מבוקש (%)", 0, 100, 15)
    
    final_df = pd.DataFrame(st.session_state.cart)
    # המרת מחיר למספר לחישוב
    final_df['cost'] = pd.to_numeric(final_df['price'], errors='coerce').fillna(0)
    final_df['מחיר סופי'] = final_df['cost'].apply(lambda x: round(x * (1 + margin/100), 2))
    
    st.table(final_df[['sku', 'desc', 'מחיר סופי']])
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ נקה הכל"):
            st.session_state.cart = []
            st.rerun()
    with col2:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            final_df[['sku', 'desc', 'מחיר סופי']].to_excel(writer, index=False)
        st.download_button("📥 הורד אקסל ללקוח", data=output.getvalue(), file_name="Customer_Quote.xlsx")
