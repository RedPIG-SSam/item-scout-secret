import streamlit as st
import pandas as pd
import requests
import gspread
from google.oauth2.service_account import Credentials
import datetime

# --- 페이지 설정 ---
st.set_page_config(page_title="팀장님 아이템 분석기 (API)", page_icon="⚡", layout="wide")

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

# --- ⚡ [핵심] 네이버 API로 데이터 수집 ---
def get_naver_api_data(keyword):
    # 1. 네이버 쇼핑 검색 API URL
    url = "https://openapi.naver.com/v1/search/shop.json"
    
    # 2. Secrets에서 내 출입증 꺼내오기
    client_id = st.secrets["NAVER_CLIENT_ID"]
    client_secret = st.secrets["NAVER_CLIENT_SECRET"]
    
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    
    # 3. 검색 요청 (정확도순, 1개만 조회해도 총 개수는 나옴)
    params = {"query": keyword, "display": 1, "sort": "sim"}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            # total: 검색된 전체 상품 수
            total_count = data.get('total', 0)
            
            return {
                "상태": "성공",
                "상품수": f"{total_count:,}", # 콤마 포맷 (예: 15,200)
                "쇼핑링크": f"https://search.shopping.naver.com/search/all?query={keyword}"
            }
        else:
            # 에러 발생 시 (401: 키 오류, 429: 하루 한도 초과 등)
            return {"상태": f"API 에러({response.status_code})", "상품수": "0", "쇼핑링크": "-"}
            
    except Exception as e:
        return {"상태": f"시스템 에러: {str(e)}", "상품수": "0", "쇼핑링크": "-"}

# ================= UI 시작 =================
st.title("⚡ 초고속 아이템 분석기 (Final)")
st.info("네이버 공식 API를 연동하여 **정확한 상품 수**를 실시간으로 추적합니다.")

col1, col2 = st.columns([3, 1])
with col1:
    keyword = st.text_input("분석할 키워드", placeholder="예: 블루투스 스피커")
with col2:
    if st.button("🚀 분석 실행", type="primary"):
        if not keyword:
            st.warning("키워드를 입력하세요!")
        else:
            with st.spinner(f"API로 '{keyword}' 조회 중..."):
                
                # 1. API 데이터 조회
                try:
                    result = get_naver_api_data(keyword)
                except KeyError:
                    st.error("❌ Secrets에 네이버 API 키가 없습니다!")
                    st.stop()
                
                now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # 2. 결과 표시
                if result["상태"] == "성공":
                    st.success("조회 성공!")
                    
                    # 결과 카드
                    m1, m2 = st.columns(2)
                    m1.metric("키워드", keyword)
                    m2.metric("총 상품 수", f"{result['상품수']}개")
                    
                    # 3. 구글 시트 저장
                    try:
                        gc = get_gspread_client()
                        sheet_url = st.secrets["SHEET_URL"]
                        doc = gc.open_by_url(sheet_url)
                        worksheet = doc.get_worksheet(0)
                        
                        # 시트에 넣을 데이터 [날짜, 키워드, 상품수, 링크]
                        final_data = [now, keyword, result['상품수'], result['쇼핑링크']]
                        
                        worksheet.append_row(final_data)
                        st.toast("✅ 구글 시트 저장 완료!", icon="💾")
                        
                    except Exception as e:
                        st.error(f"구글 시트 저장 실패: {e}")
                else:
                    st.error(f"조회 실패: {result['상태']}")
                    st.warning("팁: Secrets의 Client ID와 Secret이 정확한지 확인하세요.")
