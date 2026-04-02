import streamlit as st
import pandas as pd
import json
import re
import io
import google.generativeai as genai
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

# --- הגדרות דף ---
st.set_page_config(
    page_title="PC Pro Manager",
    page_icon="💻",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- עיצוב CSS ירוק ניאון פרימיום ---
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
    padding: 25px;
    margin-bottom: 30px;
    text-align: center;
}

.main-header h1 {
    color: var(--green-neon) !important;
    font-weight: 800 !important;
    margin: 0 !important;
}

.cart-item {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-right: 5px solid var(--green-neon);
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.price-display {
    font-family: 'JetBrains Mono', monospace;
    color: var(--green-neon);
    font-weight: 600;
    font-size: 1.3rem;
}

.ai-box {
    background: linear-gradient(135deg, var(--bg-card), var(--green-dim));
    border: 1px solid var(--green-bright);
    border-radius: 12px;
    padding: 20px;
    margin-top: 15px;
    line-height: 1.6;
}

.stTabs [data-baseweb="tab-list"] {
    background: var(--bg-secondary) !important;
    border-radius: 12px !important;
}
</style>
""", unsafe_allow_html=True)

# --- ניהול ה-State ---
if "inventory" not in st.session_state: st.session_state.inventory = None
if "cart" not in st.session_state: st.session_state.cart = []
if "ai_chat" not in st.session_state: st.session_state.ai_chat = ""

# --- פונקציות לוגיות חסינות ---
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
    
    headers = ["סטטוס", "תיאור פריט", "מק\"ט", "כמות", "מחיר ספק", "מחיר ללקוח", "סה\"כ ללקוח"]
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
        ws.append([
            item.get('status', 'רכש'),
            item.get('description', ''),
            item.get('sku', ''),
            qty,
            agent_p,
            cust_p,
            cust_p * qty
        ])
    
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

# --- Sidebar ---
with st.sidebar:
    st.markdown("### ⚙️ הגדרות מערכת")
    api_key = st.text_input("Gemini API Key", type="password")
    profit_margin = st.slider("מתח רווח ללקוח (%)", 0, 100, 20)
    
    model = None
    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(
                model_name='gemini-1.5-flash',
                system_instruction="You are an expert PC Hardware advisor for Kobi. Help with specs and parsing. Keep it professional."
            )
            st.success("AI Online")
        except: st.error("Key Error")

# --- ממשק משתמש ---
st.markdown('<div class="main-header"><h1>PC Pro Manager</h1><p>ניהול מלאי והצעות מחיר חכמות | קובי אלפיה</p></div>', unsafe_allow_html=True)

tabs = st.tabs(["📦 ניהול מלאי", "📝 חילוץ נתונים", "📑 סל מוצרים"])

with tabs[0]:
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("#### טעינת אקסל מלאי")
        uploaded_file = st.file_uploader("בחר קובץ אקסל (XLSX)", type=["xlsx"])
        
        if uploaded_file:
            try:
                # שימוש ב-openpyxl לטיפול בשגיאות BadZipFile
                st.session_state.inventory = pd.read_excel(uploaded_file, engine='openpyxl')
                st.success(f"המלאי נטען בהצלחה! ({len(st.session_state.inventory)} שורות)")
            except Exception as e:
                st.error(f"שגיאה בקריאת הקובץ: {str(e)}")
                st.info("ודא שהקובץ הוא אקסל תקין מסוג .xlsx")
            
    with c2:
        st.markdown("#### 🤖 יועץ AI")
        query = st.text_input("שאל שאלה טכנית (למשל: איזה זיכרון מתאים ל-HP G11?):")
        if st.button("שאל את המומחה") and model:
            inv_context = st.session_state.inventory.head(100).to_string() if st.session_state.inventory is not None else "No inventory."
            with st.spinner("מנתח..."):
                response = model.generate_content(f"Inventory Summary:\n{inv_context}\n\nUser Question: {query}")
                st.session_state.ai_chat = response.text
        
        if st.session_state.ai_chat:
            st.markdown(f'<div class="ai-box"><b>תשובה:</b><br>{st.session_state.ai_chat}</div>', unsafe_allow_html=True)

    if st.session_state.inventory is not None:
        st.divider()
        search = st.text_input("🔍 חפש פריט במחסן:")
        if search:
            df = st.session_state.inventory
            res = df[df.apply(lambda r: search.lower() in str(r).lower(), axis=1)]
            st.dataframe(res, use_container_width=True)
            
            # ניסיון זיהוי עמודות באופן אוטומטי
            cols = res.columns.tolist()
            picked_row_idx = st.selectbox("בחר שורה להוספה:", res.index.tolist(), format_func=lambda x: f"שורה {x}: {res.loc[x].iloc[0]}")
            
            if st.button("➕ הוסף לסל מהמלאי"):
                row_data = res.loc[picked_row_idx]
                st.session_state.cart.append({
                    "status": "מלאי",
                    "description": str(row_data.iloc[1]) if len(row_data) > 1 else "פריט מלאי",
                    "sku": str(row_data.iloc[0]),
                    "quantity": 1,
                    "price": format_price(row_data.iloc[-1])
                })
                st.toast("התווסף לסל!")

with tabs[1]:
    st.markdown("#### חילוץ מוצרים מטקסט חופשי (מייל ספק)")
    raw_input = st.text_area("הדבק כאן את תוכן המייל:", height=250)
    if st.button("🚀 חלץ מוצרים") and model and raw_input:
        with st.spinner("AI מנתח את הטקסט..."):
            p = f"Parse to JSON list [{{'description','sku','quantity','price'}}] : {raw_input}"
            res = model.generate_content(p)
            try:
                items = json.loads(parse_clean_json(res.text))
                for i in items:
                    i['status'] = 'רכש'
                    st.session_state.cart.append(i)
                st.success(f"חולצו {len(items)} פריטים בהצלחה!")
            except: st.error("שגיאה בפענוח. נסה להדביק טקסט ברור יותר.")

with tabs[2]:
    st.markdown("#### סיכום הצעת מחיר")
    if not st.session_state.cart:
        st.info("הסל ריק כרגע.")
    else:
        for idx, item in enumerate(st.session_state.cart):
            p_agent = format_price(item.get('price', 0))
            p_customer = round(p_agent * (1 + profit_margin/100), 2)
            st.markdown(f"""
            <div class="cart-item">
                <div>
                    <b>{item.get('description', 'פריט')}</b><br>
                    <small>מק"ט: {item.get('sku', '---')} | סטטוס: {item.get('status', '---')}</small>
                </div>
                <div class="price-display">${p_customer}</div>
            </div>
            """, unsafe_allow_html=True)
        
        col_down1, col_down2 = st.columns(2)
        with col_down1:
            if st.button("🗑️ נקה סל"):
                st.session_state.cart = []
                st.rerun()
        with col_down2:
            xls_data = export_to_excel(st.session_state.cart, profit_margin)
            st.download_button(
                "📥 הורד אקסל מקצועי ללקוח",
                data=xls_data,
                file_name=f"Quote_PC_Pro_{pd.Timestamp.now().strftime('%d_%m_%y')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
