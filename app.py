import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import re

st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

# פונקציית עזר לניקוי מחיר מטקסט (הופכת "855$" ל-855.0)
def parse_price(price_str):
    try:
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

# מדד אחוזים בסרגל הצד
st.sidebar.divider()
margin = st.sidebar.slider("מתח רווח להוספה (%)", 0, 50, 15)

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
        search = st.selectbox('🔍 חפש מוצר במלאי:', [""] + inv['search'].tolist())
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
    st.info("הדבק את הטקסט מהמייל. ה-AI יזהה מקט, תיאור ומחיר גם אם הם בשורות נפרדות.")
    pasted = st.text_area("הדבק כאן את נתוני הספק:", height=250)
    if st.button("🚀 חלץ מוצרים והוסף לסל") and model and pasted:
        with st.spinner("AI מנתח נתונים..."):
            try:
                # הנחיה קשיחה לפורמט JSON בלבד
                prompt = f"""
                Extract all products from this text. 
                Return ONLY a JSON list of objects. No intro text, no conversational filler.
                Each object MUST have:
                "sku": the part number or config name
                "desc": the full product description
                "price": the numeric price (remove $ and commas)
                
                Text to analyze:
                {pasted}
                """
                res = model.generate_content(prompt)
                # ניקוי שאריות Markdown אם קיימות
                raw_text = res.text.strip()
                clean_json = re.sub(r'```json\s*|```', '', raw_text)
                
                items = json.loads(clean_json)
                for i in items:
                    st.session_state.cart.append({
                        "סטטוס": "רכש (ספק)",
                        "תאור מוצר": i.get('desc', 'ללא תיאור'),
                        "כמות": 1,
                        "מקט / CONFIG": i.get('sku', 'ללא מק"ט'),
                        "מחיר לסוכן": parse_price(i.get('price', 0))
                    })
                st.success(f"חולצו {len(items)} פריטים!")
                st.rerun()
            except Exception as e:
                st.error(f"ה-AI לא הצליח לחלץ נתונים. וודא שהטקסט כולל מחיר ומק\"ט. שגיאה: {e}")

if st.session_state.cart:
    st.divider()
    st.subheader("📋 סיכום הצעת מחיר")
    
    final_df = pd.DataFrame(st.session_state.cart)
    
    # חישוב מחיר סופי לפי המדד בסרגל הצד
    final_df['מחיר ללקוח'] = final_df['מחיר לסוכן'].apply(lambda x: round(float(x) * (1 + margin/100), 2))
    
    # עמודות להצגה ולהורדה
    cols = ["סטטוס", "תאור מוצר", "כמות", "מקט / CONFIG", "מחיר לסוכן", "מחיר ללקוח"]
    st.table(final_df[cols])
    
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🗑️ נקה הכל"):
            st.session_state.cart = []
            st.rerun()
    with col_b:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            final_df[cols].to_excel(writer, index=False)
        st.download_button("📥 הורד אקסל סופי", data=output.getvalue(), file_name="Customer_Quote.xlsx")
