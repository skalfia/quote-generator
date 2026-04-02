import streamlit as st
import pandas as pd
import json
import re
import io
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
            model = genai.GenerativeModel('gemini-1.5-flash')
            st.success("AI Online")
        except: st.error("שגיאה במפתח")

# --- גוף האפליקציה ---
st.markdown('<div class="main-header"><h1>PC Pro Manager</h1><p>ניהול מלאי והצעות מחיר | קובי אלפיה</p></div>', unsafe_allow_html=True)

tabs = st.tabs(["📦 ניהול מלאי", "📝 חילוץ נתונים", "📑 סל וייצוא"])

with tabs[0]:
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("#### טעינת אקסל מלאי")
        uploaded_file = st.file_uploader("העלה קובץ XLSX (מלאי מרוכז)", type=["xlsx"])
        
        if uploaded_file:
            try:
                # מנגנון קריאה חסין לשגיאות BadZipFile
                file_bytes = uploaded_file.read()
                try:
                    # ניסיון 1: קריאה ישירה עם מנוע openpyxl
                    df = pd.read_excel(io.BytesIO(file_bytes), engine='openpyxl')
                except:
                    # ניסיון 2: טעינה גולמית דרך openpyxl ואז המרה ל-Dataframe
                    wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
                    sheet = wb.active
                    data = sheet.values
                    cols = next(data)
                    df = pd.DataFrame(data, columns=cols)
                
                st.session_state.inventory = df
                st.success(f"המלאי נטען בהצלחה! ({len(df)} שורות)")
                st.dataframe(df.head(5), use_container_width=True) # תצוגה מקדימה לאישור
            except Exception as e:
                st.error(f"שגיאה קריטית: המערכת לא מצליחה לפתוח את הקובץ.")
                st.warning("הסבר: הקובץ נראה פגום או נעול על ידי אקסל.")
                st.info("פתרון: פתח את הקובץ במחשב, בצע 'שמור בשם' כקובץ XLSX חדש ונסה להעלות שוב.")
            
    with c2:
        st.markdown("#### 🤖 יועץ חומרה")
        query = st.text_input("שאל את המומחה:")
        if st.button("בצע בדיקה") and model:
            inv_ctx = st.session_state.inventory.head(50).to_string() if st.session_state.inventory is not None else "אין מלאי"
            with st.spinner("חושב..."):
                res = model.generate_content(f"Inventory:\n{inv_ctx}\n\nQuestion: {query}")
                st.session_state.ai_chat = res.text
        
        if st.session_state.ai_chat:
            st.markdown(f'<div class="ai-box">{st.session_state.ai_chat}</div>', unsafe_allow_html=True)

    if st.session_state.inventory is not None:
        st.divider()
        search = st.text_input("🔍 חיפוש מהיר:")
        if search:
            df = st.session_state.inventory
            res_df = df[df.apply(lambda r: search.lower() in str(r).lower(), axis=1)]
            st.dataframe(res_df, use_container_width=True)
            
            if not res_df.empty:
                idx = st.selectbox("בחר שורה להוספה:", res_df.index)
                if st.button("➕ הוסף לסל"):
                    row = res_df.loc[idx]
                    st.session_state.cart.append({
                        "status": "מלאי",
                        "description": str(row.iloc[1]) if len(row) > 1 else "פריט",
                        "sku": str(row.iloc[0]),
                        "quantity": 1,
                        "price": format_price(row.iloc[-1])
                    })
                    st.toast("נוסף!")

with tabs[1]:
    st.markdown("#### חילוץ מוצרים ממייל")
    txt = st.text_area("הדבק טקסט חופשי:", height=200)
    if st.button("🚀 חלץ מוצרים") and model and txt:
        with st.spinner("AI עובד..."):
            p = f"Parse to JSON list [{{'description','sku','quantity','price'}}] : {txt}"
            res = model.generate_content(p)
            try:
                data = json.loads(parse_clean_json(res.text))
                for d in data:
                    d['status'] = 'רכש'
                    st.session_state.cart.append(d)
                st.success("הפריטים נוספו לסל!")
            except: st.error("שגיאה בחילוץ - נסה שוב")

with tabs[2]:
    st.markdown("#### סיכום הצעת מחיר")
    if not st.session_state.cart:
        st.info("הסל ריק")
    else:
        for item in st.session_state.cart:
            p_agent = format_price(item.get('price', 0))
            p_cust = round(p_agent * (1 + profit_margin/100), 2)
            st.markdown(f"""
            <div class="cart-item">
                <div><b>{item.get('description')}</b><br><small>מק"ט: {item.get('sku')}</small></div>
                <div class="price-display">${p_cust}</div>
            </div>
            """, unsafe_allow_html=True)
        
        c_a, c_b = st.columns(2)
        with c_a:
            if st.button("🗑️ נקה הכל"):
                st.session_state.cart = []
                st.rerun()
        with c_b:
            xl = export_to_excel(st.session_state.cart, profit_margin)
            st.download_button("📥 הורד אקסל ללקוח", data=xl, file_name=f"Quote_{pd.Timestamp.now().strftime('%d%m%y')}.xlsx")
