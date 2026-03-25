import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import re
import PyPDF2

st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

# פונקציה לחילוץ JSON מתוך טקסט (פותרת את השגיאה שראית בתמונה)
def extract_json(text):
    try:
        # מחפש את התוכן שבין הסוגריים המרובעים של הרשימה
        match = re.search(r'\[\s*{.*}\s*\]', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        # ניסיון נוסף ללא Markdown
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
st.sidebar.title("🛠️ הגדרות מערכת")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")
margin = st.sidebar.slider("מתח רווח להוספה (%)", 0, 100, 15)

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    st.sidebar.success("✅ AI מחובר")

if 'cart' not in st.session_state: st.session_state.cart = []
if 'inventory_df' not in st.session_state: st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מערכת הצעות מחיר - קובי")

tab1, tab2, tab3 = st.tabs(["🏢 המחסן שלי", "📧 חילוץ מטקסט/מייל", "📄 חילוץ מ-PDF/Excel"])

# --- לשונית 1: מלאי מקומי ---
with tab1:
    uploaded_inv = st.file_uploader("טען אקסל מלאי", type=["xlsx"])
    if uploaded_inv:
        df = pd.read_excel(uploaded_inv)
        df.columns = [" ".join(str(c).split()).strip() for c in df.columns]
        st.session_state.inventory_df = df
        st.success("המלאי נטען")

    if not st.session_state.inventory_df.empty:
        inv = st.session_state.inventory_df
        search = st.selectbox("🔍 חפש מוצר:", [""] + [f"{r[0]} | {r[1]}" for r in inv.iloc[:, :2].values])
        if search:
            sku_val = search.split(" | ")[0]
            row = inv[inv.iloc[:, 0].astype(str) == sku_val].iloc[0]
            qty = st.number_input("כמות:", min_value=1, value=1)
            if st.button("➕ הוסף להצעה"):
                st.session_state.cart.append({
                    "סטטוס": "מלאי",
                    "תאור מוצר": row[1],
                    "כמות": qty,
                    "מקט / CONFIG": row[0],
                    "מחיר לסוכן": parse_price(row[-1]) # לוקח עמודה אחרונה כמחיר
                })

# --- לשונית 2: חילוץ ממיילים / טקסט חופשי ---
with tab2:
    pasted = st.text_area("הדבק כאן טקסט לא מובן, מייל או רשימה:", height=300)
    if st.button("🚀 חלץ נתונים עם AI"):
        with st.spinner("מנתח טקסט..."):
            prompt = f"""
            Identify all hardware products in the text below.
            Extract: SKU/Part Number, Description, and Price.
            Return ONLY a JSON list: [{{"sku": "...", "desc": "...", "price": 123}}]
            Text: {pasted}
            """
            res = model.generate_content(prompt)
            data = extract_json(res.text)
            if data:
                for i in data:
                    st.session_state.cart.append({
                        "סטטוס": "רכש (ספק)",
                        "תאור מוצר": i.get('desc', ''),
                        "כמות": 1,
                        "מקט / CONFIG": i.get('sku', ''),
                        "מחיר לסוכן": parse_price(i.get('price', 0))
                    })
                st.success(f"חולצו {len(data)} פריטים")
            else:
                st.error("ה-AI לא הצליח לייצר רשימה תקינה. נסה להדביק שוב.")

# --- לשונית 3: חילוץ מקבצים (PDF/Excel של ספקים) ---
with tab3:
    uploaded_file = st.file_uploader("טען קובץ ספק (PDF או Excel)", type=["pdf", "xlsx"])
    if uploaded_file and st.button("🔍 חלץ מהקובץ"):
        content = ""
        if uploaded_file.type == "application/pdf":
            reader = PyPDF2.PdfReader(uploaded_file)
            for page in reader.pages:
                content += page.extract_text()
        else:
            df_file = pd.read_excel(uploaded_file)
            content = df_file.to_string()
        
        with st.spinner("AI קורא את הקובץ..."):
            res = model.generate_content(f"Extract products as JSON from this file content: {content}")
            data = extract_json(res.text)
            if data:
                for i in data:
                    st.session_state.cart.append({
                        "סטטוס": "רכש (ספק)", "תאור מוצר": i.get('desc', ''),
                        "כמות": 1, "מקט / CONFIG": i.get('sku', ''), "מחיר לסוכן": parse_price(i.get('price', 0))
                    })
                st.success("הנתונים חולצו מהקובץ!")

# --- תצוגת הצעה סופית ---
if st.session_state.cart:
    st.divider()
    final_df = pd.DataFrame(st.session_state.cart)
    final_df['מחיר ללקוח'] = final_df['מחיר לסוכן'].apply(lambda x: round(x * (1 + margin/100), 2))
    
    st.subheader("📋 הצעת מחיר סופית")
    st.table(final_df[["סטטוס", "תאור מוצר", "כמות", "מקט / CONFIG", "מחיר לסוכן", "מחיר ללקוח"]])
    
    if st.button("🗑️ נקה הכל"):
        st.session_state.cart = []
        st.rerun()
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        final_df.to_excel(writer, index=False)
    st.download_button("📥 הורד אקסל ללקוח", data=output.getvalue(), file_name="Quote.xlsx")
