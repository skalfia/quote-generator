import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

# הגדרות עמוד רחב
st.set_page_config(page_title="מערכת הצעות מחיר - קובי", layout="wide")

# פונקציה לקריאת אקסל בצורה בטוחה
def load_data(file):
    try:
        # שימוש ב-engine='openpyxl' לקריאת קבצי xlsx מודרניים
        df = pd.read_excel(file, engine='openpyxl')
        # ניקוי שמות עמודות מרווחים מיותרים
        df.columns = df.columns.astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"שגיאה בקריאת הקובץ: {e}")
        return None

# תפריט צד להגדרות
st.sidebar.title("⚙️ הגדרות")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

# ניהול הזיכרון של האפליקציה
if 'cart' not in st.session_state:
    st.session_state.cart = []
if 'inventory_df' not in st.session_state:
    st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מערכת ניהול הצעות מחיר חכמה")

# חלוקת המסך לשני טורים
col_inv, col_quote = st.columns([1, 1])

# --- צד ימין: המחסן (המלאי שלך) ---
with col_inv:
    st.header("🏢 המחסן שלי")
    uploaded_inv = st.file_uploader("טען קובץ מלאי (Excel)", type=["xlsx"])
    
    if uploaded_inv:
        data = load_data(uploaded_inv)
        if data is not None:
            st.session_state.inventory_df = data
            st.success(f"נטענו {len(data)} פריטים בהצלחה")

    if not st.session_state.inventory_df.empty:
        inv = st.session_state.inventory_df
        
        # התאמת שמות העמודות לפי הצילום ששלחת
        col_sku = 'מק"ט'
        col_desc = 'תאור מוצר'
        col_price = 'מחיר קניה'
        
        # יצירת שורת חיפוש
        inv['search_str'] = inv[col_sku].astype(str) + " | " + inv[col_desc].astype(str)
        
        selected = st.selectbox("חפש מוצר במלאי (הקלד שם או מק\"ט):", 
                               options=[""] + inv['search_str'].tolist(),
                               format_func=lambda x: "בחר מוצר..." if x == "" else x)
        
        if selected:
            row = inv[inv['search_str'] == selected].iloc[0]
            st.info(f"**מפרט:** {row[col_desc]}\n\n**מחיר קניה:** ${row[col_price]}")
            
            if st.button("➕ הוסף להצעה", use_container_width=True):
                st.session_state.cart.append({
                    "מק\"ט": row[col_sku],
                    "תיאור": row[col_desc],
                    "מחיר קניה": row[col_price],
                    "מקור": "מלאי מחסן"
                })
                st.toast("המוצר נוסף!")

# --- צד שמאל: עיבוד מיילים מהספקים ---
with col_quote:
    st.header("📧 חילוץ ממייל ספק (AI)")
    email_raw = st.text_area("הדבק כאן את תוכן המייל (C-Data, CMS וכו'):", height=200)
    
    if st.button("🚀 נתח והוסף להצעה", use_container_width=True):
        if not api_key:
            st.warning("נא להזין API Key בתפריט הצד")
        elif not email_raw:
            st.warning("נא להדביק טקסט מהמייל")
        else:
            with st.spinner("ה-AI מנתח את המייל..."):
                prompt = f"""
                You are a product manager assistant. Extract products from the following email text.
                Return ONLY a JSON list of objects with these keys: "sku", "description", "price".
                If price is in USD, return only the number.
                Text: {email_raw}
                """
                try:
                    response = model.generate_content(prompt)
                    clean_txt = response.text.replace('```json', '').replace('```', '').strip()
                    new_items = json.loads(clean_txt)
                    
                    for item in new_items:
                        st.session_state.cart.append({
                            "מק\"ט": item.get('sku', 'N/A'),
                            "תיאור": item.get('description', 'N/A'),
                            "מחיר קניה": item.get('price', 0),
                            "מקור": "ספק חיצוני"
                        })
                    st.success("המוצרים חולצו בהצלחה!")
                except Exception as e:
                    st.error(f"שגיאה בניתוח ה-AI: {e}")

# --- חלק תחתון: ריכוז הצעת המחיר ---
st.divider()
if st.session_state.cart:
    st.header("📄 הצעת המחיר למנהל התיקים")
    df_cart = pd.DataFrame(st.session_state.cart)
    
    # הגדרת רווח
    margin = st.slider("אחוז רווח מבוקש (%)", 0, 10, 10)
    df_cart['מחיר ללקוח'] = df_cart['מחיר קניה'].apply(lambda x: round(float(x) * (1 + margin/100), 2))
    
    # הצגת הטבלה
    st.dataframe(df_cart[['מק\"ט', 'תיאור', 'מחיר ללקוח', 'מקור']], use_container_width=True)
    
    col1, col2 = st.columns(2)
    with col1:
        # הורדה לאקסל
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_cart.to_excel(writer, index=False, sheet_name='הצעת מחיר')
        
        st.download_button(
            label="📥 הורד אקסל מוכן לשליחה",
            data=output.getvalue(),
            file_name="Customer_Quote.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    
    with col2:
        if st.button("🗑️ נקה הצעת מחיר", use_container_width=True):
            st.session_state.cart = []
            st.rerun()
else:
    st.info("הצעת המחיר ריקה כרגע. הוסף מוצרים מהמחסן או ממייל ספק.")
