import streamlit as st
import pandas as pd
import json
import re
import io
import google.generativeai as genai
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

# הגדרות דף
st.set_page_config(
    page_title="PC Pro Manager",
    page_icon="💻",
    layout="wide",
    initial_sidebar_state="expanded",
)

# עיצוב CSS מתקדם - ירוק כהה מקצועי
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

/* כותרת ראשית */
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
    font-size: 2.5rem !important;
}

/* כרטיסי מוצרים בסל */
.cart-item {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-right: 4px solid var(--green-neon);
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.price-tag {
    font-family: 'JetBrains Mono', monospace;
    color: var(--green-neon);
    font-weight: 600;
    font-size: 1.2rem;
}

/* טאבים */
.stTabs [data-baseweb="tab-list"] {
    background: var(--bg-secondary) !important;
    border-radius: 10px !important;
}

.stTabs [aria-selected="true"] {
    background: var(--green-bright) !important;
    color: white !important;
}

/* יועץ AI */
.ai-box {
    background: rgba(77, 187, 77, 0.05);
    border: 1px dashed var(--green-bright);
    border-radius: 12px;
    padding: 20px;
    margin-top: 15px;
}
</style>
""", unsafe_allow_html=True)

# אתחול משתני מערכת
if "inventory_df" not in st.session_state: st.session_state.inventory_df = None
if "cart" not in st.session_state: st.session_state.cart = []
if "ai_advisor_res" not in st.session_state: st.session_state.ai_advisor_res = ""

# פונקציות עזר
def clean_ai_json(text):
    """מחלץ JSON נקי מתשובת ה-AI"""
    text = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()
    match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
    return match.group(1) if match else text

def parse_price(val):
    try:
        if isinstance(val, (int, float)): return float(val)
        return float(re.sub(r'[^\d.]', '', str(val)))
    except: return 0.0

def generate_excel(cart, margin_pct):
    """יוצר קובץ אקסל מעוצב RTL"""
    wb = Workbook()
    ws = wb.active
    ws.title = "הצעת מחיר"
    ws.sheet_view.rightToLeft = True
    
    headers = ["סטטוס", "תיאור מוצר", "מק\"ט / CONFIG", "כמות", "מחיר סוכן", "מחיר ללקוח", "סה\"כ"]
    ws.append(headers)
    
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2D6A2D", end_color="2D6A2D", fill_type="solid")
    
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for item in cart:
        p_agent = float(item.get('price', 0))
        p_cust = round(p_agent * (1 + margin_pct/100), 2)
        qty = int(item.get('quantity', 1))
        ws.append([
            item.get('status', 'רכש'),
            item.get('description', ''),
            item.get('sku', ''),
            qty,
            p_agent,
            p_cust,
            p_cust * qty
        ])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

# סרגל צד
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2991/2991148.png", width=80)
    st.title("הגדרות מערכת")
    api_key = st.text_input("Gemini API Key", type="password", help="הכנס מפתח מ-Google AI Studio")
    margin = st.slider("מתח רווח ללקוח (%)", 0, 100, 15)
    
    model = None
    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            st.success("AI מחובר בהצלחה")
        except: st.error("שגיאה במפתח ה-API")

# גוף האפליקציה
st.markdown('<div class="main-header"><h1>PC Pro Manager</h1><p>מערכת חכמה לבניית הצעות מחיר וניהול מלאי</p></div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["🏢 ניהול מלאי ויועץ חומרה", "📧 חילוץ ממיילים", "🛒 סל מוצרים וייצוא"])

with tab1:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("טעינת מלאי")
        up_file = st.file_uploader("העלה אקסל מחסן", type=["xlsx"])
        if up_file:
            st.session_state.inventory_df = pd.read_excel(up_file)
            st.success(f"נטענו {len(st.session_state.inventory_df)} פריטים")
            
    with col2:
        st.subheader("🤖 יועץ חומרה חכם")
        q = st.text_input("שאל שאלה טכנית (למשל: איזה זיכרון מתאים ל-HP 400 G9?):")
        if st.button("שאל את המכונה") and model and q:
            with st.spinner("מנתח תאימות..."):
                inv_text = st.session_state.inventory_df.head(100).to_string() if st.session_state.inventory_df is not None else "אין מלאי טעון"
                prompt = f"You are a PC expert. Based on this inventory: {inv_text}. Answer this: {q}"
                res = model.generate_content(prompt)
                st.session_state.ai_advisor_res = res.text
        
        if st.session_state.ai_advisor_res:
            st.markdown(f'<div class="ai-box"><b>תשובה:</b><br>{st.session_state.ai_advisor_res}</div>', unsafe_allow_html=True)

    if st.session_state.inventory_df is not None:
        st.divider()
        search = st.text_input("🔍 חיפוש מהיר במלאי (מק\"ט או תיאור):")
        if search:
            results = st.session_state.inventory_df[st.session_state.inventory_df.apply(lambda r: search.lower() in str(r).lower(), axis=1)]
            st.dataframe(results, use_container_width=True)
            
            sel_sku = st.selectbox("בחר פריט להוספה:", [""] + results.iloc[:,0].astype(str).tolist())
            if sel_sku and st.button("➕ הוסף לסל מהמלאי"):
                match = results[results.iloc[:,0].astype(str) == sel_sku].iloc[0]
                st.session_state.cart.append({
                    "status": "מלאי", "description": match[1], "sku": match[0],
                    "quantity": 1, "price": parse_price(match[-1])
                })
                st.toast("התווסף בהצלחה")

with tab2:
    st.subheader("חילוץ נתונים מטקסט חופשי")
    pasted_text = st.text_area("הדבק כאן תוכן של מייל או רשימת ספק:", height=250)
    if st.button("🚀 חלץ מוצרים עם AI") and model and pasted_text:
        with st.spinner("AI מנתח את הטקסט..."):
            p = f"Extract products to JSON list [{{'description','sku','quantity','price'}}] from: {pasted_text}"
            res = model.generate_content(p)
            try:
                data = json.loads(clean_ai_json(res.text))
                for d in data:
                    d['status'] = 'רכש'
                    st.session_state.cart.append(d)
                st.success(f"חולצו {len(data)} פריטים!")
            except: st.error("ה-AI לא החזיר פורמט תקין. נסה שוב.")

with tab3:
    st.subheader("🛒 ריכוז הצעת מחיר")
    if not st.session_state.cart:
        st.info("הסל שלך ריק כרגע.")
    else:
        for i, item in enumerate(st.session_state.cart):
            p_agent = float(item.get('price', 0))
            p_customer = round(p_agent * (1 + margin/100), 2)
            st.markdown(f"""
            <div class="cart-item">
                <div>
                    <b>{item.get('description', 'ללא תיאור')}</b><br>
                    <small>מק"ט: {item.get('sku', '---')} | סטטוס: {item.get('status', 'רכש')}</small>
                </div>
                <div class="price-tag">${p_customer}</div>
            </div>
            """, unsafe_allow_html=True)
            
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("🗑️ נקה הכל"):
                st.session_state.cart = []
                st.rerun()
        with col_b2:
            excel_file = generate_excel(st.session_state.cart, margin)
            st.download_button(
                label="📥 הורד אקסל ללקוח",
                data=excel_file,
                file_name=f"Quote_Kobi_{pd.Timestamp.now().strftime('%d%m%y')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
