import streamlit as st
import os
import sys

def setup(title, icon="🏈", layout="wide"):
    st.set_page_config(page_title=title, page_icon=icon, layout=layout)
    st.title(f"{icon} {title}")

    pages_dir = os.path.join(os.path.dirname(__file__), "pages")
    if os.path.basename(os.path.dirname(os.path.abspath(sys.argv[0]))) == "pages" or True:
        app_dir = os.path.dirname(__file__)
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)

    st.markdown("""
        <style>
            .stApp { font-size: 15px; }
            .stMarkdown p { font-size: 15px; line-height: 1.6; }
            .stMarkdown h3 { font-size: 22px; }
            .stMarkdown h2 { font-size: 26px; }
            section[data-testid="stSidebar"] .stMarkdown p { font-size: 14px; }
            section[data-testid="stSidebar"] { width: 320px; }
            button[data-baseweb="tab"] { font-size: 15px !important; }
            table td, table th,
            [data-testid="stTable"] td, [data-testid="stTable"] th {
                text-align: left !important;
                font-size: 14px !important;
                padding: 6px 8px !important;
            }
            .stDataFrame td, .stDataFrame th,
            [data-testid="stDataFrame"] td,
            [data-testid="stDataFrame"] th {
                font-size: 14px !important;
            }
            table { line-height: 1.6; }
            .block-container { padding-top: 2rem; padding-bottom: 1rem; }
            div[data-testid="stExpander"] { margin-bottom: 0; }
            .stSelectbox, .stMultiSelect, .stTextInput { margin-bottom: -10px; }
        </style>
    """, unsafe_allow_html=True)
