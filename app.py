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
st.set_page_config(page_title="💎 아이템 스카우트 (Final)", page_icon="💎", layout="wide")

# ================= 0. 도움말 및 UI 가이드 (추가된 부분) =================
st.title("💎 아이템 스카우트 Ver 12.0")

with st.expander("📚 지표 해석 가이드 (여기를 눌러서 확인하세요!)", expanded=False):
    st.markdown("""
    ### 📊 주요 지표 설명
    
    **1. 경쟁강도 (상품수 ÷ 검색량)**
    * **0.5 이하:** 꿀통! (검색은 많은데 상품이 적음)
    * **1 ~ 5:** 적당함 (일반적인 시장)
    * **10 이상:** 🔥레드오션 (경쟁이 매우 치열함)
    
    **2. SEO 종합점수 & 등급**
    * **👑S (95점~):** 완벽합니다. 상위노출 가능성 높음!
    * **✨A (85점~):** 훌륭해요. 조금만 다듬으면 S급.
    * **⚠️B (70점~):** 평범합니다. 제목 최적화가 필요해요.
    * **❌F (70점 미만):** 상품명 갈아엎어야 합니다.
    
    **3. 🚨 어뷰징(가구매/트래픽) 판독**
    * **슬롯/트래픽 의심:** 랭킹은 1~10위인데 리뷰도 없고 SEO도 엉망인 경우. (기계적 조작 의심)
    * **벤치마킹 주의:** 어뷰징 업체는 따라 해도 소용없으니 거르세요!
    """)

st.info("키워드를 입력하면 **검색량 조회 + 가구매 업체 탐지 + 엑셀 칼각 저장**을 수행합니다.")

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

# [🚨 어뷰징 탐지 로직]
def detect_abuse(rank, reviews, seo_score, is_brand, is_big_mall):
    if is_brand or is_big_mall:
        return "✅정상(브랜드)"
    
    # 랭킹 10위권 내인데 기본기가 부족한 경우
    if rank <= 10:
        if seo_score < 40 and reviews < 10:
            return "🚨슬롯/트래픽 강력의심"
        if reviews < 5:
            return "⚠️리뷰부족(가구매의심)"
        if seo_score < 50:
            return "⚠️SEO불량(트래픽의심)"
            
    return "-"

# ================= 2. API 통신 함수들 =================
def get_keyword_stats(keywords_list):
    BASE_URL = "https://api.searchad.naver.com"
    URI = "/keywordstool"
    
    try:
        customer_id = st.secrets["NAVER_CUSTOMER_ID"]
        access_license = st.secrets["NAVER_ACCESS_LICENSE"]
        secret_key = st.secrets["NAVER_SECRET_KEY"]
    except:
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
    except: pass
    return {}

def get_shopping_data(keyword):
    url = "https://openapi.naver.com/v1/search/shop.json"
    try:
        headers = {
            "X-Naver-Client-Id": st.secrets["NAVER_CLIENT_ID"],
            "X-Naver-Client-Secret": st.secrets["NAVER_CLIENT_SECRET"]
        }
    except: return None
    params = {"query": keyword, "display": 80, "sort": "sim"}
    try:
        res = requests.get(url, headers=headers, params=params)
        return res.json()
    except: return None

# --- 디자인: 시트 열 너비 조절 ---
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

# ================= 3. 입력 폼 및 실행 =================
with st.form("analysis_form"):
    col1, col2 = st.columns([3, 1])
    with col1:
        input_keywords = st.text_input("분석할 키워드 (쉼표 구분)", placeholder="예: 매장용 앰프, 블루투스 스피커")
        my_store_name = st.text_input("내 스토어명 (내 상품 찾기용)", placeholder="예: 베링거 스토어")
    with col2:
        st.write("")
        st.write("")
        submit_btn = st.form_submit_button("🚀 분석 실행", type="primary")

if submit_btn and input_keywords:
    target_keywords = [k.strip() for k in input_keywords.split(',')]
    
    stats_map = get_keyword_stats(target_keywords)
    if stats_map is None:
        st.error("❌ Secrets 오류! 광고 API 키를 확인해주세요.")
        st.stop()

    with st.spinner("💎 데이터 채굴 중... (네이버 쇼핑 + 광고API + 어뷰징 탐지)"):
        all_results = []
        kst_now = (datetime.datetime.now() + datetime.timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')
        big_malls = ["쿠팡", "11번가", "G마켓", "옥션", "인터파크", "롯데", "신세계", "이마트", "스마트스토어"]

        for kw in target_keywords:
            shop = get_shopping_data(kw)
            if not shop: continue
            
            items = shop.get('items', [])
            total_products = int(shop.get('total', 0))
            
            # 검색량
            stat = stats_map.get(kw.replace(" ", ""), {})
            pc_vol = clean_num(stat.get('monthlyPcQcCnt', 0))
            mo_vol = clean_num(stat.get('monthlyMobileQcCnt', 0))
            total_vol = pc_vol + mo_vol
            comp_ratio = round(total_products / total_vol, 2) if total_vol > 0 else 0
            
            # 시장분석 행
            top_10 = items[:10]
            prices = [clean_num(i['lprice']) for i in top_10 if clean_num(i['lprice']) > 100]
            avg_price = sum(prices) / len(prices) if prices else 0
            
            all_results.append({
                '순위': 0, '구분': '📢 시장분석', '어뷰징': '-',
                '스토어명': f"평균 {int(avg_price):,}원",
                '상품명': f"검색 {total_vol:,} / 상품 {total_products:,}", 
                'AI_전략': f"경쟁강도 {comp_ratio}", 
                '가격': int(avg_price), '키워드': kw, '검색량': total_vol,
                '수집일시': kst_now
            })
            
            # 상품 분석
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
                
                abuse_status = detect_abuse(rank, reviews, seo_raw_score, bool(brand), is_big_mall)
                
                category = "일반"
                if brand: category = "브랜드"
                if is_mine: category = "★내 상품"
                
                strategy_comment = f"SEO: {seo_grade_text}"
                if is_mine: strategy_comment = "내 상품 관리"
                elif "의심" in abuse_status: strategy_comment = "🚫벤치마킹 금지"

                all_results.append({
                    '순위': rank, '구분': category, '어뷰징': abuse_status,
                    '스토어명': mall, '상품명': title, 
                    'AI_전략': strategy_comment,
                    '가격': price, '키워드': kw, '검색량': total_vol,
                    '수집일시': kst_now
                })

        # 저장
        if all_results:
            df = pd.DataFrame(all_results)
            cols = ['순위', '구분', '어뷰징', '스토어명', '상품명', 'AI_전략', '가격', '키워드', '검색량', '수집일시']
            df = df[cols]
            
            try:
                gc = get_gspread_client()
                sheet_url = st.secrets["SHEET_URL"]
                doc = gc.open_by_url(sheet_url)
                ws = doc.get_worksheet(0)
                
                ws.clear()
                ws.update(values=[df.columns.values.tolist()] + df.values.tolist(), range_name='A1')
                set_column_widths(ws, [('A', 35), ('B', 60), ('C', 150), ('D', 120), ('E', 400), ('F', 120), ('G', 70), ('H', 80), ('I', 60), ('J', 130)])
                ws.freeze(rows=1)
                ws.format("A1:J1", {"backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}, "textFormat": {"bold": True}, "horizontalAlignment": "CENTER"})
                
                # 시장분석 강조
                summary_indices = df.index[df['순위'] == 0].tolist()
                for idx in summary_indices:
                    row_num = idx + 2
                    ws.format(f"A{row_num}:J{row_num}", {"backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.8}, "textFormat": {"bold": True}})

                st.success(f"✅ 분석 완료! (도움말을 참고해서 데이터를 분석해보세요!)")
                st.dataframe(df)
            except Exception as e:
                st.error(f"저장 실패: {e}")
