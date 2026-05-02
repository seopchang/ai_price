import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import plotly.graph_objects as go
import datetime
import gspread
from google.oauth2.service_account import Credentials
import json
import re

# --- [1] 구글 시트 연결 세팅 (투명 알바생 설정) ---
@st.cache_resource
def init_connection():
    # 스트림릿 금고(Secrets)에서 마스터 열쇠 꺼내오기
    key_dict = json.loads(st.secrets["gcp_secret"])
    creds = Credentials.from_service_account_info(
        key_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    return gspread.authorize(creds)

def save_to_sheet(date_str, score, ai_report, feedback_result):
    try:
        client = init_connection()
        doc = client.open("AI_Price_DB") # 우리가 만든 구글 시트 이름
        sheet = doc.sheet1 # 첫 번째 시트에 저장
        # 시트 맨 아래에 새로운 데이터 한 줄 추가
        sheet.append_row([date_str, str(score), ai_report, feedback_result])
        return True
    except Exception as e:
        st.error(f"구글 시트 저장 중 에러가 발생했어요: {e}")
        return False

# --- [2] 네이버 경제 뉴스 크롤링 파이프라인 ---
def get_news_headlines():
    headers = {"User-Agent": "Mozilla/5.0"}
    url = "https://news.naver.com/main/main.naver?mode=LSD&mid=shm&sid1=101" # 경제 뉴스 메인
    try:
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 헤드라인 텍스트 추출 (10개)
        headlines = soup.select('.sh_text_headline')
        news_text = "\n".join([h.text.strip() for h in headlines[:10]])
        
        if not news_text:
            return "최신 뉴스 헤드라인 텍스트를 찾지 못했습니다. (테스트 데이터: 환율 급등, 해상 운임 상승, 기상이변으로 인한 곡물가 상승)"
        return news_text
    except Exception as e:
        return "크롤링 실패. (테스트 데이터: 환율 급등, 해상 운임 상승, 곡물가 상승)"

# --- [3] 생성형 AI (XAI) 분석 및 프롬프트 엔지니어링 ---
def analyze_with_gemini(api_key, news_data):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash') 
    
    prompt = f"""
    당신은 거시경제 애널리스트입니다. 아래의 실시간 경제 뉴스 헤드라인들을 분석하여,
    향후 대한민국 물가 상승에 미칠 위험도를 0점에서 100점 사이의 숫자로 평가해주세요.
    
    [최신 경제 뉴스]
    {news_data}
    
    [요청 사항]
    1. 분석 결과 보고서 작성 (사건 -> 파급 효과 -> 가격 상승의 인과관계를 설명할 것)
    2. 마지막 줄에는 반드시 '최종 위험도: OO점' 형식으로 점수를 명확히 적어주세요.
    """
    
    response = model.generate_content(prompt)
    return response.text

# --- [4] 대시보드 시각화 (게이지 차트) ---
def draw_gauge_chart(score):
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = score,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "실시간 물가 변동 위험도 지수", 'font': {'size': 20}},
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': "rgba(0,0,0,0)"}, # 기본 바 숨기기
            'steps' : [
                {'range': [0, 30], 'color': "#00CC96"},   # 안전 (초록)
                {'range': [30, 70], 'color': "#FFA15A"},   # 주의 (주황)
                {'range': [70, 100], 'color': "#EF553B"}   # 위험 (빨강)
            ],
            'threshold': {
                'line': {'color': "black", 'width': 5},
                'thickness': 0.75,
                'value': score # 현재 점수를 선으로 표시
            }
        }
    ))
    return fig

# --- [5] 스트림릿 웹 화면(UI) 구성 ---
st.set_page_config(page_title="AI 물가 파수꾼", page_icon="📈", layout="wide")

st.title("📈 비정형 데이터 기반 물가 조기 경보 시스템")
st.markdown("웹 크롤링과 생성형 AI를 활용하여 실시간 뉴스를 분석하고, 물가 상승 위험도를 구글 시트에 영구 기록합니다.")

# 왼쪽 사이드바
with st.sidebar:
    st.header("⚙️ 설정 패널")
    user_api_key = st.text_input("Gemini API 키를 입력하세요", type="password")
    st.markdown("---")
    st.info("💡 **시스템 작동 프로세스**\n1. 실시간 포털 뉴스 크롤링\n2. 설명 가능한 AI(XAI) 인과관계 분석\n3. 위험도 정량화 및 시각화\n4. 클라우드 DB(구글 시트) 데이터 적재")

# 메인 실행 버튼
if st.button("🚀 뉴스 수집 및 물가 위험도 분석 시작", use_container_width=True):
    if not user_api_key:
        st.warning("⚠️ 왼쪽 사이드바에 Gemini API 키를 먼저 입력해주세요!")
    else:
        with st.spinner("🤖 웹 크롤링 및 AI 분석을 진행 중입니다... (약 10~15초 소요)"):
            
            # 단계 1: 뉴스 수집
            news_text = get_news_headlines()
            
            try:
                # 단계 2: AI 리포트 생성
                report = analyze_with_gemini(user_api_key, news_text)
                
                # 단계 3: 비정형 데이터 정량화 (점수 추출)
                score_match = re.search(r'최종 위험도:\s*(\d+)점', report)
                if score_match:
                    final_score = int(score_match.group(1))
                else:
                    final_score = 50 # 에러 방지용 기본값
                
                # 화면 반으로 나눠서 결과 보여주기
                col1, col2 = st.columns([1, 1])
                with col1:
                    st.subheader("📊 AI 위험도 정량 분석")
                    st.plotly_chart(draw_gauge_chart(final_score), use_container_width=True)
                
                with col2:
                    st.subheader("📝 애널리스트 분석 리포트")
                    st.write(report)
                
                # 단계 4: 구글 시트(DB) 저장
                today_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                is_saved = save_to_sheet(today_date, final_score, report, "검증 대기")
                
                if is_saved:
                    st.success("💾 오늘의 물가 분석 결과가 구글 시트(AI_Price_DB)에 안전하게 저장되었습니다!")
                
            except Exception as e:
                st.error(f"분석 중 에러가 발생했습니다. API 키가 정확한지, 한도를 초과하지 않았는지 확인해주세요. (상세 에러: {e})")


# --- [6] AI 자가 검증 (피드백 루프) 시스템 ---
st.markdown("---")
st.subheader("🔍 AI 예측 자가 검증 (Feedback Loop)")
st.caption("과거의 예측이 맞았는지 최신 뉴스와 비교하여 스스로 평가하고 DB를 업데이트합니다.")

if st.button("과거 예측 결과 검증하기", use_container_width=True):
    if not user_api_key:
        st.warning("⚠️ 왼쪽 사이드바에 Gemini API 키를 먼저 입력해주세요!")
    else:
        with st.spinner("🕵️ 과거 데이터와 현재 뉴스를 비교하여 예측 정확도를 채점 중입니다..."):
            try:
                # 1. 최신 뉴스 다시 불러오기
                current_news = get_news_headlines()
                
                # 2. 제미나이 모델 세팅 및 검증 리포트 생성
                genai.configure(api_key=user_api_key)
                model = genai.GenerativeModel('gemini-2.5-flash')
                
                verify_prompt = f"""
                당신은 경제 예측의 정확성을 평가하는 AI 감사관입니다.
                아래의 실시간 경제 뉴스를 바탕으로, 우리의 과거 물가 위험도 예측이 실제 시장 상황과 얼마나 잘 맞아떨어졌는지 냉정하게 평가해주세요.
                
                [현재 최신 경제 뉴스]
                {current_news}
                
                [요청 사항]
                1. 현재 시장 상황과 뉴스를 바탕으로 예측 정확도 평가 (잘된 점 / 아쉬운 점)
                2. 예측 당시에는 없었지만 새롭게 등장한 외부 변수(돌발 상황)가 있다면 설명
                """
                
                verify_result = model.generate_content(verify_prompt)
                
                st.info("💡 **AI 감사관의 검증 결과 리포트**")
                st.write(verify_result.text)

                # --- 3. 구글 시트 연동: 마지막 줄 D열에 내용 덮어쓰기 ---
                client = init_connection()
                doc = client.open("AI_Price_DB")
                sheet = doc.sheet1
                
                # 데이터가 적혀있는 가장 마지막 줄의 번호 찾기
                last_row = len(sheet.get_all_values())
                
                # 첫 번째 줄(헤더)이 아니라 실제 데이터가 있을 때만 업데이트
                if last_row > 1:
                    # update_cell(행 번호, 열 번호, 넣을 데이터) -> 4는 D열을 의미함!
                    sheet.update_cell(last_row, 4, verify_result.text)
                    st.success("💾 검증 결과가 구글 시트의 마지막 분석 기록에 성공적으로 업데이트되었습니다!")
                else:
                    st.warning("아직 분석된 데이터가 없어서 검증 결과를 기록할 수 없어요. [분석 시작]부터 먼저 실행해주세요!")
                    
            except Exception as e:
                st.error(f"검증 및 저장 중 에러가 발생했습니다. (상세 에러: {e})")
