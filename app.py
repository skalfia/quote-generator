import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import re

# ניסיון לייבא PyPDF2 - אם לא קיים, האפליקציה לא תקרוס
try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

# פונקציה לחילוץ JSON חסינה
def extract_json(text):
    try:
        match = re.search(r'\[\s*{.*}\s*\]', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        clean_text = re.sub(r'```json\s*|```', '', text).strip()
        return json.loads(clean_text)
    except:
        return None

def parse_price(price_str):
    try:
        if isinstance(price_str, (int, float)): return float(price_str)
        return float(re.sub(r'[^\d.]', '', str(price_str)))
    except:
        return 0.0

# סרגל צד
st.sidebar.title("🛠️ הגדרות")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")
margin = st.sidebar.slider("מתח רווח להוספה (%)", 0, 100, 15)

model = None
if api_key:
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        st.sidebar.success("✅ AI מחובר")
    except:
        st.sidebar.error("❌ שגיאה בחיבור ל-API")

if 'cart' not in st.session_state: st.session_state.cart = []
if 'inventory_df' not in st.session_state: st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מערכת הצעות מחיר - קובי")

tab1, tab2, tab3 = st.tabs(["🏢 המחסן שלי", "📧 חילוץ מטקסט/מייל", "📄 חילוץ מקבצים"])

# --- לשונית 1: מלאי ---
with tab1:
    uploaded_inv = st.file_uploader("טען אקסל מלאי", type=["xlsx"])
    if uploaded_inv:
        try:
            df = pd.read_excel(uploaded_inv, engine='calamine')
            df.columns = [" ".join(str(c).split()).strip() for c in df.columns]
            st.session_state.inventory_df = df
            st.success("המלאי נטען בהצלחה!")
        except Exception as e:
            st.error(f"שגיאה בטעינת האקסל: {e}")

    if not st.session_state.inventory_df.empty:
        inv = st.session_state.inventory_df
        # חיפוש לפי מק"ט ותיאור (עמודות 0 ו-1)
        search_list = [f"{str(r[0])} | {str(r[1])}" for r in inv.values]
        search = st.selectbox("🔍 חפש מוצר:", [""] + search_list)
        if search:
            sku_val = search.split(" | ")[0]
            row = inv[inv.iloc[:, 0].astype(str) == sku_val].iloc[0]
            
            c1, c2 = st.columns(2)
            with c1: st.info(f"תיאור: {row[1]}")
            with c2: qty = st.number_input("כמות:", min_value=1, value=1)
            
            if st.button("➕ הוסף להצעה"):
                st.session_state.cart.append({
                    "סטטוס": "מלאי",
                    "תאור מוצר": row[1],
                    "כמות": qty,
                    "מקט / CONFIG": row[0],
                    "מחיר לסוכן": parse_price(row[-1]) # מחיר מעמודה אחרונה
                })
                st.toast("נוסף!")

# --- לשונית 2: טקסט חופשי ---
with tab2:
    pasted = st.text_area("הדבק כאן טקסט מהמייל:", height=250)
    if st.button("🚀 חלץ עם AI") and model:
        with st.spinner("מנתח..."):
            res = model.generate_content(f"Extract as JSON list [{{'sku','desc','price'}}] from: {pasted}")
            data = extract_json(res.text)
            if data:
                for i in data:
                    st.session_state.cart.append({
                        "סטטוס": "רכש (ספק)", "תאור מוצר": i.get('desc',''),
                        "כמות": 1, "מקט / CONFIG": i.get('sku',''), "מחיר לסוכן": parse_price(i.get('price',0))
                    })
                st.success("הנתונים התווספו!")
                st.rerun()

# --- לשונית 3: קבצים ---
with tab3:
    if not PDF_SUPPORT:
        st.warning("שים לב: תמיכת PDF דורשת עדכון קובץ requirements.txt ב-GitHub.")
    
    uploaded_file = st.file_uploader("טען קובץ ספק (PDF או Excel)", type=["pdf", "xlsx"])
    if uploaded_file and st.button("🔍 סרוק קובץ"):
        content = ""
        if uploaded_file.type == "application/pdf" and PDF_SUPPORT:
            reader = PyPDF2.PdfReader(uploaded_file)
            for page in reader.pages: content += page.extract_text()
        elif "excel" in uploaded_file.type:
            df_file = pd.read_excel(uploaded_file)
            content = df_file.to_string()
        
        if content and model:
            with st.spinner("מחלץ נתונים מהקובץ..."):
                res = model.generate_content(f"Extract products as JSON from: {content}")
                data = extract_json(res.text)
                if data:
                    for i in data:
                        st.session_state.cart.append({
                            "סטטוס": "רכש", "תאור מוצר": i.get('desc',''),
                            "כמות": 1, "מקט / CONFIG": i.get('sku',''), "מחיר לסוכן": parse_price(i.get('price',0))
                        })
                    st.success("בוצע!")

# --- הצגת התוצאה ---
if st.session_state.cart:
    st.divider()
    df_final = pd.DataFrame(st.session_state.cart)
    df_final['מחיר ללקוח'] = df_final['מחיר לסוכן'].apply(lambda x: round(x * (1 + margin/100), 2))
    
    st.subheader("📋 הצעת מחיר סופית")
    cols = ["סטטוס", "תאור מוצר", "כמות", "מקט / CONFIG", "מחיר לסוכן", "מחיר ללקוח"]
    st.table(df_final[cols])
    
    if st.button("🗑️ נקה הכל"):
        st.session_state.cart = []
        st.rerun()
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final[cols].to_excel(writer, index=False)
    st.download_button("📥 הורד אקסל ללקוח", data=output.getvalue(), file_name="Quote.xlsx")
