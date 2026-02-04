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
st.set_page_config(page_title="💎 아이템 스카우트 (Ver 12.0)", page_icon="💎", layout="wide")

# ================= 1. 유틸리티 함수들 =================
def clean_num(n):
    """숫자만 남기고 정수 변환"""
    if not n: return 0
    s = str(n).replace(",", "")
    return 10 if "<" in s else int(s) if s.isdigit() else 0

def extract_keywords(title):
    """제목에서 키워드 추출"""
    clean = re.sub(r'[^\w\s]', ' ', title)
    return [w for w in clean.split() if len(w) > 1]

def get_seo_score(title, target_keyword):
    """SEO 점수 계산 로직 (팀장님 Ver 12.0)"""
    clean_title = title.replace('<b>','').replace('</b>','')
    score = 80
    length = len(clean_title)
    
    # 1. 길이 점수
    if 20 <= length <= 50: score += 10
    elif length < 10: score -= 20
    elif length > 60: score -= 10
    
    # 2. 키워드 위치 (앞쪽에 있는지)
    target_parts = target_keyword.split()
    front_part = clean_title[:15]
    match_count = sum(1 for part in target_parts if part in front_part)
    if match_count > 0: score += 10
    
    # 3. 반복 감점
    counts = Counter(extract_keywords(clean_title))
    repeats = sum(1 for w in counts if counts[w] >= 3)
    if repeats > 0: score -= 20
    
    # 4. 특수문자 감점
    special_chars = len(re.findall(r'[^\w\s]', clean_title))
    if special_chars > 5: score -= 10
    
    return max(0, min(100, score))

def get_seo_grade_text(score):
    if score >= 95: return "👑S"
    elif score >= 85: return "✨A"
    elif score >= 70: return "⚠️B"
    else: return "❌F"

def calculate_power_score(rank, reviews, is_brand, is_big_mall, seo_score):
    """종합 전투력 계산"""
    total = 0
    total += max(0, 41 - rank) # 랭킹 점수
    total += min(30, reviews / 10) # 리뷰 점수
    if is_brand or is_big_mall: total += 20 # 브랜드/대형몰 가산점
    total += (seo_score / 10) # SEO 반영
    return int(total)

# ================= 2. API 통신 함수들 =================

def get_keyword_stats(keywords_list):
    """네이버 검색광고 API (검색량 조회)"""
    BASE_URL = "https://api.searchad.naver.com"
    URI = "/keywordstool"
    
    try:
        customer_id = st.secrets["NAVER_CUSTOMER_ID"]
        access_license = st.secrets["NAVER_ACCESS_LICENSE"]
        secret_key = st.secrets["NAVER_SECRET_KEY"]
    except:
        st.error("❌ Secrets에 광고 API 키가 없습니다!")
        return {}

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
    except Exception as e:
        st.error(f"광고 API 에러: {e}")
    return {}

def get_shopping_data(keyword):
    """네이버 쇼핑 API (상품 목록 조회)"""
    url = "https://openapi.naver.com/v1/search/shop.json"
    try:
        headers = {
            "X-Naver-Client-Id": st.secrets["NAVER_CLIENT_ID"],
            "X-Naver-Client-Secret": st.secrets["NAVER_CLIENT_SECRET"]
        }
    except:
        return None
        
    params = {"query": keyword, "display": 80, "sort": "sim"} # 80개 조회
    try:
        res = requests.get(url, headers=headers, params=params)
        return res.json()
    except: return None

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

# ================= 3. 메인 화면 UI =================
st.title("💎 아이템 스카우트 Ver 12.0")
st.info("검색량 조회 + SEO 채점 + 엑셀 칼각 디자인까지 한 번에 처리합니다.")

with st.form("analysis_form"):
    col1, col2 = st.columns([3, 1])
    with col1:
        input_keywords = st.text_input("분석할 키워드 (쉼표로 구분)", placeholder="예: 매장용 앰프, 블루투스 스피커")
        my_store_name = st.text_input("내 스토어명 (강조용)", placeholder="예: 베링거 스토어")
    with col2:
        st.write("")
        st.write("")
        submit_btn = st.form_submit_button("🚀 분석 및 시트 저장", type="primary")

if submit_btn and input_keywords:
    with st.spinner("💎 Ver 12.0 엔진 가동 중... (검색량 조회 -> 상품 분석 -> SEO 채점)"):
        
        target_keywords = [k.strip() for k in input_keywords.split(',')]
        
        # 1. 검색량 조회 (광고 API)
        stats_map = get_keyword_stats(target_keywords)
        
        all_results = []
        kst_now = (datetime.datetime.now() + datetime.timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')
        big_malls = ["쿠팡", "11번가", "G마켓", "옥션", "인터파크", "롯데", "신세계", "이마트"]

        for kw in target_keywords:
            shop = get_shopping_data(kw)
            if not shop: continue
            
            items = shop.get('items', [])
            total_products = int(shop.get('total', 0))
            
            # 검색량 데이터 매칭
            stat = stats_map.get(kw.replace(" ", ""), {})
            pc_vol = clean_num(stat.get('monthlyPcQcCnt', 0))
            mo_vol = clean_num(stat.get('monthlyMobileQcCnt', 0))
            total_vol = pc_vol + mo_vol
            comp_ratio = round(total_products / total_vol, 2) if total_vol > 0 else 0
            
            # 상위 10개 키워드 분석
            top_10 = items[:10]
            prices = [clean_num(i['lprice']) for i in top_10 if clean_num(i['lprice']) > 100]
            avg_price = sum(prices) / len(prices) if prices else 0
            all_titles = " ".join([i['title'].replace('<b>','').replace('</b>','') for i in top_10])
            top_kws = [w[0] for w in Counter(extract_keywords(all_titles)).most_common(7)]
            
            # [시장분석 행 추가]
            all_results.append({
                '순위': 0, '구분': '📢 시장분석', 
                '종합점수': '-', 
                '스토어명': f"평균가 {int(avg_price):,}원",
                '상품명': f"검색 {total_vol:,}회 / 상품 {total_products:,}개", 
                'AI_전략': f"Top 키워드: {', '.join(top_kws[:3])}", 
                '가격': int(avg_price), '키워드': kw, '검색량': total_vol, '경쟁강도': comp_ratio, 
                '수집일시': kst_now
            })
            
            # [개별 상품 분석 Loop]
            for idx, item in enumerate(items):
                rank = idx + 1
                title = item['title'].replace('<b>','').replace('</b>','')
                mall = item.get('mallName', '')
                brand = item.get('brand', '')
                price = clean_num(item.get('lprice'))
                is_mine = my_store_name in mall if my_store_name else False
                is_big_mall = any(big in mall for big in big_malls)
                
                # 점수 계산
                seo_raw_score = get_seo_score(title, kw)
                seo_grade_text = get_seo_grade_text(seo_raw_score)
                reviews = clean_num(item.get('reviewCount', 0))
                power_score = calculate_power_score(rank, reviews, bool(brand), is_big_mall, seo_raw_score)
                
                # 점수 표시 텍스트
                score_display = f"{power_score}점"
                if power_score >= 80: score_display += "👿"
                elif power_score <= 40: score_display += "🍀"
                
                category = "일반"
                if brand: category = "브랜드"
                if is_mine: category = "★내 상품"
                
                # 전략 코멘트
                strategy_comment = f"타이틀: {seo_grade_text}"
                if is_mine:
                    my_kws = extract_keywords(title)
                    missing = [w for w in top_kws if w not in my_kws]
                    strategy_comment = f"누락: {', '.join(missing[:2])}" if missing else "✅SEO완벽"
                elif not brand and rank <= 10 and not is_big_mall:
                     if power_score < 50: strategy_comment = "🎯공략타겟"
                elif seo_raw_score < 50:
                     strategy_comment += " (수정要)"

                all_results.append({
                    '순위': rank, '구분': category, 
                    '종합점수': score_display, 
                    '스토어명': mall, '상품명': title, 
                    'AI_전략': strategy_comment,
                    '가격': price, '키워드': kw, '검색량': total_vol, '경쟁강도': comp_ratio, 
                    '수집일시': kst_now
                })

        # 2. 구글 시트 저장 및 디자인 적용
        if all_results:
            df = pd.DataFrame(all_results)
            # 컬럼 순서 강제 지정
            cols = ['순위', '종합점수', '구분', '스토어명', '상품명', 'AI_전략', '가격', '키워드', '검색량', '경쟁강도', '수집일시']
            df = df[cols]
            
            try:
                gc = get_gspread_client()
                sheet_url = st.secrets["SHEET_URL"]
                doc = gc.open_by_url(sheet_url)
                ws = doc.get_worksheet(0)
                
                # 시트 초기화 후 데이터 쓰기
                ws.clear()
                ws.update(values=[df.columns.values.tolist()] + df.values.tolist(), range_name='A1')
                
                # [★ 칼각 디자인 적용]
                try:
                    # 열 너비 조절
                    ws.set_column_width(1, 35)   # 순위
                    ws.set_column_width(2, 90)   # 종합점수
                    ws.set_column_width(3, 70)   # 구분
                    ws.set_column_width(4, 120)  # 스토어명
                    ws.set_column_width(5, 450)  # 상품명 (제일 넓게)
                    ws.set_column_width(6, 150)  # AI전략
                    ws.set_column_width(7, 70)   # 가격
                    ws.set_column_width(8, 90)   # 키워드
                    ws.set_column_width(9, 60)   # 검색량
                    ws.set_column_width(10, 60)  # 경쟁강도
                    ws.set_column_width(11, 130) # 수집일시
                    
                    # 틀 고정
                    ws.freeze(rows=1)
                    
                    # 헤더 색상
                    ws.format("A1:K1", {"backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}, "textFormat": {"bold": True}, "horizontalAlignment": "CENTER"})
                    
                    # 시장분석 행 강조 (노란색)
                    summary_indices = df.index[df['순위'] == 0].tolist()
                    for idx in summary_indices:
                        row_num = idx + 2 # 헤더(1) + 0-index(1) = 2
                        ws.format(f"A{row_num}:K{row_num}", {"backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.8}, "textFormat": {"bold": True}})
                        
                except Exception as e:
                    st.warning(f"데이터는 저장됐는데 디자인 적용 중 오류: {e}")

                st.success(f"✅ 분석 완료! 총 {len(all_results)}개 데이터를 시트에 '칼각'으로 저장했습니다.")
                st.dataframe(df) # 화면에도 보여줌

            except Exception as e:
                st.error(f"구글 시트 저장 실패: {e}")
