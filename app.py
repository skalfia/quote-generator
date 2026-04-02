import streamlit as st
import pandas as pd
import json
import re
import io
import base64
import google.generativeai as genai
from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill, Font, Alignment

# --- הגדרות דף ---
st.set_page_config(
    page_title="PC Pro Manager",
    page_icon="💻",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- עיצוב CSS ירוק ניאון מתקדם ---
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

.available-qty {
    color: var(--green-neon);
    font-size: 1.2rem;
    font-weight: 800;
}

.price-tag {
    font-family: 'JetBrains Mono', monospace;
    color: #ffd700;
    font-size: 1.3rem;
}

.cart-item-row {
    background: rgba(255,255,255,0.03);
    border-right: 4px solid var(--green-neon);
    padding: 10px;
    margin-bottom: 8px;
    border-radius: 4px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

/* Print Styles */
@media print {
    .no-print { display: none !important; }
    body { background: white !important; color: black !important; }
}
</style>
""", unsafe_allow_html=True)

# --- ניהול State ---
if "inventory" not in st.session_state: st.session_state.inventory = None
if "cart" not in st.session_state: st.session_state.cart = []
if "ai_analysis" not in st.session_state: st.session_state.ai_analysis = ""

# --- פונקציות עזר ---
def format_num(val):
    try:
        if pd.isna(val): return 0.0
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
    headers = ["תיאור פריט", "מק\"ט", "כמות", "מחיר ללקוח", "סה\"כ"]
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = PatternFill(start_color="1A3A1A", end_color="1A3A1A", fill_type="solid")
        cell.font = Font(bold=True, color="4DBB4D")
    for item in cart_data:
        p_cust = round(format_num(item.get('price', 0)) * (1 + margin/100), 2)
        qty = int(item.get('quantity', 1))
        ws.append([item.get('description', ''), item.get('sku', ''), qty, p_cust, p_cust * qty])
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

# --- Sidebar ---
with st.sidebar:
    st.markdown("### ⚙️ הגדרות מערכת")
    api_key = st.text_input("Gemini API Key", type="password")
    profit_margin = st.slider("רווח ללקוח (%)", 0, 100, 20)
    
    model = None
    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            st.success("AI מוכן")
        except: st.error("Key Error")

# --- דף ראשי ---
st.markdown('<div class="main-header"><h1>PC Pro Manager</h1></div>', unsafe_allow_html=True)

tabs = st.tabs(["🔍 חיפוש במלאי", "📝 חילוץ ממייל/תמונה", "🛒 סל והצעת מחיר"])

with tabs[0]:
    c_up1, c_up2 = st.columns([1, 2])
    with c_up1:
        uploaded_inventory = st.file_uploader("טען אקסל מלאי", type=["xlsx"])
        if uploaded_inventory:
            try:
                df = pd.read_excel(uploaded_inventory, engine='openpyxl')
                st.session_state.inventory = df
                st.success(f"נטענו {len(df)} פריטים")
            except: st.error("שגיאה בקובץ")

    with c_up2:
        search_query = st.text_input("חפש מוצר (מק\"ט / תיאור):", placeholder="חפש כאן...")

    if st.session_state.inventory is not None and search_query:
        df = st.session_state.inventory
        col_sku = find_column(df, ["מק'ט", "מקט", "מק\"ט"])
        col_desc = find_column(df, ["תאור מוצר", "תיאור מוצר"])
        col_bal = find_column(df, ["יתרה מחסני מכירה", "יתרה"])
        col_orders = find_column(df, ["הזמנות לקוח"])
        col_purch = find_column(df, ["כמות ברכש"])
        col_price = find_column(df, ["מחיר מוצג לסוכן $", "מחיר סוכן"])
        
        res = df[df.apply(lambda r: search_query.lower() in str(r).lower(), axis=1)]
        
        if not res.empty:
            for idx, row in res.iterrows():
                sku = str(row[col_sku]) if col_sku else "N/A"
                desc = str(row[col_desc]) if col_desc else "N/A"
                v_bal = format_num(row[col_bal]) if col_bal else 0
                v_orders = format_num(row[col_orders]) if col_orders else 0
                v_purch = format_num(row[col_purch]) if col_purch else 0
                v_price = format_num(row[col_price]) if col_price else 0
                v_total = v_bal - v_orders + v_purch
                
                st.markdown(f"""
                <div class="inventory-item-box">
                    <div style="display: flex; justify-content: space-between;">
                        <div><b>{desc}</b><br><small>מק"ט: {sku}</small></div>
                        <div class="price-tag">${v_price}</div>
                    </div>
                    <div style="display: flex; gap: 15px; margin-top: 10px; border-top: 1px solid #1e3a1e; padding-top: 10px;">
                        <div style="flex:1"><small>מלאי:</small><br><b>{int(v_bal)}</b></div>
                        <div style="flex:1"><small>הזמנות:</small><br><b style="color:#ff4b4b">-{int(v_orders)}</b></div>
                        <div style="flex:1"><small>ברכש:</small><br><b style="color:#4d88ff">+{int(v_purch)}</b></div>
                        <div style="flex:1; background:rgba(77,187,77,0.1); border-radius:5px; text-align:center;">
                            <small>זמין:</small><br><b class="available-qty">{int(v_total)}</b>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"➕ הוסף לסל", key=f"add_{idx}"):
                    st.session_state.cart.append({"description": desc, "sku": sku, "price": v_price, "quantity": 1})
                    st.toast(f"התווסף {sku}")

with tabs[1]:
    st.subheader("חילוץ מוצרים חכם (AI)")
    c_ai1, c_ai2 = st.columns(2)
    with c_ai1:
        st.write("הדבק טקסט ממייל או רשימת ספק:")
        mail_input = st.text_area("טקסט כאן:", height=200)
    with c_ai2:
        st.write("או העלה צילום מסך של הצעה:")
        img_input = st.file_uploader("העלה תמונה", type=["png", "jpg", "jpeg"])

    if st.button("🚀 חלץ פריטים") and model:
        with st.spinner("ה-AI מנתח את הנתונים..."):
            prompt = "Extract list of items to JSON: [{'description','sku','quantity','price'}]. Price must be numbers only."
            if img_input:
                img_data = base64.b64encode(img_input.read()).decode()
                response = model.generate_content([prompt, {"inline_data": {"mime_type": "image/jpeg", "data": img_data}}])
            else:
                response = model.generate_content(f"{prompt}\nText: {mail_input}")
            
            try:
                extracted = json.loads(parse_clean_json(response.text))
                for item in extracted:
                    st.session_state.cart.append(item)
                st.success(f"חולצו {len(extracted)} פריטים בהצלחה!")
            except:
                st.error("ה-AI לא הצליח לפענח את המבנה. נסה טקסט ברור יותר.")

with tabs[2]:
    st.subheader("🛒 סיכום הצעת מחיר")
    if not st.session_state.cart:
        st.info("הסל ריק")
    else:
        total_sum = 0
        for i, item in enumerate(st.session_state.cart):
            p_agent = format_num(item.get('price', 0))
            p_cust = round(p_agent * (1 + profit_margin/100), 2)
            qty = item.get('quantity', 1)
            total_sum += (p_cust * qty)
            
            col_i, col_d = st.columns([6, 1])
            with col_i:
                st.markdown(f"""
                <div class="cart-item-row">
                    <span><b>{item['description']}</b> ({item['sku']})</span>
                    <span>מחיר יח': <b>${p_cust}</b></span>
                </div>
                """, unsafe_allow_html=True)
            with col_d:
                if st.button("🗑️", key=f"del_{i}"):
                    st.session_state.cart.pop(i)
                    st.rerun()
        
        st.markdown(f"### סה\"כ לתשלום: ${round(total_sum, 2)}")
        st.divider()
        
        c_act1, c_act2, c_act3 = st.columns(3)
        with c_act1:
            if st.button("🗑️ נקה הכל"):
                st.session_state.cart = []
                st.rerun()
        with c_act2:
            xl_out = export_to_excel(st.session_state.cart, profit_margin)
            st.download_button("📥 הורד Excel", data=xl_out, file_name="Quote.xlsx")
        with c_act3:
            st.button("🖨️ הדפס/שמור PDF (Ctrl+P)")
