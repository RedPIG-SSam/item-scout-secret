import streamlit as st
import pandas as pd
import requests
import re  # 👈 강력한 검색 도구 추가
import gspread
from google.oauth2.service_account import Credentials
import datetime

# --- 페이지 설정 ---
st.set_page_config(page_title="팀장님 아이템 분석기 (Pro)", page_icon="🕵️", layout="wide")

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

# --- 🕵️ [핵심] 네이버 데이터 정밀 채굴 함수 ---
def get_naver_data(keyword):
    url = f"https://search.shopping.naver.com/search/all?query={keyword}"
    
    # 봇 차단 회피용 헤더 (일반 사람인 척 위장)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://www.naver.com/"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            html = response.text
            
            # [비장의 무기] HTML 태그가 아니라, 소스 코드 내의 'totalCount' 숫자를 직접 찾음
            # 패턴: "totalCount":12345 형태를 찾습니다.
            match = re.search(r'"totalCount":(\d+)', html)
            
            if match:
                # 찾은 숫자 가져오기
                raw_count = match.group(1)
                # 보기 좋게 콤마 찍기 (예: 15200 -> 15,200)
                product_count = f"{int(raw_count):,}"
            else:
                product_count = "집계실패(패턴없음)"
                
            return {
                "상태": "성공",
                "상품수": product_count,
                "쇼핑주소": url
            }
        else:
            return {"상태": f"접속차단({response.status_code})", "상품수": "0", "쇼핑주소": url}
            
    except Exception as e:
        return {"상태": f"에러: {str(e)}", "상품수": "0", "쇼핑주소": "-"}

# ================= UI 시작 =================
st.title("🕵️ 실시간 아이템 분석기 (Pro)")
st.write("네이버 쇼핑의 **실제 상품 수**를 정밀하게 추적합니다.")

col1, col2 = st.columns([3, 1])
with col1:
    keyword = st.text_input("분석할 키워드", placeholder="예: 스칼렛 솔로")
with col2:
    if st.button("🚀 분석 실행", type="primary"):
        if not keyword:
            st.warning("키워드를 입력하세요!")
        else:
            with st.spinner(f"'{keyword}' 정밀 분석 중..."):
                
                # 1. 데이터 수집
                naver_result = get_naver_data(keyword)
                now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # 2. 결과 표시 (화면)
                if naver_result["상품수"] not in ["0", "집계실패(패턴없음)"]:
                    st.success(f"분석 성공! 총 **{naver_result['상품수']}개**의 상품이 발견되었습니다.")
                    st.balloons()
                else:
                    st.error(f"분석 실패: {naver_result['상태']}")
                
                # 결과 카드
                m1, m2 = st.columns(2)
                m1.metric("검색 키워드", keyword)
                m2.metric("상품 수", naver_result['상품수'])
                
                # 3. 구글 시트 저장
                try:
                    gc = get_gspread_client()
                    sheet_url = st.secrets["SHEET_URL"]
                    doc = gc.open_by_url(sheet_url)
                    worksheet = doc.get_worksheet(0)
                    
                    final_data = [now, keyword, naver_result["상품수"], naver_result["쇼핑주소"]]
                    worksheet.append_row(final_data)
                    st.toast("✅ 엑셀 저장 완료!", icon="💾")
                    
                except Exception as e:
                    st.error(f"시트 저장 실패: {e}")
