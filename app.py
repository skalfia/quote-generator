import streamlit as st
import pandas as pd
import json
import re
import io
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

.main-header h1 {
    color: var(--green-neon) !important;
    font-weight: 800 !important;
    margin: 0 !important;
}

/* עיצוב כרטיס סל */
.cart-item {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-right: 5px solid var(--green-neon);
    border-radius: 10px;
    padding: 12px;
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.price-display {
    font-family: 'JetBrains Mono', monospace;
    color: var(--green-neon);
    font-weight: 600;
}

/* עיצוב שורות המלאי לחיפוש */
.inventory-row {
    background: rgba(255,255,255,0.03);
    border-bottom: 1px solid var(--border);
    padding: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.inventory-row:hover {
    background: rgba(77, 187, 77, 0.1);
}
</style>
""", unsafe_allow_html=True)

# --- ניהול State ---
if "inventory" not in st.session_state: st.session_state.inventory = None
if "cart" not in st.session_state: st.session_state.cart = []
if "ai_chat" not in st.session_state: st.session_state.ai_chat = ""

# --- פונקציות לוגיות ---
def parse_clean_json(text):
    text = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()
    match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
    return match.group(1) if match else text

def format_price(val):
    try:
        if pd.isna(val): return 0.0
        if isinstance(val, (int, float)): return float(val)
        cleaned = re.sub(r'[^\d.]', '', str(val))
        return float(cleaned) if cleaned else 0.0
    except: return 0.0

def export_to_excel(cart_data, margin):
    wb = Workbook()
    ws = wb.active
    ws.title = "הצעת מחיר"
    ws.sheet_view.rightToLeft = True
    headers = ["סטטוס", "תיאור פריט", "מק\"ט", "כמות", "מחיר ספק", "מחיר ללקוח", "סה\"כ"]
    ws.append(headers)
    
    fill = PatternFill(start_color="1A3A1A", end_color="1A3A1A", fill_type="solid")
    font = Font(bold=True, color="4DBB4D")
    for cell in ws[1]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center")

    for item in cart_data:
        agent_p = format_price(item.get('price', 0))
        cust_p = round(agent_p * (1 + margin/100), 2)
        qty = int(item.get('quantity', 1))
        ws.append([item.get('status', 'רכש'), item.get('description', ''), item.get('sku', ''), qty, agent_p, cust_p, cust_p * qty])
    
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

# --- Sidebar ---
with st.sidebar:
    st.markdown("### ⚙️ הגדרות")
    api_key = st.text_input("Gemini API Key", type="password")
    profit_margin = st.slider("מתח רווח (%)", 0, 100, 20)
    
    model = None
    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            st.success("AI Online")
        except: st.error("Key Error")

# --- גוף האפליקציה ---
st.markdown('<div class="main-header"><h1>PC Pro Manager</h1></div>', unsafe_allow_html=True)

tabs = st.tabs(["📦 מלאי וחיפוש", "📝 חילוץ נתונים", "📑 סל וייצוא"])

with tabs[0]:
    c1, c2 = st.columns([1, 1])
    with c1:
        uploaded_file = st.file_uploader("טען אקסל מלאי (XLSX)", type=["xlsx"])
        if uploaded_file:
            try:
                file_bytes = uploaded_file.read()
                try:
                    df = pd.read_excel(io.BytesIO(file_bytes), engine='openpyxl')
                except:
                    wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
                    sheet = wb.active
                    data = list(sheet.values)
                    df = pd.DataFrame(data[1:], columns=data[0])
                st.session_state.inventory = df
                st.success(f"נטענו {len(df)} שורות")
            except Exception as e:
                st.error("שגיאה בטעינת הקובץ. נסה לשמור אותו מחדש כאקסל רגיל.")

    with c2:
        query = st.text_input("🤖 שאל את היועץ:")
        if st.button("בצע בדיקה") and model:
            inv_ctx = st.session_state.inventory.head(50).to_string() if st.session_state.inventory is not None else "אין מלאי"
            with st.spinner("בודק..."):
                res = model.generate_content(f"Inventory:\n{inv_ctx}\n\nQuestion: {query}")
                st.session_state.ai_chat = res.text
        if st.session_state.ai_chat:
            st.markdown(f'<div style="background:rgba(77,187,77,0.1); padding:10px; border-radius:10px;">{st.session_state.ai_chat}</div>', unsafe_allow_html=True)

    if st.session_state.inventory is not None:
        st.divider()
        search = st.text_input("🔍 חפש פריט (מק\"ט או שם):", placeholder="הקלד כאן...")
        
        if search:
            df = st.session_state.inventory
            # חיפוש חכם בכל העמודות
            res_df = df[df.apply(lambda r: search.lower() in str(r).lower(), axis=1)]
            
            if not res_df.empty:
                st.write(f"נמצאו {len(res_df)} תוצאות:")
                # תצוגת שורות עם כפתור הוספה ליד כל אחת
                for idx, row in res_df.iterrows():
                    sku = str(row.iloc[0])
                    name = str(row.iloc[1])
                    price = format_price(row.iloc[-1])
                    
                    col_info, col_btn = st.columns([5, 1])
                    with col_info:
                        st.markdown(f"**{sku}** | {name} | <span style='color:#4dbb4d'>${price}</span>", unsafe_allow_html=True)
                    with col_btn:
                        if st.button("➕", key=f"add_{idx}"):
                            st.session_state.cart.append({
                                "status": "מלאי",
                                "description": name,
                                "sku": sku,
                                "quantity": 1,
                                "price": price
                            })
                            st.toast(f"התווסף: {sku}")
                    st.markdown("<hr style='margin:5px 0; opacity:0.2'>", unsafe_allow_html=True)
            else:
                st.warning("לא נמצאו פריטים תואמים.")

with tabs[1]:
    txt = st.text_area("הדבק טקסט ממייל ספק:", height=200)
    if st.button("🚀 חלץ מוצרים") and model and txt:
        with st.spinner("מנתח..."):
            p = f"Parse to JSON list [{{'description','sku','quantity','price'}}] : {txt}"
            res = model.generate_content(p)
            try:
                data = json.loads(parse_clean_json(res.text))
                for d in data:
                    d['status'] = 'רכש'
                    st.session_state.cart.append(d)
                st.success("הפריטים חולצו ונוספו לסל!")
            except: st.error("שגיאה בחילוץ.")

with tabs[2]:
    st.subheader("🛒 ריכוז הצעת מחיר")
    if not st.session_state.cart:
        st.info("הסל ריק")
    else:
        for i, item in enumerate(st.session_state.cart):
            p_agent = format_price(item.get('price', 0))
            p_cust = round(p_agent * (1 + profit_margin/100), 2)
            
            c_info, c_del = st.columns([5, 1])
            with c_info:
                st.markdown(f"""
                <div class="cart-item">
                    <div><b>{item.get('description')}</b><br><small>{item.get('sku')} | {item.get('status')}</small></div>
                    <div class="price-display">${p_cust}</div>
                </div>
                """, unsafe_allow_html=True)
            with c_del:
                if st.button("🗑️", key=f"del_{i}"):
                    st.session_state.cart.pop(i)
                    st.rerun()
        
        st.divider()
        c_clear, c_down = st.columns(2)
        with c_clear:
            if st.button("נקה סל"):
                st.session_state.cart = []
                st.rerun()
        with c_down:
            xl = export_to_excel(st.session_state.cart, profit_margin)
            st.download_button("📥 הורד אקסל ללקוח", data=xl, file_name="Quote.xlsx")
