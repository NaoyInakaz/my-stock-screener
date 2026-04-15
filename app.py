import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import re
import gspread
from google.oauth2.service_account import Credentials

# ページの設定
st.set_page_config(layout="wide", page_title="My Stock Screener")

def safe_float(val, default_val):
    if pd.isna(val) or val is None or str(val).strip() == "" or str(val).strip() == "-": return default_val
    match = re.search(r'-?\d+\.?\d*', str(val))
    if match: return float(match.group())
    return default_val

def calculate_upside(text):
    try:
        if pd.isna(text) or str(text).strip() == "": return 15.0
        nums = re.findall(r'[\d,]+', str(text))
        if len(nums) >= 2:
            current = float(nums[0].replace(',', ''))
            target = float(nums[-1].replace(',', ''))
            if current > 0 and target > 0:
                return max(5.0, min(((target - current) / current) * 100, 80.0))
        return 15.0
    except: return 15.0

def add_trend_icon(row):
    trend = str(row.get('①トレンド構造', ''))
    name = str(row['銘柄']).split(' ')[-1]
    if '上' in trend: return f"▲ {name}"
    elif '下' in trend: return f"▼ {name}"
    return name

@st.cache_data(ttl=3600)
def load_data():
    SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1oomwgYozZgl9N9etkZkcqennHprrKX4h65VqqlsCV2E/edit"
    
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes
    )
    gc = gspread.authorize(credentials)
    ss = gc.open_by_url(SPREADSHEET_URL)
    
    try:
        sheet_market = ss.worksheet("Market")
        macro_row = sheet_market.get_all_values()[-1] 
        macro_data = {'地合い判定': macro_row[2], 'VIX': safe_float(macro_row[4], 20.0), '日経平均予想PER': safe_float(macro_row[9], 15.0), '理由': macro_row[3]}
    except:
        macro_data = {'地合い判定': '通常', 'VIX': '-', '日経平均予想PER': '-', '理由': 'マクロシート未設定（通常モードで動作中）'}

    sheet_stock = ss.worksheet("StockCheck")
    df_all = pd.DataFrame(sheet_stock.get_all_records())
    latest_date = df_all['日付'].iloc[-1]
    df = df_all[df_all['日付'] == latest_date].copy()
    
    return macro_data, df, latest_date

# UI表示
st.title("📈 真・投資定点スクリーナー")

try:
    with st.spinner("最新データを取得中..."):
        macro_data, df, latest_date = load_data()
        
    st.markdown(f"**基準日:** {latest_date} | **マクロ判定:** `{macro_data['地合い判定']}`")
    st.caption(f"判定理由: {macro_data['理由']}")
    
    if not df.empty:
        MAX_PER, MAX_ROE, MIN_ROE = 80, 35, -15
        df['PER_num'] = df['PER'].apply(lambda x: safe_float(x, np.nan))
        df['ROE_num'] = df['ROE'].apply(lambda x: safe_float(x, np.nan))
        df['PER_viz'] = df['PER_num'].fillna(0).clip(lower=0, upper=MAX_PER)
        df['ROE_viz'] = df['ROE_num'].fillna(MIN_ROE).clip(lower=MIN_ROE, upper=MAX_ROE)
        df['アップサイド(%)'] = df.get('④株価 / 目標株価', pd.Series(['']*len(df))).apply(calculate_upside).fillna(15.0)
        df['表示名'] = df.apply(add_trend_icon, axis=1)

        def build_hover(row):
            return (f"<b>{row['銘柄']}</b><br>PER: {row['PER']} / ROE: {row['ROE']}<br>アクション: {row.get('💡総合投資アクション', '不明')}")
        df['ホバー情報'] = df.apply(build_hover, axis=1)

        bg_colors = {'通常': '#f8f9fa', '注意': '#fffdf0', '警戒': '#fff5f5'}
        current_bg = next((color for key, color in bg_colors.items() if key in macro_data['地合い判定']), '#ffffff')

        fig = px.scatter(
            df, x="PER_viz", y="ROE_viz", size="アップサイド(%)", color="💡総合投資アクション", 
            hover_name="ホバー情報", text="表示名",
            labels={'PER_viz': '割安度 (PER)', 'ROE_viz': '稼ぐ力 (ROE)'},
            color_discrete_map={
                '買い': '#00CC96', '買い (強気)': '#00CC96', '打診買い': '#636EFA', '打診買い (少額)': '#636EFA', 
                '様子見': '#FECB52', '売り': '#EF553B', '売り (利確・損切り)': '#EF553B'
            },
            range_x=[-5, MAX_PER + 5], range_y=[MIN_ROE - 5, MAX_ROE + 5]
        )
        fig.add_shape(type="rect", x0=0, y0=10, x1=15, y1=MAX_ROE + 5, fillcolor="rgba(0, 255, 0, 0.05)", line_width=0, layer="below")
        fig.update_traces(textposition='top center', selector=dict(type='scatter'))
        fig.update_layout(plot_bgcolor=current_bg, paper_bgcolor=current_bg, height=700)
        
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"エラー詳細: {e}")
