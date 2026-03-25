import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import PyPDF2

# הגדרות עמוד
st.set_page_config(page_title="ניהול מחסן והצעות מחיר - קובי", layout="wide")

# פונקציות עזר
def load_inventory(file):
    try:
        # פתרון לשגיאת ה-Styles: קוראים רק את הנתונים
        from openpyxl import load_workbook
        wb = load_workbook(file, data_only=True)
        ws = wb.active
        data = ws.values
        cols = next(data)
        df = pd.DataFrame(data, columns=cols)
        # ניקוי רווחים משמות העמודות
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"שגיאה בקריאת האקסל: {e}")
        return None

def extract_text_from_pdf(pdf_file):
    try:
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        st.error(f"שגיאה בקריאת ה-PDF: {e}")
        return None

# הגדרת ה-AI בתפריט הצד
st.sidebar.title("🛠️ הגדרות")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")

model = None
if api_key:
    try:
        genai.configure(api_key=api_key)
        # שינוי למודל ה-Pro שעובד ב-100% מהמקרים
        model = genai.GenerativeModel('gemini-pro')
    except Exception as e:
        st.sidebar.error(f"שגיאה בחיבור ל-API: {e}")

# ניהול הזיכרון
if 'cart' not in st.session_state:
    st.session_state.cart = []
if 'inventory_df' not in st.session_state:
    st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מערכת הצעות מחיר חכמה")

# בדיקת המפתח להודעת אישור
if api_key and model:
    st.sidebar.success("✅ מפתח ה-API מחובר")

col_inv, col_quote = st.columns([1, 1])

# --- צד ימין: המחסן ---
with col_inv:
    st.subheader("🏢 המחסן שלי")
    uploaded_inv = st.file_uploader("1. טען קובץ מלאי (XLSX)", type=["xlsx"])
    
    if uploaded_inv:
        df = load_inventory(uploaded_inv)
        if df is not None:
            st.session_state.inventory_df = df
            st.success(f"נטענו {len(df)} פריטים")

    if not st.session_state.inventory_df.empty:
        inv = st.session_state.inventory_df
        # מיפוי עמודות לפי הצילום שלך
        col_sku = 'מק"ט'
        col_desc = 'תאור מוצר'
        col_price = 'מחיר קניה'
        
        # שורת חיפוש חכמה
        inv['search_tag'] = inv[col_sku].astype(str) + " | " + inv[col_desc].astype(str)
        st.write("---")
        search_val = st.selectbox("🔍 חפש מוצר במלאי:", options=[""] + inv['search_tag'].tolist())
        
        if search_val:
            row = inv[inv['search_tag'] == search_val].iloc[0]
            with st.container(border=True):
                st.write(f"**{row[col_desc]}**")
                st.write(f"מק\"ט: {row[col_sku]}")
                st.markdown(f"### מחיר קניה: ${row[col_price]}")
                if st.button("➕ הוסף להצעה", use_container_width=True):
                    st.session_state.cart.append({
                        "מק\"ט": row[col_sku], "תיאור": row[col_desc],
                        "מחיר קניה": row[col_price], "מקור": "מחסן"
                    })
                    st.toast("נוסף!")

# --- צד שמאל: ספקים ---
with col_quote:
    st.subheader("📧 חילוץ מהצעה (PDF/מייל)")
    supplier_file = st.file_uploader("2. גרור קובץ PDF מהספק:", type=["pdf"])
    pasted_text = st.text_area("או הדבק כאן טקסט מהמייל:", height=100)
    
    input_text = ""
    if supplier_file:
        input_text = extract_text_from_pdf(supplier_file)
    elif pasted_text:
        input_text = pasted_text

    if st.button("🚀 נתח נתונים והוסף", use_container_width=True):
        if not model: st.error("נא להזין API Key")
        elif not input_text: st.warning("אין תוכן לניתוח")
        else:
            with st.spinner("ה-AI מנתח..."):
                try:
                    prompt = f"Return ONLY a JSON list of products with 'sku', 'description', and 'price'. Text: {input_text}"
                    res = model.generate_content(prompt)
                    clean_res = res.text.replace('```json', '').replace('```', '').strip()
                    items = json.loads(clean_res)
                    for item in items:
                        st.session_state.cart.append({
                            "מק\"ט": item.get('sku', 'N/A'), "תיאור": item.get('description', 'N/A'),
                            "מחיר קניה": item.get('price', 0), "מקור": "ספק"
                        })
                    st.success(f"חולצו {len(items)} פריטים!")
                except Exception as e:
                    st.error(f"שגיאה בניתוח: {e}")

# --- חלק תחתון: ריכוז ---
st.divider()
if st.session_state.cart:
    st.header("📄 הצעת מחיר סופית")
    margin = st.slider("אחוז רווח (%)", 0, 20, 10)
    
    # השוואה למלאי
    inv_data = {}
    if not st.session_state.inventory_df.empty:
        inv_data = dict(zip(st.session_state.inventory_df['מק"ט'].astype(str), st.session_state.inventory_df['מחיר קניה']))

    to_delete = []
    for i, item in enumerate(st.session_state.cart):
        sku = str(item['מק"ט'])
        cost = float(str(item['מחיר קניה']).replace('$',''))
        final_p = round(cost * (1 + margin/100), 2)
        
        with st.container(border=True):
            c1, c2, c3 = st.columns([4, 2, 1])
            with c1:
                st.write(f"**{item['תיאור']}** (מק\"ט: {sku})")
                if item['מקור'] == "ספק" and sku in inv_data:
                    if inv_data[sku] < cost:
                        st.warning(f"⚠️ קיים במחסן שלך ביותר זול! (${inv_data[sku]})")
                    else:
                        st.info(f"💡 קיים גם במחסן שלך (${inv_data[sku]})")
            with c2: st.markdown(f"**מחיר ללקוח: ${final_p}**")
            with c3:
                if st.button("🗑️", key=f"del_{i}"): to_delete.append(i)

    if to_delete:
        for idx in sorted(to_delete, reverse=True): del st.session_state.cart[idx]
        st.rerun()

    # הורדה
    df_exp = pd.DataFrame(st.session_state.cart)
    df_exp['מחיר ללקוח'] = df_exp['מחיר קניה'].apply(lambda x: round(float(str(x).replace('$','')) * (1+margin/100), 2))
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as wr:
        df_exp[['מק"ט', 'תיאור', 'מחיר ללקוח']].to_excel(wr, index=False)
    st.download_button("📥 הורד אקסל מוכן", data=out.getvalue(), file_name="Quote.xlsx", use_container_width=True)
else:
    st.info("הצעת המחיר ריקה. חפש מוצרים במלאי או טען קובץ ספק.")
