import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import re

st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

# פונקציה לניקוי והמרת מחיר למספר (מטפלת ב-$ ופסיקים)
def parse_price(price_str):
    try:
        if isinstance(price_str, (int, float)): return float(price_str)
        return float(re.sub(r'[^\d.]', '', str(price_str)))
    except:
        return 0.0

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

# סרגל צד
st.sidebar.title("🛠️ הגדרות")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")
margin = st.sidebar.slider("מתח רווח להוספה (%)", 0, 50, 15)

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

tab1, tab2 = st.tabs(["🏢 המחסן שלי", "📧 חילוץ מהיר מספק (AI)"])

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
            with c1: st.metric("מחיר סוכן", f"${row[m['price']]}")
            with c2: st.metric("מלאי זמין", int(row['מלאי זמין']))
            with c3: qty = st.number_input("כמות:", min_value=1, value=1, key="inv_qty")
            
            if st.button("➕ הוסף להצעה"):
                st.session_state.cart.append({
                    "סטטוס": "מלאי" if row['מלאי זמין'] > 0 else "רכש",
                    "תאור מוצר": row[m['desc']],
                    "כמות": qty,
                    "מקט / CONFIG": row[m['sku']],
                    "מחיר לסוכן": parse_price(row[m['price']])
                })
                st.toast("נוסף!")

with tab2:
    pasted = st.text_area("הדבק כאן את נתוני הספק (מקט, תיאור ומחיר):", height=250)
    if st.button("🚀 חלץ מוצרים והוסף לסל") and model and pasted:
        with st.spinner("AI מנתח..."):
            try:
                prompt = f"Extract items as JSON list [{{'sku','desc','price'}}] from: {pasted}. Return ONLY JSON."
                res = model.generate_content(prompt)
                
                # ניקוי תיבת הקוד Markdown (כמו שראינו בתמונה שלך)
                raw_res = res.text.strip()
                clean_json = re.sub(r'```json\s*|```', '', raw_res)
                
                items = json.loads(clean_json)
                for i in items:
                    st.session_state.cart.append({
                        "סטטוס": "רכש (ספק)",
                        "תאור מוצר": i.get('desc', ''),
                        "כמות": 1,
                        "מקט / CONFIG": i.get('sku', ''),
                        "מחיר לסוכן": parse_price(i.get('price', 0))
                    })
                st.success(f"חולצו {len(items)} פריטים!")
                st.rerun()
            except Exception as e:
                st.error(f"לא הצלחתי לפענח את התשובה. שגיאה: {e}")

# הצגת ההצעה
if st.session_state.cart:
    st.divider()
    st.subheader("📋 הצעת מחיר סופית")
    
    final_df = pd.DataFrame(st.session_state.cart)
    # חישוב המחיר ללקוח בזמן אמת לפי האחוזים בסיידבר
    final_df['מחיר ללקוח'] = final_df['מחיר לסוכן'].apply(lambda x: round(float(x) * (1 + margin/100), 2))
    
    cols = ["סטטוס", "תאור מוצר", "כמות", "מקט / CONFIG", "מחיר לסוכן", "מחיר ללקוח"]
    st.table(final_df[cols])
    
    c_a, c_b = st.columns(2)
    with c_a:
        if st.button("🗑️ נקה הצעה"):
            st.session_state.cart = []
            st.rerun()
    with c_b:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            final_df[cols].to_excel(writer, index=False)
        st.download_button("📥 הורד אקסל מוכן", data=output.getvalue(), file_name="Customer_Quote.xlsx")
