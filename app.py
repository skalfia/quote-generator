import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json
import PyPDF2

# הגדרות עמוד רחב ומראה נקי
st.set_page_config(page_title="ניהול מלאי והצעות מחיר חכמות - קובי", layout="wide")

# פונקציה לטעינת אקסל חסינה לשגיאות עיצוב
def load_inventory(file):
    try:
        # קריאת הנתונים בלבד ללא עיצובים (מונע שגיאות Fill/Styles)
        df = pd.read_excel(file, engine='openpyxl')
        # ניקוי רווחים משמות העמודות
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"שגיאה בקריאת הקובץ: {e}")
        return None

# פונקציה לחילוץ טקסט מקובץ PDF
def extract_text_from_pdf(pdf_file):
    try:
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        st.error(f"שגיאה בקריאת ה-PDF: {e}")
        return None

# הגדרת ה-AI בתפריט הצד
st.sidebar.title("🛠️ הגדרות מערכת")
api_key = st.sidebar.text_input("הכנס Google API Key:", type="password")

# אתחול המודל רק אם יש מפתח
model = None
if api_key:
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        st.sidebar.error(f"שגיאה בחיבור ל-API: {e}")

# ניהול הזיכרון (Session State)
if 'cart' not in st.session_state:
    st.session_state.cart = []
if 'inventory_df' not in st.session_state:
    st.session_state.inventory_df = pd.DataFrame()

st.title("📦 מערכת ניהול הצעות מחיר חכמה")

# חלוקה לטורים רחבים
col_inv, col_quote = st.columns([1, 1])

# --- צד ימין: המחסן ושורת חיפוש ---
with col_inv:
    st.subheader("🏢 המחסן שלי")
    uploaded_inv = st.file_uploader("1. טען קובץ מלאי מעודכן (XLSX)", type=["xlsx"])
    
    if uploaded_inv:
        df = load_inventory(uploaded_inv)
        if df is not None:
            st.session_state.inventory_df = df
            st.success(f"נטענו {len(df)} פריטים מהמלאי")

    if not st.session_state.inventory_df.empty:
        inv = st.session_state.inventory_df
        
        # מיפוי עמודות לפי הצילום ששלחת
        col_sku = 'מק"ט'
        col_desc = 'תאור מוצר'
        col_price = 'מחיר קניה'
        
        # יצירת שורת חיפוש משולבת
        inv['display'] = inv[col_sku].astype(str) + " | " + inv[col_desc].astype(str)
        
        st.write("---")
        search_query = st.selectbox(
            "🔍 חפש מוצר במלאי (לחיפוש מהיר):",
            options=[""] + inv['display'].tolist(),
            format_func=lambda x: "התחל להקליד לחיפוש..." if x == "" else x
        )
        
        if search_query:
            selected_row = inv[inv['display'] == search_query].iloc[0]
            
            # תצוגת פרטי מוצר נבחר
            with st.container(border=True):
                st.write(f"**מק\"ט:** {selected_row[col_sku]}")
                st.write(f"**תיאור:** {selected_row[col_desc]}")
                st.write(f"**יתרה במחסן:** {selected_row.get('יתרה מחסני', 'לא צוין')}")
                st.markdown(f"### מחיר קניה: ${selected_row[col_price]}")
                
                if st.button("➕ הוסף מהמלאי להצעת המחיר", use_container_width=True):
                    st.session_state.cart.append({
                        "מק\"ט": selected_row[col_sku],
                        "תיאור": selected_row[col_desc],
                        "מחיר קניה": selected_row[col_price],
                        "מקור": "מלאי פנימי"
                    })
                    st.toast("המוצר נוסף לסל!")

# --- צד שמאל: עיבוד מיילים מהספקים ---
with col_quote:
    st.subheader("📧 חילוץ ממייל/קובץ ספק (AI)")
    
    # אפשרות גרירת קבצים
    uploaded_supplier_file = st.file_uploader("2. גרור קובץ הצעת ספק (PDF או TXT)", type=["pdf", "txt"])
    
    # אפשרות הדבקת טקסט (כגיבוי)
    email_text_pasted = st.text_area("או הדבק כאן את תוכן המייל:", height=150, placeholder="הדבק כאן את רשימת המוצרים והמחירים...")
    
    # קביעת הטקסט לעיבוד
    final_text_to_process = ""
    if uploaded_supplier_file:
        if uploaded_supplier_file.type == "application/pdf":
            final_text_to_process = extract_text_from_pdf(uploaded_supplier_file)
        else: # txt
            final_text_to_process = uploaded_supplier_file.read().decode('utf-8')
    elif email_text_pasted:
        final_text_to_process = email_text_pasted

    if st.button("🚀 נתח נתונים והוסף", use_container_width=True):
        if not model:
            st.error("נא להזין API Key בתפריט הצד")
        elif not final_text_to_process:
            st.warning("נא לגרור קובץ או להדביק טקסט לעיבוד")
        else:
            with st.spinner("ה-AI מנתח את הנתונים..."):
                try:
                    # פרומפט משופר לקבלת JSON נקי
                    prompt = f"""
                    Identify products, SKUs, and prices from this text.
                    Return ONLY a JSON list of objects with "sku", "description", and "price".
                    Important: Price must be a number only.
                    Text: {final_text_to_process}
                    """
                    response = model.generate_content(prompt)
                    # ניקוי פורמט ה-Markdown מהתשובה
                    raw_res = response.text.replace('```json', '').replace('```', '').strip()
                    items = json.loads(raw_res)
                    
                    for item in items:
                        st.session_state.cart.append({
                            "מק\"ט": item.get('sku', 'N/A'),
                            "תיאור": item.get('description', 'N/A'),
                            "מחיר קניה": item.get('price', 0),
                            "מקור": "ספק חיצוני"
                        })
                    st.success(f"חולצו {len(items)} מוצרים בהצלחה!")
                except Exception as e:
                    st.error(f"שגיאה בניתוח הנתונים: {e}")

# --- חלק תחתון: ריכוז וייצוא הצעת המחיר ---
st.divider()
if st.session_state.cart:
    st.header("📄 הצעת המחיר המתגבשת")
    
    # ניהול רווח
    margin = st.slider("אחוז רווח מבוקש (%)", 0, 20, 10)
    
    # השוואת מחירים (לוגיקה)
    inventory_skus = []
    if not st.session_state.inventory_df.empty:
        # מיפוי עמודות
        col_sku_inv = 'מק"ט'
        col_price_inv = 'מחיר קניה'
        # יצירת מילון חיפוש מהיר למק"טים
        st.session_state.inventory_df[col_sku_inv] = st.session_state.inventory_df[col_sku_inv].astype(str)
        inventory_skus = st.session_state.inventory_df[col_sku_inv].tolist()
        inventory_prices = dict(zip(st.session_state.inventory_df[col_sku_inv], st.session_state.inventory_df[col_price_inv]))

    # הצגת הטבלה בצורה דינמית עם התראות
    indices_to_remove = []
    for i, item in enumerate(st.session_state.cart):
        sku = str(item['מק"ט'])
        cost_price = round(float(str(item['מחיר קניה']).replace('$','')), 2)
        customer_price = round(cost_price * (1 + margin/100), 2)
        source = item['מקור']
        description = item['תיאור']

        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 2, 1])
            
            # טור 1: פרטי מוצר
            with col1:
                st.write(f"**{description}**")
                st.write(f"מק\"ט: {sku} | מקור: {source}")
            
            # טור 2: מחיר סופי
            with col2:
                st.markdown(f"### מחיר ללקוח: ${customer_price}")
            
            # טור 3: כפתור מחיקה
            with col3:
                if st.button("🗑️ מחק", key=f"remove_{i}"):
                    indices_to_remove.append(i)

            # לוגיקת השוואת מחירים (אם המוצר מהספק)
            if source == "ספק חיצוני" and inventory_skus and sku in inventory_skus:
                inv_cost = inventory_prices[sku]
                if inv_cost < cost_price:
                    st.warning(f"💡 שים לב! המוצר קיים במלאי המחסן שלך. מחיר קניה ספק: ${cost_price}, מחיר קניה מחסן: ${inv_cost}.")
                else:
                    st.info(f"💡 המוצר קיים במלאי המחסן שלך, אך מחיר הספק זול יותר.")
    
    # ביצוע מחיקות (אם היו)
    if indices_to_remove:
        for index in sorted(indices_to_remove, reverse=True):
            del st.session_state.cart[index]
        st.rerun()

    # יצירת אקסל להורדה
    st.write("---")
    df_final_export = pd.DataFrame(st.session_state.cart)
    if not df_final_export.empty:
        df_final_export['מחיר ללקוח'] = df_final_export['מחיר קניה'].apply(lambda x: round(float(str(x).replace('$','')) * (1 + margin/100), 2))
        
        c1, c2 = st.columns(2)
        with c1:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_final_export[['מק\"ט', 'תיאור', 'מחיר ללקוח', 'מקור']].to_excel(writer, index=False, sheet_name='הצעת מחיר')
            
            st.download_button(
                label="📥 הורד אקסל למנהל תיק לקוח",
                data=output.getvalue(),
                file_name="Customer_Quote.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with c2:
            if st.button("🗑️ נקה הכל", use_container_width=True):
                st.session_state.cart = []
                st.rerun()
else:
    st.info("הצעת המחיר ריקה. חפש מוצרים במלאי או טען קובץ ספק.")
