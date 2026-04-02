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

.main-header h1 {
    color: var(--green-neon) !important;
    font-weight: 800 !important;
    margin: 0 !important;
}

.inventory-item-box {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 10px;
    transition: all 0.3s ease;
}

.inventory-item-box:hover {
    border-color: var(--green-neon);
    background: rgba(77, 187, 77, 0.05);
}

.status-badge {
    padding: 2px 8px;
    border-radius: 5px;
    font-size: 0.8rem;
    font-weight: bold;
}

.available-qty {
    color: var(--green-neon);
    font-size: 1.1rem;
    font-weight: 800;
}

.price-tag {
    font-family: 'JetBrains Mono', monospace;
    color: #ffd700;
}

.cart-item {
    background: var(--bg-card);
    border-right: 5px solid var(--green-neon);
    padding: 10px;
    margin-bottom: 8px;
    border-radius: 5px;
}
</style>
""", unsafe_allow_html=True)

# --- ניהול State ---
if "inventory" not in st.session_state: st.session_state.inventory = None
if "cart" not in st.session_state: st.session_state.cart = []
if "ai_chat" not in st.session_state: st.session_state.ai_chat = ""

# --- פונקציות עזר ---
def parse_clean_json(text):
    text = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()
    match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
    return match.group(1) if match else text

def format_num(val):
    try:
        if pd.isna(val): return 0
        if isinstance(val, (int, float)): return float(val)
        cleaned = re.sub(r'[^\d.-]', '', str(val))
        return float(cleaned) if cleaned else 0
    except: return 0

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
        agent_p = format_num(item.get('price', 0))
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
    profit_margin = st.slider("מתח רווח ללקוח (%)", 0, 100, 20)
    
    model = None
    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            st.success("AI מוכן")
        except: st.error("Key Error")

# --- גוף האפליקציה ---
st.markdown('<div class="main-header"><h1>PC Pro Manager</h1></div>', unsafe_allow_html=True)

tabs = st.tabs(["📦 מלאי וחיפוש פריטים", "📝 חילוץ נתונים חכם", "📑 סל וייצוא הצעת מחיר"])

with tabs[0]:
    col_up1, col_up2 = st.columns([1, 1])
    with col_up1:
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
                st.success(f"נטענו {len(df)} שורות מוצרים")
            except Exception as e:
                st.error("שגיאה בטעינה. וודא שהקובץ תקין.")

    with col_up2:
        query = st.text_input("🤖 יועץ חומרה:")
        if st.button("שאל את המערכת") and model:
            inv_ctx = st.session_state.inventory.head(30).to_string() if st.session_state.inventory is not None else "אין מלאי"
            with st.spinner("מנתח..."):
                res = model.generate_content(f"Inventory:\n{inv_ctx}\n\nQuestion: {query}")
                st.session_state.ai_chat = res.text
        if st.session_state.ai_chat:
            st.info(st.session_state.ai_chat)

    if st.session_state.inventory is not None:
        st.divider()
        search = st.text_input("🔍 חיפוש פריט (מק\"ט, תיאור או משפחה):", placeholder="למשל: DDR5, HP, 5600...")
        
        if search:
            df = st.session_state.inventory
            # חיפוש חופשי בכל העמודות
            res_df = df[df.apply(lambda r: search.lower() in str(r).lower(), axis=1)]
            
            if not res_df.empty:
                st.write(f"נמצאו {len(res_df)} פריטים רלוונטיים:")
                
                for idx, row in res_df.iterrows():
                    # הנחת עמודות לפי הגיון אקסל נפוץ (0: מק"ט, 1: תיאור, 2: מלאי, 3: הזמנות רכש, אחרון: מחיר)
                    sku = str(row.iloc[0])
                    name = str(row.iloc[1])
                    curr_stock = format_num(row.iloc[2]) if len(row) > 2 else 0
                    po_stock = format_num(row.iloc[3]) if len(row) > 3 else 0
                    price = format_num(row.iloc[-1])
                    
                    # לוגיקה: מלאי זמין = מלאי נוכחי + הזמנות רכש
                    available = curr_stock + po_stock
                    
                    with st.container():
                        st.markdown(f"""
                        <div class="inventory-item-box">
                            <div style="display: flex; justify-content: space-between; align-items: start;">
                                <div>
                                    <span style="font-weight: 800; font-size: 1.1rem;">{name}</span><br>
                                    <small>מק"ט: {sku}</small>
                                </div>
                                <div style="text-align: left;">
                                    <span class="price-tag">${price}</span>
                                </div>
                            </div>
                            <div style="margin-top: 10px; display: flex; gap: 20px;">
                                <div>📦 מלאי נוכחי: <b>{int(curr_stock)}</b></div>
                                <div>🚚 בדרך (PO): <b>{int(po_stock)}</b></div>
                                <div>✅ זמין למכירה: <span class="available-qty">{int(available)}</span></div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if st.button(f"➕ הוסף להצעה", key=f"add_{idx}"):
                            st.session_state.cart.append({
                                "status": "מלאי" if curr_stock > 0 else "רכש",
                                "description": name,
                                "sku": sku,
                                "quantity": 1,
                                "price": price
                            })
                            st.toast(f"נוסף: {sku}")
                        st.markdown("<br>", unsafe_allow_html=True)
            else:
                st.warning("לא נמצאו תוצאות לחיפוש זה.")

with tabs[1]:
    st.subheader("חילוץ מוצרים מרשימה גולמית")
    txt = st.text_area("הדבק כאן מייל או רשימה מספק:", height=250)
    if st.button("🚀 בצע חילוץ") and model and txt:
        with st.spinner("AI מנתח..."):
            p = f"Parse this to JSON list [{{'description','sku','quantity','price'}}] : {txt}"
            res = model.generate_content(p)
            try:
                data = json.loads(parse_clean_json(res.text))
                for d in data:
                    d['status'] = 'רכש'
                    st.session_state.cart.append(d)
                st.success("חולץ בהצלחה!")
            except: st.error("חילוץ נכשל.")

with tabs[2]:
    st.subheader("🛒 ריכוז פריטים להצעה")
    if not st.session_state.cart:
        st.info("הסל ריק. חפש מוצרים במלאי או חלץ נתונים כדי להתחיל.")
    else:
        for i, item in enumerate(st.session_state.cart):
            p_agent = format_num(item.get('price', 0))
            p_cust = round(p_agent * (1 + profit_margin/100), 2)
            
            c_info, c_del = st.columns([6, 1])
            with c_info:
                st.markdown(f"""
                <div class="cart-item">
                    <b>{item.get('description')}</b> ({item.get('sku')})<br>
                    מחיר ללקוח: <span style="color:#4dbb4d; font-weight:bold;">${p_cust}</span> | סטטוס: {item.get('status')}
                </div>
                """, unsafe_allow_html=True)
            with c_del:
                if st.button("🗑️", key=f"del_{i}"):
                    st.session_state.cart.pop(i)
                    st.rerun()
        
        st.divider()
        c_c, c_d = st.columns(2)
        with c_c:
            if st.button("מחיקת כל הסל"):
                st.session_state.cart = []
                st.rerun()
        with c_d:
            xl_file = export_to_excel(st.session_state.cart, profit_margin)
            st.download_button("📥 ייצא אקסל להצעת מחיר", data=xl_file, file_name="Quote_PC_Pro.xlsx")
