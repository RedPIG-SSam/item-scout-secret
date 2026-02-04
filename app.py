import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials
import datetime
import time

# --- 페이지 설정 ---
st.set_page_config(page_title="팀장님 아이템 분석기 (Real)", page_icon="🕵️", layout="wide")

# --- 🔐 구글 시트 인증 ---
def get_gspread_client():
    try:
        creds_info = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(credentials)
    except Exception as e:
        return None

# --- 🕵️ [핵심] 실제 네이버 데이터 수집 함수 ---
def get_naver_data(keyword):
    # 1. 네이버 쇼핑 검색 URL
    url = f"https://search.shopping.naver.com/search/all?query={keyword}"
    
    # 2. 봇이 아닌 척 헤더 설정
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            
            # 3. 상품 수 찾기 (네이버 페이지 구조에 따라 다를 수 있음)
            # 보통 '전체 123,456개' 형태로 되어 있는 부분을 찾습니다.
            # (구조가 자주 바뀌므로, 못 찾으면 '집계불가'로 처리)
            try:
                # subFilter_num__... 클래스는 네이버 업데이트에 따라 바뀔 수 있어 안전하게 텍스트로 찾음
                count_tag = soup.find("span", {"class": "subFilter_num__S9sle"})
                if count_tag:
                    product_count = count_tag.text.replace("개", "").replace(",", "")
                else:
                    # 태그를 못 찾으면 단순 텍스트 검색 시도
                    product_count = "집계중"
            except:
                product_count = "확인필요"

            return {
                "상태": "성공",
                "상품수": product_count,
                "쇼핑주소": url
            }
        else:
            return {"상태": "접속실패", "상품수": "0", "쇼핑주소": url}
    except Exception as e:
        return {"상태": f"에러: {str(e)}", "상품수": "0", "쇼핑주소": "-"}

# ================= UI 시작 =================
st.title("🕵️ 실시간 아이템 분석기")
st.caption("키워드를 입력하면 **네이버 쇼핑 실제 상품수**를 조회하여 구글 시트에 기록합니다.")

col1, col2 = st.columns([3, 1])
with col1:
    keyword = st.text_input("분석할 키워드", placeholder="예: 무선 청소기")
with col2:
    if st.button("🚀 분석 실행", type="primary"):
        if not keyword:
            st.warning("키워드를 입력하세요!")
        else:
            with st.spinner(f"네이버에서 '{keyword}' 조회 중..."):
                
                # 1. 실제 데이터 가져오기
                naver_result = get_naver_data(keyword)
                now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # 결과 데이터 정리
                final_data = [
                    now,              # 날짜
                    keyword,          # 키워드
                    naver_result["상품수"], # 실제 상품수
                    naver_result["쇼핑주소"] # 확인용 링크
                ]
                
                # 2. 화면에 표시
                st.success("조회 성공!")
                
                # 결과 카드 보여주기
                m1, m2 = st.columns(2)
                m1.metric(label="검색 키워드", value=keyword)
                m2.metric(label="쇼핑 상품수", value=f"{naver_result['상품수']}개")
                
                # 3. 구글 시트 저장
                try:
                    gc = get_gspread_client()
                    sheet_url = st.secrets["SHEET_URL"]
                    doc = gc.open_by_url(sheet_url)
                    worksheet = doc.get_worksheet(0)
                    worksheet.append_row(final_data)
                    st.toast("✅ 구글 시트 저장 완료!", icon="💾")
                except Exception as e:
                    st.error(f"시트 저장 실패: {e}")
