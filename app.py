import streamlit as st
import pandas as pd
import json
import re
import io
import base64
import google.generativeai as genai
from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill, Font, Alignment

# --- דף הגדרות ---
st.set_page_config(
    page_title="PC Pro Manager",
    page_icon="💻",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- עיצוב CSS ירוק ניאון ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@400;700;800&display=swap');

:root {
    --bg-primary: #0a0f0a;
    --bg-secondary: #0f1a0f;
    --bg-card: #111c11;
    --green-neon: #4dbb4d;
    --green-bright: #3a9c3a;
    --green-dim: #1a3a1a;
    --text-main: #e8f5e8;
    --border: #1e3a1e;
}

html, body, [class*="css"] {
    font-family: 'Syne', sans-serif !important;
    background-color: var(--bg-primary) !important;
    color: var(--text-main) !important;
    direction: rtl;
}

.stApp {
    background: linear-gradient(135deg, #0a0f0a 0%, #0d160d 50%, #0a0f0a 100%) !important;
}

.main-header {
    background: linear-gradient(90deg, var(--bg-card) 0%, var(--green-dim) 100%);
    border: 1px solid var(--green-bright);
    border-radius: 15px;
    padding: 20px;
    margin-bottom: 25px;
    text-align: center;
}

.inventory-item-box {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 10px;
}

.price-tag {
    font-family: 'JetBrains Mono', monospace;
    color: #ffd700;
    font-size: 1.2rem;
}

.extraction-table {
    background: rgba(255,255,255,0.05);
    border-radius: 10px;
    padding: 15px;
    border: 1px dashed var(--green-neon);
}
</style>
""", unsafe_allow_html=True)

# --- ניהול State ---
if "inventory" not in st.session_state: st.session_state.inventory = None
if "cart" not in st.session_state: st.session_state.cart = []
if "extracted_buffer" not in st.session_state: st.session_state.extracted_buffer = []

# --- פונקציות עזר ---
def format_num(val):
    try:
        if pd.isna(val) or val == "": return 0.0
        if isinstance(val, (int, float)): return float(val)
        cleaned = re.sub(r'[^\d.-]', '', str(val))
        return float(cleaned) if cleaned else 0.0
    except: return 0.0

def find_column(df, possible_names):
    for col in df.columns:
        clean_col = str(col).strip().replace(" ", "").replace("'", "").replace('"', "")
        for target in possible_names:
            if clean_col == target.replace(" ", "").replace("'", "").replace('"', ""):
                return col
    return None

def parse_clean_json(text):
    text = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()
    match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
    return match.group(1) if match else text

def export_to_excel(cart_data, margin):
    wb = Workbook()
    ws = wb.active
    ws.title = "הצעת מחיר"
    ws.sheet_view.rightToLeft = True
    headers = ["תיאור פריט", "מק\"ט", "כמות", "מחיר סוכן", "מחיר ללקוח", "סה\"כ"]
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = PatternFill(start_color="1A3A1A", end_color="1A3A1A", fill_type="solid")
        cell.font = Font(bold=True, color="4DBB4D")
    for item in cart_data:
        p_agent = format_num(item.get('price', 0))
        p_cust = round(p_agent * (1 + margin/100), 2)
        qty = int(item.get('quantity', 1))
        ws.append([item.get('description', ''), item.get('sku', ''), qty, p_agent, p_cust, p_cust * qty])
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

# --- Sidebar ---
with st.sidebar:
    st.markdown("### ⚙️ הגדרות")
    api_key = st.text_input("Gemini API Key", type="password")
    profit_margin = st.slider("רווח ללקוח (%)", 0, 100, 20)
    
    model = None
    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            st.success("AI Online")
        except: st.error("API Error")

# --- דף ראשי ---
st.markdown('<div class="main-header"><h1>PC Pro Manager</h1></div>', unsafe_allow_html=True)

tabs = st.tabs(["🔍 חיפוש מלאי", "📝 חילוץ מרשימות (AI)", "🛒 סל הצעות"])

with tabs[0]:
    c1, c2 = st.columns([1, 2])
    with c1:
        file = st.file_uploader("טען אקסל מלאי", type=["xlsx"])
        if file:
            try:
                st.session_state.inventory = pd.read_excel(file)
                st.success("המלאי נטען!")
            except: st.error("שגיאה בקובץ")
    with c2:
        q = st.text_input("חפש מוצר:")

    if st.session_state.inventory is not None and q:
        df = st.session_state.inventory
        # זיהוי עמודות לפי הבקשה שלך
        c_sku = find_column(df, ["מק'ט", "מקט", "מק\"ט"])
        c_desc = find_column(df, ["תאור מוצר", "תיאור מוצר"])
        c_bal = find_column(df, ["יתרה מחסני מכירה"])
        c_ord = find_column(df, ["הזמנות לקוח"])
        c_pur = find_column(df, ["כמות ברכש"])
        c_prc = find_column(df, ["מחיר מוצג לסוכן $"])
        
        res = df[df.apply(lambda r: q.lower() in str(r).lower(), axis=1)]
        
        for idx, row in res.iterrows():
            v_bal = format_num(row[c_bal]) if c_bal else 0
            v_ord = format_num(row[c_ord]) if c_ord else 0
            v_pur = format_num(row[c_pur]) if c_pur else 0
            v_total = v_bal - v_ord + v_pur
            v_price = format_num(row[c_prc]) if c_prc else 0
            sku = str(row[c_sku]) if c_sku else "N/A"
            desc = str(row[c_desc]) if c_desc else "N/A"
            
            st.markdown(f"""
            <div class="inventory-item-box">
                <div style="display:flex; justify-content:space-between">
                    <b>{desc}</b>
                    <span class="price-tag">${v_price}</span>
                </div>
                <div style="font-size:0.8rem; opacity:0.7">מק"ט: {sku}</div>
                <div style="display:flex; gap:20px; margin-top:10px; padding-top:10px; border-top:1px solid #222">
                    <div>יתרה: {int(v_bal)}</div>
                    <div style="color:#ff6b6b">הזמנות: -{int(v_ord)}</div>
                    <div style="color:#4dabf7">ברכש: +{int(v_pur)}</div>
                    <div style="color:var(--green-neon); font-weight:800">זמין: {int(v_total)}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"➕ הוסף להצעה", key=f"add_{idx}"):
                st.session_state.cart.append({"description": desc, "sku": sku, "price": v_price, "quantity": 1})
                st.toast("נוסף לסל")

with tabs[1]:
    st.subheader("חילוץ נתונים חכם")
    st.write("הדבק מייל או העלה צילום מסך של הצעת מחיר ספק.")
    
    ca1, ca2 = st.columns(2)
    with ca1:
        txt_area = st.text_area("טקסט ממייל:", height=200)
    with ca2:
        img_file = st.file_uploader("צילום מסך:", type=["png", "jpg", "jpeg"])

    if st.button("🚀 נתח נתונים") and model:
        with st.spinner("ה-AI סורק את המידע..."):
            prompt = """
            Act as a data extractor for computer hardware.
            Scan the provided image or text. Look for product tables, email lists, or quote summaries.
            Extract EVERY product found.
            Return a JSON list: [{"description": "Full product name", "sku": "Part number", "quantity": number, "price": number}].
            Focus:
            - Price is usually a number near $ or ₪. 
            - SKU is often a mix of letters and numbers (e.g., HP-123, 456-789).
            - Ignore signatures, addresses, and footer text.
            """
            
            if img_file:
                img_data = base64.b64encode(img_file.read()).decode()
                response = model.generate_content([prompt, {"inline_data": {"mime_type": "image/jpeg", "data": img_data}}])
            else:
                response = model.generate_content(f"{prompt}\nContent: {txt_area}")
            
            try:
                st.session_state.extracted_buffer = json.loads(parse_clean_json(response.text))
                st.success(f"זיהיתי {len(st.session_state.extracted_buffer)} פריטים!")
            except:
                st.error("ה-AI לא הצליח לקרוא את הפורמט. נסה טקסט ברור יותר.")

    if st.session_state.extracted_buffer:
        st.markdown('<div class="extraction-table">', unsafe_allow_html=True)
        st.write("### ערוך ואשר פריטים לפני הוספה:")
        for i, item in enumerate(st.session_state.extracted_buffer):
            col1, col2, col3, col4, col5 = st.columns([3, 2, 1, 1, 0.5])
            with col1: new_desc = st.text_input(f"תיאור {i}", item.get('description'), label_visibility="collapsed")
            with col2: new_sku = st.text_input(f"מק\"ט {i}", item.get('sku'), label_visibility="collapsed")
            with col3: new_qty = st.number_input(f"כמות {i}", value=int(item.get('quantity', 1)) or 1, label_visibility="collapsed")
            with col4: new_prc = st.number_input(f"מחיר {i}", value=float(item.get('price', 0)), label_visibility="collapsed")
            with col5: 
                if st.button("🗑️", key=f"rem_buf_{i}"):
                    st.session_state.extracted_buffer.pop(i)
                    st.rerun()
            # עדכון הבאפר בזמן אמת
            st.session_state.extracted_buffer[i] = {"description": new_desc, "sku": new_sku, "quantity": new_qty, "price": new_prc}
        
        if st.button("✅ הוסף את הכל לסל ההצעות"):
            for itm in st.session_state.extracted_buffer:
                st.session_state.cart.append(itm)
            st.session_state.extracted_buffer = []
            st.success("הפריטים נוספו לסל!")
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

with tabs[2]:
    st.subheader("🛒 ריכוז הצעת מחיר")
    if not st.session_state.cart:
        st.info("הסל ריק")
    else:
        total = 0
        for i, item in enumerate(st.session_state.cart):
            p_agent = format_num(item.get('price', 0))
            p_cust = round(p_agent * (1 + profit_margin/100), 2)
            qty = int(item.get('quantity', 1))
            total += (p_cust * qty)
            
            ci, cd = st.columns([6, 1])
            with ci:
                st.markdown(f"""
                <div style="background:#152015; padding:10px; border-radius:5px; margin-bottom:5px; border-right:3px solid var(--green-neon)">
                    <b>{item['description']}</b><br>
                    <small>מק"ט: {item['sku']} | כמות: {qty} | מחיר ללקוח: <b>${p_cust}</b></small>
                </div>
                """, unsafe_allow_html=True)
            with cd:
                if st.button("🗑️", key=f"del_item_{i}"):
                    st.session_state.cart.pop(i)
                    st.rerun()
        
        st.markdown(f"### סה\"כ הצעת מחיר: **${round(total, 2)}**")
        st.divider()
        col_c, col_e = st.columns(2)
        with col_c:
            if st.button("מחק הכל"):
                st.session_state.cart = []
                st.rerun()
        with col_e:
            xl = export_to_excel(st.session_state.cart, profit_margin)
            st.download_button("📥 ייצא הצעת מחיר לאקסל", data=xl, file_name="PC_Pro_Quote.xlsx")
