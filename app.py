import streamlit as st
import pandas as pd
import requests
import gspread
from google.oauth2.service_account import Credentials
import datetime
import re # HTML 태그 제거용

# --- 페이지 설정 ---
st.set_page_config(page_title="팀장님 아이템 분석기 (Detail)", page_icon="🕵️‍♀️", layout="wide")

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

# --- 🧹 HTML 태그 청소부 (<b> 같은거 지움) ---
def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext

# --- ⚡ [핵심] 네이버 API로 상세 정보 수집 ---
def get_naver_api_data(keyword):
    url = "https://openapi.naver.com/v1/search/shop.json"
    
    client_id = st.secrets["NAVER_CLIENT_ID"]
    client_secret = st.secrets["NAVER_CLIENT_SECRET"]
    
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    
    # 정확도순(sim)으로 1등 상품을 가져옵니다.
    params = {"query": keyword, "display": 1, "sort": "sim"}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            total_count = data.get('total', 0)
            
            # 검색 결과가 하나라도 있으면 상세 정보를 가져옴
            if data['items']:
                item = data['items'][0] # 1등 상품
                
                # 데이터 추출 (없으면 '-' 표시)
                brand = item.get('brand', '-')
                mall_name = item.get('mallName', '-') # 경쟁사명
                title = clean_html(item.get('title', '-')) # 상품명 (태그 제거)
                lprice = f"{int(item.get('lprice', 0)):,}" # 가격 (콤마 추가)
                link = item.get('link', '-')
                
                return {
                    "상태": "성공",
                    "상품수": f"{total_count:,}",
                    "브랜드": brand,
                    "경쟁사": mall_name,
                    "상품명": title,
                    "가격": lprice,
                    "링크": link
                }
            else:
                return {
                    "상태": "성공(상품없음)",
                    "상품수": "0", "브랜드": "-", "경쟁사": "-", "상품명": "-", "가격": "-", "링크": "-"
                }
        else:
            return {"상태": f"에러({response.status_code})", "상품수": "0", "브랜드": "-", "경쟁사": "-", "상품명": "-", "가격": "-", "링크": "-"}
            
    except Exception as e:
        return {"상태": f"시스템 에러: {str(e)}", "상품수": "0", "브랜드": "-", "경쟁사": "-", "상품명": "-", "가격": "-", "링크": "-"}

# ================= UI 시작 =================
st.title("🕵️‍♀️ 아이템 심층 분석기")
st.info("키워드를 입력하면 **총 상품수**와 **1등 경쟁사 정보**를 엑셀에 기록합니다.")

col1, col2 = st.columns([3, 1])
with col1:
    keyword = st.text_input("분석할 키워드", placeholder="예: 무선 게이밍 마우스")
with col2:
    if st.button("🚀 상세 분석 실행", type="primary"):
        if not keyword:
            st.warning("키워드를 입력하세요!")
        else:
            with st.spinner(f"'{keyword}' 시장 조사 중..."):
                
                # 1. API 데이터 조회
                try:
                    result = get_naver_api_data(keyword)
                except KeyError:
                    st.error("❌ Secrets 설정 오류! 네이버 키를 확인하세요.")
                    st.stop()
                
                now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # 2. 결과 화면 표시
                if "성공" in result["상태"]:
                    st.success("분석 완료!")
                    
                    # 상세 정보 카드
                    c1, c2, c3 = st.columns(3)
                    c1.metric("총 상품 수", f"{result['상품수']}개")
                    c2.metric("1위 브랜드", result['브랜드'])
                    c3.metric("1위 경쟁사", result['경쟁사'])
                    
                    st.write(f"**대표 상품:** {result['상품명']} ({result['가격']}원)")
                    
                    # 3. 구글 시트 저장
                    try:
                        gc = get_gspread_client()
                        sheet_url = st.secrets["SHEET_URL"]
                        doc = gc.open_by_url(sheet_url)
                        worksheet = doc.get_worksheet(0)
                        
                        # [중요] 시트에 들어갈 순서입니다! (헤더와 맞춰주세요)
                        # 날짜 | 키워드 | 상품수 | 브랜드 | 경쟁사(몰) | 상품명 | 가격 | 링크
                        final_data = [
                            now, 
                            keyword, 
                            result['상품수'], 
                            result['브랜드'], 
                            result['경쟁사'], 
                            result['상품명'], 
                            result['가격'], 
                            result['링크']
                        ]
                        
                        worksheet.append_row(final_data)
                        st.toast(f"✅ 엑셀에 '{keyword}' 상세 정보 저장 완료!", icon="💾")
                        
                    except Exception as e:
                        st.error(f"구글 시트 저장 실패: {e}")
                else:
                    st.error(f"조회 실패: {result['상태']}")
