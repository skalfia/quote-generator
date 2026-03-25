import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

def load_and_map_df(file):
    try:
        df = pd.read_excel(file, engine='calamine')
        df.columns = [str(c).strip() for c in df.columns]
        
        # מיפוי לפי שמות העמודות המדויקים שראינו בצילום המסך
        mapping = {
            'sku': 'מק"ט',
            'desc': 'תאור מוצר',
            'price': 'מחיר קניה מחשב $',
            'stock_main': 'יתרה מחסני',
            'stock_orders': 'הזמנות לקוח לאיסוף',
            'stock_purchase': 'כמות ברכש'
        }
        
        # חישוב מלאי זמין לפי הנוסחה של קובי
        df['מלאי זמין'] = df[mapping['stock_main']].fillna(0) + \
                          df[mapping['stock_purchase']].fillna(0) + \
                          df[mapping['stock_orders']].fillna(0)
        
        # יצירת עמודת חיפוש
        df['search'] = df[mapping['sku']].astype(str) + " | " + df[mapping['desc']].astype(str)
        st.session_state.mapping = mapping
        return df
    except Exception as e:
        st.error(f"שגיאה בקריאת הקובץ: {e}")
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
        # תיקון השגיאה מהצילום: שימוש במרכאות בודדות בחוץ כדי לא לשבור את הטקסט
        search = st.selectbox('🔍 חפש מוצר (מק"ט או תיאור):', [""] + inv['search'].tolist())
        if search:
            row = inv[inv['search'] == search].iloc[0]
            m = st.session_state.mapping
            
            c1, c2 = st.columns(2)
            with c1:
                st.metric("מחיר קניה מחשב", f"${row[m['price']]}")
            with c2:
                st.metric("מלאי זמין (כולל רכש והזמנות)", int(row['מלאי זמין']))
            
            if st.button("➕ הוסף להצעה"):
                st.session_state.cart.append({
                    "sku": row[m['sku']], 
                    "desc": row[m['desc']], 
                    "price": row[m['price']]
                })
                st.toast("המוצר נוסף!")

with tab2:
    pasted = st.text_area("הדבק טקסט מהמייל כאן:")
    if st.button("🚀 חלץ נתונים") and model and pasted:
        with st.spinner("AI מנתח..."):
            try:
                res = model.generate_content(f"Return JSON list [{{'sku','desc','price'}}] from: {pasted}")
                items = json.loads(res.text.replace('```json', '').replace('```', '').strip())
                for i in items: st.session_state.cart.append(i)
                st.success("הנתונים חולצו בהצלחה")
            except: st.error("שגיאה בניתוח הטקסט")

if st.session_state.cart:
    st.divider()
    margin = st.slider("אחוז רווח (%)", 0, 50, 15)
    final_df = pd.DataFrame(st.session_state.cart)
    final_df['מחיר סופי'] = final_df['price'].apply(lambda x: round(float(x) * (1 + margin/100), 2))
    
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
        st.download_button("📥 הורד קובץ ללקוח", data=output.getvalue(), file_name="Customer_Quote.xlsx")
