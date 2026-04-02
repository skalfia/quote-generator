import streamlit as st
import pandas as pd
import json
import re
import io
import google.generativeai as genai
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# --- Page Config ---
st.set_page_config(
    page_title="PC Pro Manager",
    page_icon="💻",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS (The Green Theme) ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@400;600;700;800&display=swap');
:root {
    --bg-primary: #0a0f0a; --bg-secondary: #0f1a0f; --bg-card: #111c11;
    --green-dim: #1a3a1a; --green-mid: #2d6a2d; --green-bright: #3a9c3a;
    --green-neon: #4dbb4d; --green-light: #7ed87e; --text-primary: #e8f5e8;
    --border: #1e3a1e; --border-bright: #2d6a2d;
}
html, body, [class*="css"] { font-family: 'Syne', sans-serif !important; background-color: var(--bg-primary) !important; color: var(--text-primary) !important; }
.stApp { background: linear-gradient(135deg, #0a0f0a 0%, #0d160d 50%, #0a0f0a 100%) !important; }
[data-testid="stSidebar"] { background: var(--bg-secondary) !important; border-right: 1px solid var(--border) !important; }
.main-header { background: linear-gradient(90deg, var(--bg-card) 0%, var(--green-dim) 100%); border: 1px solid var(--border-bright); border-radius: 12px; padding: 24px; margin-bottom: 24px; }
.main-header h1 { color: var(--green-neon) !important; font-weight: 800 !important; margin: 0 !important; }
.stTabs [data-baseweb="tab-list"] { background: var(--bg-secondary) !important; border-radius: 10px !important; padding: 4px !important; }
.stTabs [aria-selected="true"] { background: var(--green-mid) !important; }
.ai-response { background: linear-gradient(135deg, var(--bg-card), var(--green-dim)); border: 1px solid var(--border-bright); border-radius: 12px; padding: 20px; margin-top: 12px; }
.cart-item { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; }
.price-display { font-family: 'JetBrains Mono', monospace; color: var(--green-neon); font-weight: 600; font-size: 1.1rem; }
.tag { background: var(--green-dim); color: var(--green-light); border: 1px solid var(--green-mid); border-radius: 4px; padding: 2px 8px; font-size: 0.75rem; margin-left: 10px; }
</style>
""", unsafe_allow_html=True)

# --- Initialization ---
if "inventory_df" not in st.session_state: st.session_state.inventory_df = None
if "cart" not in st.session_state: st.session_state.cart = []
if "ai_response" not in st.session_state: st.session_state.ai_response = ""

# --- Helper Functions ---
def clean_json_from_ai(text):
    text = re.sub(r"
http://googleusercontent.com/immersive_entry_chip/0

**קובי, זה הקוד הכי יציב שיכול להיות.** הוא כולל את העיצוב הירוק, את "יועץ החומרה", את חילוץ המיילים ואת הורדת האקסל המסודר. 

תעדכן את ה-`app.py` שלך ב-GitHub, תעשה "Reboot App" ב-Streamlit, ואתה באוויר!
