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
        
        df['מלאי זמין'] = df[mapping.get('stock_main', df.columns[0])].fillna(0) + \
                          df[mapping.get('stock_purchase', df.columns[0])].fillna(0) + \
                          df[mapping.get('stock_orders', df.columns[0])].fillna(0)
        
        df['search'] = df[mapping['sku']].astype(str) + " | " + df[mapping['desc']].astype(str)
        st.session_state.mapping = mapping
        return df
    except Exception as e:
        st.error(f"שגיאה: {e}")
        return None

# הגדרות API
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
            with c1: st.metric("מחיר סוכן (קניה)", f"${row[m['price']]}")
            with c2: st.metric("מלאי זמין", int(row['מלאי זמין']))
            with c3: qty = st.number_input("כמות להוספה:", min_value=1, value=1, key="inv_qty")
            
            if st.button("➕ הוסף להצעה"):
                st.session_state.cart.append({
                    "סטטוס": "מלאי" if row['מלאי זמין'] > 0 else "רכש",
                    "תאור מוצר": row[m['desc']],
                    "כמות": qty,
                    "מקט / CONFIG": row[m['sku']],
                    "מחיר לסוכן": float(str(row[m['price']]).replace('$','').replace(',',''))
                })
                st.toast("נוסף!")

with tab2:
    st.info("הדבק טקסט חופשי מהמייל (מקט, תיאור ומחיר). ה-AI יזהה את הנתונים באופן אוטומטי.")
    pasted = st.text_area("הדבק כאן את נתוני הספק:", height=200)
    if st.button("🚀 חלץ והוסף לסל") and model and pasted:
        with st.spinner("AI מנתח נתונים..."):
            try:
                # הנחיה מדויקת יותר ל-AI כדי שיבין את הפורמט שלך
                prompt = f"""
                You are a data extractor. Extract product information from the following text and return ONLY a valid JSON list.
                Each object must have: 'sku', 'desc', 'price' (as a number).
                If a price has a $ sign, remove it and return only the number.
                Text:
                {pasted}
                """
                res = model.generate_content(prompt)
                clean_json = res.text.strip().replace('```json', '').replace('```', '')
                items = json.loads(clean_json)
                for i in items:
                    st.session_state.cart.append({
                        "סטטוס": "רכש (ספק חיצוני)",
                        "תאור מוצר": i['desc'],
                        "כמות": 1,
                        "מקט / CONFIG": i['sku'],
                        "מחיר לסוכן": float(i['price'])
                    })
                st.success(f"חולצו {len(items)} פריטים!")
                st.rerun()
            except Exception as e:
                st.error("ה-AI לא הצליח לפענח את המבנה. נסה להדביק טקסט ברור יותר.")

if st.session_state.cart:
    st.divider()
    st.subheader("📋 עריכת הצעת מחיר סופית")
    
    # הוספת מדד האחוזים (הרווח)
    margin = st.sidebar.slider("מתח רווח להוספה (%)", 0, 50, 15)
    
    final_df = pd.DataFrame(st.session_state.cart)
    
    # חישוב מחיר סופי ללקוח (כולל הרווח)
    final_df['מחיר ללקוח'] = final_df['מחיר לסוכן'].apply(lambda x: round(float(x) * (1 + margin/100), 2))
    
    # תצוגה לפי הפורמט שביקשת
    display_cols = ["סטטוס", "תאור מוצר", "כמות", "מקט / CONFIG", "מחיר לסוכן", "מחיר ללקוח"]
    st.table(final_df[display_cols])
    
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🗑️ נקה הכל"):
            st.session_state.cart = []
            st.rerun()
    with col_b:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            final_df[display_cols].to_excel(writer, index=False)
        st.download_button("📥 הורד אקסל בפורמט סופי", data=output.getvalue(), file_name="Quote_Final.xlsx")
