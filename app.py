import streamlit as st
import pandas as pd
import json
import re
import io
import google.generativeai as genai
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

# --- הקונפיגורציה של הדף ---
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

/* כותרת */
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

/* כרטיס פריט בסל */
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

/* AI Answer Box */
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

# --- ניהול ה-State של המערכת ---
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
        return float(re.sub(r'[^\d.]', '', str(val)))
    except: return 0.0

def export_to_excel(cart_data, margin):
    wb = Workbook()
    ws = wb.active
    ws.title = "הצעת מחיר"
    ws.sheet_view.rightToLeft = True
    
    headers = ["סטטוס", "תיאור פריט", "מק\"ט", "כמות", "מחיר ספק", "מחיר ללקוח", "סה\"כ"]
    ws.append(headers)
    
    # עיצוב כותרות
    fill = PatternFill(start_color="1A3A1A", end_color="1A3A1A", fill_type="solid")
    font = Font(bold=True, color="4DBB4D")
    for cell in ws[1]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center")

    for item in cart_data:
        agent_p = float(item.get('price', 0))
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
    st.markdown("### ⚙️ הגדרות")
    api_key = st.text_input("Gemini API Key", type="password")
    profit_margin = st.slider("מתח רווח (%)", 0, 100, 20)
    
    model = None
    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(
                model_name='gemini-1.5-flash',
                system_instruction="""You are an elite PC hardware expert. 
                Your job is to assist Kobi in managing IT inventory and quotes.
                1. Always prioritize checking the provided inventory.
                2. Be technically precise (DDR types, Slots, Chipsets).
                3. If asked for a recommendation (like 'What RAM fits HP G11?'), check the inventory for compatible parts first.
                4. For parsing requests, return ONLY a JSON list."""
            )
            st.success("AI Online")
        except: st.error("Key Error")

# --- ממשק משתמש ---
st.markdown('<div class="main-header"><h1>PC Pro Manager</h1><p>מערכת חכמה לניהול חומרה ומלאי - קובי אלפיה</p></div>', unsafe_allow_html=True)

tabs = st.tabs(["📦 מלאי וייעוץ", "📝 חילוץ חכם", "📑 הצעת מחיר"])

with tabs[0]:
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("#### טעינת מחסן")
        file = st.file_uploader("העלה אקסל (XLSX)", type=["xlsx"])
        if file:
            st.session_state.inventory = pd.read_excel(file)
            st.success(f"המלאי עודכן: {len(st.session_state.inventory)} שורות")
            
    with c2:
        st.markdown("#### 🤖 יועץ חומרה")
        query = st.text_input("שאל שאלה טכנית על תאימות או מלאי:")
        if st.button("שאל את המכונה") and model and query:
            inv_context = st.session_state.inventory.head(200).to_string() if st.session_state.inventory is not None else "No inventory loaded."
            with st.spinner("בודק..."):
                full_query = f"Based on this inventory summary:\n{inv_context}\n\nQuestion: {query}"
                response = model.generate_content(full_query)
                st.session_state.ai_chat = response.text
        
        if st.session_state.ai_chat:
            st.markdown(f'<div class="ai-box"><b>תשובת מומחה:</b><br>{st.session_state.ai_chat}</div>', unsafe_allow_html=True)

    if st.session_state.inventory is not None:
        st.divider()
        search = st.text_input("🔍 חיפוש פריט במלאי:")
        if search:
            df = st.session_state.inventory
            res = df[df.apply(lambda r: search.lower() in str(r).lower(), axis=1)]
            st.dataframe(res, use_container_width=True)
            
            picked = st.selectbox("בחר מק\"ט להוספה:", [""] + res.iloc[:,0].astype(str).tolist())
            if picked and st.button("➕ הוסף לסל מהמחסן"):
                match = res[res.iloc[:,0].astype(str) == picked].iloc[0]
                st.session_state.cart.append({
                    "status": "מלאי",
                    "description": match[1],
                    "sku": match[0],
                    "quantity": 1,
                    "price": format_price(match[-1])
                })
                st.toast("הפריט נוסף לסל")

with tabs[1]:
    st.markdown("#### חילוץ מוצרים מטקסט")
    raw_input = st.text_area("הדבק מייל או רשימה גולמית כאן:", height=250)
    if st.button("🚀 חלץ מוצרים עם AI") and model and raw_input:
        with st.spinner("מנתח נתונים..."):
            p = f"Convert this to JSON list [{{'description','sku','quantity','price'}}] : {raw_input}"
            res = model.generate_content(p)
            try:
                items = json.loads(parse_clean_json(res.text))
                for i in items:
                    i['status'] = 'רכש'
                    st.session_state.cart.append(i)
                st.success(f"חולצו {len(items)} פריטים בהצלחה!")
            except: st.error("ה-AI לא הצליח לייצר מבנה תקין. נסה שוב.")

with tabs[2]:
    st.markdown("#### סיכום הצעת מחיר")
    if not st.session_state.cart:
        st.info("הסל ריק. הוסף מוצרים מהמחסן או מחילוץ הטקסט.")
    else:
        for idx, item in enumerate(st.session_state.cart):
            p_agent = float(item.get('price', 0))
            p_customer = round(p_agent * (1 + profit_margin/100), 2)
            st.markdown(f"""
            <div class="cart-item">
                <div>
                    <b>{item.get('description', 'ללא תיאור')}</b><br>
                    <small>מק"ט: {item.get('sku', '---')} | סטטוס: {item.get('status', '---')}</small>
                </div>
                <div class="price-display">${p_customer}</div>
            </div>
            """, unsafe_allow_html=True)
        
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🗑️ נקה הכל"):
                st.session_state.cart = []
                st.rerun()
        with col_b:
            xls = export_to_excel(st.session_state.cart, profit_margin)
            st.download_button(
                "📥 הורד קובץ אקסל סופי",
                data=xls,
                file_name=f"Quote_{pd.Timestamp.now().strftime('%d_%m_%y')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
