import streamlit as st
import pandas as pd
import requests
import gspread
from google.oauth2.service_account import Credentials

# 페이지 설정
st.set_page_config(page_title="비밀 실험실: 아이템스카우트", page_icon="🕵️")

# --- 🔐 구글 시트 인증 (비밀 설정 필요) ---
def get_gspread_client():
    # Streamlit Secrets에 저장된 구글 인증 정보를 가져옵니다
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(credentials)

# --- 🔍 데이터 분석 로직 (팀장님의 기존 코드 기반) ---
def run_item_scout(keyword):
    # 여기에 팀장님이 코랩에서 쓰시던 아이템스카우트 수집 로직이 들어갑니다.
    # 예시 데이터 (실제 API/크롤링 코드로 대체 가능)
    result = {
        "키워드": keyword,
        "검색량": "15,200",
        "경쟁강도": "매우 높음",
        "날짜": pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')
    }
    return result

# --- ✍️ 시트에 기록하기 ---
def update_sheet(data):
    try:
        client = get_gspread_client()
        # 시트 URL 또는 ID는 Secrets에 넣어두는 것이 안전합니다.
        sheet = client.open_by_url(st.secrets["SHEET_URL"]).sheet1
        sheet.append_row(list(data.values()))
        return True
    except Exception as e:
        st.error(f"시트 연동 에러: {e}")
        return False

# ================= UI =================
st.title("🕵️ 나만의 아이템 분석기")
st.write("키워드를 입력하면 분석 후 자동으로 구글 시트에 기록됩니다.")

keyword_input = st.text_input("분석할 키워드 입력", placeholder="예: 스칼렛 솔로")

if st.button("🚀 분석 및 시트 전송", type="primary"):
    if not keyword_input:
        st.warning("키워드를 입력해주세요.")
    else:
        with st.spinner("분석 중..."):
            # 1. 분석 수행
            analysis_result = run_item_scout(keyword_input)
            
            # 2. 결과 화면 표시
            st.success(f"'{keyword_input}' 분석 완료!")
            st.json(analysis_result)
            
            # 3. 구글 시트 기록
            if update_sheet(analysis_result):
                st.info("✅ 구글 스프레드시트에 성공적으로 기록되었습니다!")
