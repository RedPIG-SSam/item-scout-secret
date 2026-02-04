import streamlit as st
import pandas as pd
import requests
import gspread
from google.oauth2.service_account import Credentials
import datetime
import time
import hmac
import hashlib
import base64
import re
from collections import Counter

# --- 페이지 설정 ---
st.set_page_config(page_title="💎 아이템 스카우트 (어뷰징 탐지)", page_icon="🚨", layout="wide")

# ================= 1. 유틸리티 & 어뷰징 로직 =================
def clean_num(n):
    if not n: return 0
    s = str(n).replace(",", "")
    return 10 if "<" in s else int(s) if s.isdigit() else 0

def extract_keywords(title):
    clean = re.sub(r'[^\w\s]', ' ', title)
    return [w for w in clean.split() if len(w) > 1]

# [SEO 채점]
def get_seo_score(title, target_keyword):
    clean_title = title.replace('<b>','').replace('</b>','')
    score = 80
    length = len(clean_title)
    if 20 <= length <= 50: score += 10
    elif length < 10: score -= 20
    elif length > 60: score -= 10
    
    target_parts = target_keyword.split()
    front_part = clean_title[:15]
    match_count = sum(1 for part in target_parts if part in front_part)
    if match_count > 0: score += 10
    
    counts = Counter(extract_keywords(clean_title))
    repeats = sum(1 for w in counts if counts[w] >= 3)
    if repeats > 0: score -= 20
    
    special_chars = len(re.findall(r'[^\w\s]', clean_title))
    if special_chars > 5: score -= 10
    return max(0, min(100, score))

def get_seo_grade_text(score):
    if score >= 95: return "👑S"
    elif score >= 85: return "✨A"
    elif score >= 70: return "⚠️B"
    else: return "❌F"

def calculate_power_score(rank, reviews, is_brand, is_big_mall, seo_score):
    total = 0
    total += max(0, 41 - rank)
    total += min(30, reviews / 10)
    if is_brand or is_big_mall: total += 20
    total += (seo_score / 10)
    return int(total)

# [🚨 핵심] 어뷰징 탐지 로직
def detect_abuse(rank, reviews, seo_score, is_brand, is_big_mall):
    """
    네이버 쇼핑 로직 역추적:
    1. 트래픽/슬롯: 상품력(리뷰, SEO)이 개판인데 상위노출(1~10위)인 경우
    2. 가구매: 리뷰가 너무 적은데 상위권인 경우 (약한 의심)
    """
    if is_brand or is_big_mall:
        return "✅정상(브랜드)"
    
    # 1. 트래픽/슬롯 의심 (랭킹은 높은데 기본기가 엉망)
    if rank <= 10:
        if seo_score < 40 and reviews < 10:
            return "🚨슬롯/트래픽 강력의심 (기본기X)"
        if reviews < 5:
            return "⚠️가구매/트래픽 주의 (리뷰부족)"
        if seo_score < 50:
            return "⚠️어뷰징 가능성 (SEO불량)"
            
    return "작업징후 없음"

# ================= 2. API 통신 함수들 =================
def get_keyword_stats(keywords_list):
    BASE_URL = "https://api.searchad.naver.com"
    URI = "/keywordstool"
    
    try:
        customer_id = st.secrets["NAVER_CUSTOMER_ID"]
        access_license = st.secrets["NAVER_ACCESS_LICENSE"]
        secret_key = st.secrets["NAVER_SECRET_KEY"]
    except:
        st.error("❌ Secrets 설정 오류: 광고 API 키가 없습니다.")
        return None

    timestamp = str(int(time.time() * 1000))
    msg = f"{timestamp}.GET.{URI}"
    signature = base64.b64encode(hmac.new(secret_key.encode(), msg.encode(), hashlib.sha256).digest()).decode()

    headers = {
        "X-Timestamp": timestamp, "X-API-KEY": access_license,
        "X-Customer": customer_id, "X-Signature": signature
    }
    
    clean_kws = [k.strip().replace(" ", "") for k in keywords_list if k.strip()][:5]
    params = {"hintKeywords": ",".join(clean_kws), "showDetail": "1"}
    
    try:
        response = requests.get(f"{BASE_URL}{URI}", headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            return {item['relKeyword'].replace(" ", ""): item for item in data['keywordList']}
        else:
            st.error(f"광고 API 호출 실패: {response.status_code}")
    except Exception as e:
        st.error(f"광고 API 연결 에러: {e}")
    return {}

def get_shopping_data(keyword):
    url = "https://openapi.naver.com/v1/search/shop.json"
    try:
        headers = {
            "X-Naver-Client-Id": st.secrets["NAVER_CLIENT_ID"],
            "X-Naver-Client-Secret": st.secrets["NAVER_CLIENT_SECRET"]
        }
    except:
        return None
    params = {"query": keyword, "display": 80, "sort": "sim"}
    try:
        res = requests.get(url, headers=headers, params=params)
        return res.json()
    except: return None

# --- 디자인: 시트 열 너비 조절 (Batch Update) ---
def set_column_widths(worksheet, widths):
    body = {"requests": []}
    for col_char, width in widths:
        col_index = ord(col_char.upper()) - 65
        body["requests"].append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": worksheet.id, "dimension": "COLUMNS",
                    "startIndex": col_index, "endIndex": col_index + 1
                },
                "properties": {"pixelSize": width}, "fields": "pixelSize"
            }
        })
    try:
        worksheet.spreadsheet.batch_update(body)
    except: pass

# --- 🔐 구글 시트 인증 ---
def get_gspread_client():
    try:
        creds_info = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(credentials)
    except: return None

# ================= 3. 메인 화면 UI =================
st.title("🚨 아이템 스카우트 (어뷰징 탐지 Ver)")
st.info("검색량 조회 + **트래픽/가구매 작업 업체 탐지** 기능이 추가되었습니다.")

with st.form("analysis_form"):
    col1, col2 = st.columns([3, 1])
    with col1:
        input_keywords = st.text_input("분석할 키워드", placeholder="예: 스칼렛 솔로")
        my_store_name = st.text_input("내 스토어명", placeholder="예: 베링거 스토어")
    with col2:
        st.write("")
        st.write("")
        submit_btn = st.form_submit_button("🚀 분석 및 탐지", type="primary")

if submit_btn and input_keywords:
    target_keywords = [k.strip() for k in input_keywords.split(',')]
    
    # 1. 검색량 조회 (실패 시 메시지 출력)
    stats_map = get_keyword_stats(target_keywords)
    if stats_map is None:
        st.warning("⚠️ 광고 API 연결 실패 -> 검색량이 0으로 나옵니다. Secrets를 확인하세요!")
        stats_map = {}

    with st.spinner("🕵️‍♂️ 어뷰징 업체 색출 중..."):
        all_results = []
        kst_now = (datetime.datetime.now() + datetime.timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')
        big_malls = ["쿠팡", "11번가", "G마켓", "옥션", "인터파크", "롯데", "신세계", "이마트", "스마트스토어"]

        for kw in target_keywords:
            shop = get_shopping_data(kw)
            if not shop: continue
            
            items = shop.get('items', [])
            total_products = int(shop.get('total', 0))
            
            # 검색량 매칭
            stat = stats_map.get(kw.replace(" ", ""), {})
            pc_vol = clean_num(stat.get('monthlyPcQcCnt', 0))
            mo_vol = clean_num(stat.get('monthlyMobileQcCnt', 0))
            total_vol = pc_vol + mo_vol
            comp_ratio = round(total_products / total_vol, 2) if total_vol > 0 else 0
            
            # 상위 분석
            top_10 = items[:10]
            prices = [clean_num(i['lprice']) for i in top_10 if clean_num(i['lprice']) > 100]
            avg_price = sum(prices) / len(prices) if prices else 0
            
            # [시장분석 행]
            all_results.append({
                '순위': 0, '구분': '📢 시장분석', '어뷰징': '-',
                '스토어명': f"평균 {int(avg_price):,}원",
                '상품명': f"검색 {total_vol:,} / 상품 {total_products:,}", 
                'AI_전략': f"경쟁강도 {comp_ratio}", 
                '가격': int(avg_price), '키워드': kw, '검색량': total_vol,
                '수집일시': kst_now
            })
            
            # [개별 상품 분석]
            for idx, item in enumerate(items):
                rank = idx + 1
                title = item['title'].replace('<b>','').replace('</b>','')
                mall = item.get('mallName', '')
                brand = item.get('brand', '')
                price = clean_num(item.get('lprice'))
                is_mine = my_store_name in mall if my_store_name else False
                is_big_mall = any(big in mall for big in big_malls)
                
                seo_raw_score = get_seo_score(title, kw)
                seo_grade_text = get_seo_grade_text(seo_raw_score)
                reviews = clean_num(item.get('reviewCount', 0))
                
                # 어뷰징 탐지 실행
                abuse_status = detect_abuse(rank, reviews, seo_raw_score, bool(brand), is_big_mall)
                
                # 카테고리
                category = "일반"
                if brand: category = "브랜드"
                if is_mine: category = "★내 상품"
                
                # 전략 코멘트
                strategy_comment = f"SEO: {seo_grade_text}"
                if is_mine:
                    strategy_comment = "내 상품 관리중"
                elif "의심" in abuse_status:
                    strategy_comment = "🚫벤치마킹 금지"

                all_results.append({
                    '순위': rank, '구분': category, '어뷰징': abuse_status,
                    '스토어명': mall, '상품명': title, 
                    'AI_전략': strategy_comment,
                    '가격': price, '키워드': kw, '검색량': total_vol,
                    '수집일시': kst_now
                })

        # 3. 구글 시트 저장
        if all_results:
            df = pd.DataFrame(all_results)
            # 컬럼 순서 (어뷰징 추가됨)
            cols = ['순위', '구분', '어뷰징', '스토어명', '상품명', 'AI_전략', '가격', '키워드', '검색량', '수집일시']
            df = df[cols]
            
            try:
                gc = get_gspread_client()
                sheet_url = st.secrets["SHEET_URL"]
                doc = gc.open_by_url(sheet_url)
                ws = doc.get_worksheet(0)
                
                ws.clear()
                ws.update(values=[df.columns.values.tolist()] + df.values.tolist(), range_name='A1')
                
                # [칼각 디자인]
                set_column_widths(ws, [
                    ('A', 35), ('B', 60), ('C', 150), ('D', 120),
                    ('E', 400), ('F', 120), ('G', 70), ('H', 80), ('I', 60), ('J', 130)
                ])
                
                ws.freeze(rows=1)
                ws.format("A1:J1", {"backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}, "textFormat": {"bold": True}, "horizontalAlignment": "CENTER"})
                
                # 경고 색상 (어뷰징 행은 빨간색 강조)
                # (생략: 코드가 너무 길어지니 일단 데이터부터 확인!)

                st.success(f"✅ 분석 완료! 어뷰징 의심 업체 {len(df[df['어뷰징'].str.contains('의심')])}건 발견.")
                st.dataframe(df) # 화면 확인용
            except Exception as e:
                st.error(f"저장 실패: {e}")
