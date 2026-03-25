import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

# הגדרת דף
st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

# פונקציית עזר לניקוי שמות עמודות
def clean_col_name(name):
    return " ".join(str(name).split()).strip()

def load_and_map_df(file):
    try:
        # קריאה עם calamine ליציבות מקסימלית
        df = pd.read_excel(file, engine='calamine')
        # ניקוי אגרסיבי של כל שמות העמודות
        df.columns = [clean_col_name(c) for c in df.columns]
        
        mapping = {}
        for col in df.columns:
            if 'מק"ט' in col: mapping['sku'] = col
            if 'תאור מוצר' in col: mapping['desc'] = col
            if 'מחיר קניה מחשב' in col: mapping['price'] = col
            if 'יתרה מחסני' in col: mapping['stock_main'] = col
            if 'כמות ברכש' in col: mapping['stock_purchase'] = col
            if 'הזמנות לקוח לאיסוף' in col: mapping['stock_orders'] = col

        # בדיקה אם מצאנו את המינימום הנדרש
        if 'sku' not in mapping or 'price' not in mapping:
            st.error(f"⚠️ חסרות עמודות קריטיות באקסל. נמצאו: {list(df.columns)}")
            return None

        # המרת מלאי למספרים בצורה בטוחה
        for k in ['stock_main', 'stock_purchase', 'stock_orders']:
            if k in mapping:
                df[mapping[k]] = pd.to_numeric(df[mapping[k]], errors='coerce').fillna(0)

        # חישוב מלאי זמין
        df['מלאי זמין'] = df[mapping.get('stock_main', df.columns[0])].fillna(0) + \
                          df[mapping.get('stock_purchase', df.columns[0])].fillna(0) + \
                          df[mapping.get('stock_orders', df.columns[0])].fillna(0)
        
        df['search'] = df[mapping['sku']].astype(str) + " | " + df[mapping['desc']].astype(str)
        st.session_state.mapping = mapping
        return df
    except Exception as e:
        st.error(f"שגיאה בטעינה: {e}")
        return None

# סרגל צד - הגדרות וחיווי API
st.sidebar.title("🛠️ הגדרות מערכת")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")

model = None
if api_key:
    try:
        genai.configure(api_key=api_key)
        # בדיקה קטנה אם ה-API עובד
        model = genai.GenerativeModel('gemini-1.5-flash')
        st.sidebar.success("✅ מחובר ל-AI בהצלחה")
    except Exception as e:
        st.sidebar.error("❌ מפתח API לא תקין")

if 'cart' not in st.session_state: st.session_state.cart = []
if 'inventory_df' not in st.session_state: st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מערכת הצעות מחיר - קובי")

tab1, tab2 = st.tabs(["🏢 ניהול מלאי", "📧 חילוץ מהיר (AI)"])

with tab1:
    uploaded = st.file_uploader("טען קובץ אקסל (XLSX)", type=["xlsx"])
    if uploaded:
        df = load_and_map_df(uploaded)
        if df is not None:
            st.session_state.inventory_df = df
            st.success(f"הקטלוג נטען: {len(df)} פריטים נמצאו.")

    if not st.session_state.inventory_df.empty:
        inv = st.session_state.inventory_df
        search = st.selectbox("🔍 חפש מוצר במלאי:", [""] + inv['search'].tolist())
        
        if search:
            row = inv[inv['search'] == search].iloc[0]
            m = st.session_state.mapping
            
            col1, col2 = st.columns(2)
            with col1: st.metric("מחיר קניה", f"${row[m['price']]}")
            with col2: st.metric("מלאי זמין (כולל רכש)", int(row['מלאי זמין']))
            
            if st.button("➕ הוסף להצעת המחיר"):
                st.session_state.cart.append({
                    "sku": row[m['sku']], 
                    "desc": row[m['desc']], 
                    "price": row[m['price']]
                })
                st.toast("נוסף לסל!")

with tab2:
    pasted_text = st.text_area("הדבק טקסט מספק או ממייל:")
    if st.button("🚀 חלץ מוצרים עם AI"):
        if model and pasted_text:
            with st.spinner("מנתח..."):
                try:
                    prompt = f"Extract items as JSON list [{{'sku','desc','price'}}] from this text: {pasted_text}"
                    response = model.generate_content(prompt)
                    # ניקוי הטקסט מה-AI למקרה שהחזיר Markdown
                    clean_json = response.text.strip().replace('```json', '').replace('```', '')
                    items = json.loads(clean_json)
                    for i in items: st.session_state.cart.append(i)
                    st.success(f"חולצו {len(items)} פריטים מהטקסט!")
                except:
                    st.error("ה-AI לא הצליח לקרוא את הפורמט. נסה להדביק טקסט נקי יותר.")
        else:
            st.warning("נא להזין API Key ולצרף טקסט.")

# תצוגת סל והורדה
if st.session_state.cart:
    st.divider()
    st.subheader("📋 סיכום הצעה")
    margin = st.slider("מתח רווח מבוקש (%)", 0, 50, 15)
    
    final_df = pd.DataFrame(st.session_state.cart)
    final_df['מחיר בסיס'] = pd.to_numeric(final_df['price'], errors='coerce').fillna(0)
    final_df['מחיר ללקוח'] = final_df['מחיר בסיס'].apply(lambda x: round(x * (1 + margin/100), 2))
    
    st.table(final_df[['sku', 'desc', 'מחיר ללקוח']])
    
    c_out1, c_out2 = st.columns(2)
    with c_out1:
        if st.button("🗑️ נקה הכל"):
            st.session_state.cart = []
            st.rerun()
    with c_out2:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            final_df[['sku', 'desc', 'מחיר ללקוח']].to_excel(writer, index=False)
        st.download_button("📥 הורד אקסל מוכן ללקוח", data=output.getvalue(), file_name="quote.xlsx")
