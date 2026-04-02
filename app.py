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

.metric-label {
    font-size: 0.85rem;
    color: #888;
}

.metric-value {
    font-weight: bold;
    font-size: 1rem;
}
</style>
""", unsafe_allow_html=True)

# --- ניהול State ---
if "inventory" not in st.session_state: st.session_state.inventory = None
if "cart" not in st.session_state: st.session_state.cart = []

# --- פונקציות עזר ---
def format_num(val):
    try:
        if pd.isna(val): return 0.0
        if isinstance(val, (int, float)): return float(val)
        cleaned = re.sub(r'[^\d.-]', '', str(val))
        return float(cleaned) if cleaned else 0.0
    except: return 0.0

def find_column(df, possible_names):
    """מוצא עמודה לפי רשימת שמות אפשריים תוך התעלמות מרווחים"""
    for col in df.columns:
        clean_col = str(col).strip().replace(" ", "")
        for target in possible_names:
            if clean_col == target.replace(" ", ""):
                return col
    return None

def export_to_excel(cart_data, margin):
    wb = Workbook()
    ws = wb.active
    ws.title = "הצעת מחיר"
    ws.sheet_view.rightToLeft = True
    headers = ["תיאור פריט", "מק\"ט", "כמות", "מחיר ללקוח", "סה\"כ"]
    ws.append(headers)
    
    fill = PatternFill(start_color="1A3A1A", end_color="1A3A1A", fill_type="solid")
    font = Font(bold=True, color="4DBB4D")
    for cell in ws[1]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center")

    for item in cart_data:
        p_cust = round(format_num(item.get('price', 0)) * (1 + margin/100), 2)
        qty = int(item.get('quantity', 1))
        ws.append([item.get('description', ''), item.get('sku', ''), qty, p_cust, p_cust * qty])
    
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

# --- ממשק ---
st.markdown('<div class="main-header"><h1>PC Pro Manager</h1></div>', unsafe_allow_html=True)

tabs = st.tabs(["🔍 חיפוש במלאי", "🛒 סל והצעה"])

with tabs[0]:
    c1, c2 = st.columns([1, 2])
    with c1:
        uploaded_file = st.file_uploader("טען אקסל מלאי משפחה מרוכזת", type=["xlsx"])
        if uploaded_file:
            try:
                df = pd.read_excel(uploaded_file, engine='openpyxl')
                st.session_state.inventory = df
                st.success(f"נטענו {len(df)} פריטים")
            except Exception as e:
                st.error("שגיאה בטעינת הקובץ.")

    with c2:
        search = st.text_input("חפש מק\"ט או תיאור מוצר:", placeholder="הקלד לחיפוש...")

    if st.session_state.inventory is not None and search:
        df = st.session_state.inventory
        
        # זיהוי עמודות דינמי לפי הדרישות שלך
        col_sku = find_column(df, ["מק'ט", "מקט", "מק\"ט"])
        col_desc = find_column(df, ["תאור מוצר", "תיאור מוצר"])
        col_bal = find_column(df, ["יתרה מחסני מכירה", "יתרה"])
        col_orders = find_column(df, ["הזמנות לקוח"])
        col_purch = find_column(df, ["כמות ברכש"])
        col_price = find_column(df, ["מחיר מוצג לסוכן $", "מחיר סוכן"])
        
        # חיפוש
        res = df[df.apply(lambda r: search.lower() in str(r).lower(), axis=1)]
        
        if not res.empty:
            for idx, row in res.iterrows():
                sku = str(row[col_sku]) if col_sku else "חסר"
                desc = str(row[col_desc]) if col_desc else "חסר"
                
                # חישובים
                v_bal = format_num(row[col_bal]) if col_bal else 0
                v_orders = format_num(row[col_orders]) if col_orders else 0
                v_purch = format_num(row[col_purch]) if col_purch else 0
                v_price = format_num(row[col_price]) if col_price else 0
                
                # לוגיקה: יתרה פחות הזמנות פלוס רכש
                v_total = v_bal - v_orders + v_purch
                
                st.markdown(f"""
                <div class="inventory-item-box">
                    <div style="display: flex; justify-content: space-between;">
                        <div>
                            <span style="font-weight:bold; font-size:1.1rem;">{desc}</span><br>
                            <small>מק"ט: {sku}</small>
                        </div>
                        <div class="price-tag">${v_price}</div>
                    </div>
                    <div style="display: flex; gap: 15px; margin-top: 10px; border-top: 1px solid #1e3a1e; padding-top: 10px;">
                        <div style="flex:1">
                            <div class="metric-label">יתרה במחסן</div>
                            <div class="metric-value">{int(v_bal)}</div>
                        </div>
                        <div style="flex:1">
                            <div class="metric-label">הזמנות לקוח</div>
                            <div class="metric-value" style="color:#ff4b4b">-{int(v_orders)}</div>
                        </div>
                        <div style="flex:1">
                            <div class="metric-label">כמות ברכש</div>
                            <div class="metric-value" style="color:#4d88ff">+{int(v_purch)}</div>
                        </div>
                        <div style="flex:1; background: rgba(77,187,77,0.1); padding: 5px; border-radius:5px; text-align:center;">
                            <div class="metric-label" style="color:var(--green-neon)">סה"כ זמין</div>
                            <div class="available-qty">{int(v_total)}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button(f"➕ הוסף להצעה", key=f"btn_{idx}"):
                    st.session_state.cart.append({
                        "description": desc,
                        "sku": sku,
                        "price": v_price,
                        "quantity": 1
                    })
                    st.toast(f"נוסף: {sku}")
                st.markdown("<br>", unsafe_allow_html=True)

with tabs[1]:
    st.subheader("🛒 פריטים שנבחרו")
    profit_margin = st.slider("מתח רווח ללקוח (%)", 0, 100, 20)
    
    if not st.session_state.cart:
        st.info("הסל ריק")
    else:
        for i, item in enumerate(st.session_state.cart):
            p_agent = item.get('price', 0)
            p_cust = round(p_agent * (1 + profit_margin/100), 2)
            
            c_info, c_del = st.columns([6, 1])
            with c_info:
                st.markdown(f"**{item['description']}** | מחיר ללקוח: **${p_cust}**")
            with c_del:
                if st.button("🗑️", key=f"del_{i}"):
                    st.session_state.cart.pop(i)
                    st.rerun()
        
        st.divider()
        if st.button("נקה סל"):
            st.session_state.cart = []
            st.rerun()
            
        xl_data = export_to_excel(st.session_state.cart, profit_margin)
        st.download_button("📥 הורד הצעת מחיר באקסל", data=xl_data, file_name="PC_Pro_Quote.xlsx")
