"""
게임 산업 분석 서비스 - 랜딩 페이지
streamlit run analysis_app.py
"""
import os
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Steam 게임 시장 분석 서비스",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS 커스터마이징
st.markdown("""
<style>
.metric-card {
    background: #1e2a3a;
    border-radius: 8px;
    padding: 16px;
    text-align: center;
}
.big-num { font-size: 2rem; font-weight: bold; color: #4fc3f7; }
.sub-text { color: #9e9e9e; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

# ── 사이드바 ──────────────────────────────────────────────
with st.sidebar:
    st.title("🎮 Steam 분석 서비스")
    st.divider()

    # API 키 상태
    from analysis.claude_client import check_api_key
    ok, msg = check_api_key()
    if ok:
        st.success(f"✅ Claude API: {msg}")
    else:
        st.error(f"❌ Claude API: {msg}")
        st.info("`.env` 파일에 `ANTHROPIC_API_KEY`를 설정하세요.")

    st.divider()
    st.markdown("**페이지 목록**")
    st.page_link("pages/1_장르_KPI_트렌드.py", label="📈 장르 KPI 트렌드", icon="📈")
    st.page_link("pages/2_시장_현황_분석.py", label="🏪 시장 현황 분석", icon="🏪")
    st.page_link("pages/3_개발_가이드.py", label="🛠 개발 전략 가이드", icon="🛠")
    st.page_link("pages/4_커스텀_리포트.py", label="📋 커스텀 AI 리포트", icon="📋")

# ── 메인 ─────────────────────────────────────────────────
st.title("🎮 Steam 게임 시장 분석 서비스")
st.caption("Gamalytic API 수집 데이터 × Claude AI 심층 분석")
st.divider()

# 데이터 로드
from analysis.data_loader import load_all_games, get_genre_stats, get_yearly_trends, _release_year

with st.spinner("데이터 로딩 중..."):
    games = load_all_games()

if not games:
    st.error("게임 데이터를 찾을 수 없습니다. `raw_data/games/` 폴더를 확인하세요.")
    st.stop()

# ── 주요 지표 카드 ────────────────────────────────────────
total_games = len(games)
total_revenue = sum(g.get("revenue") or 0 for g in games)
total_sales = sum(g.get("copiesSold") or 0 for g in games)
hit_count = sum(1 for g in games if (g.get("copiesSold") or 0) >= 1_000_000)

release_years = [_release_year(g) for g in games if _release_year(g)]
year_min = min(release_years) if release_years else 0
year_max = max(release_years) if release_years else 0

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("수집 게임 수", f"{total_games:,}개")
with col2:
    st.metric("총 수익 합계", f"${total_revenue / 1e9:.1f}B")
with col3:
    st.metric("총 판매량", f"{total_sales / 1e9:.2f}B장")
with col4:
    st.metric("히트작 (100만장+)", f"{hit_count}개")
with col5:
    st.metric("데이터 기간", f"{year_min}~{year_max}")

st.divider()

# ── 서비스 소개 ───────────────────────────────────────────
st.subheader("📊 분석 서비스 소개")

col_a, col_b, col_c = st.columns(3)

with col_a:
    st.markdown("""
    ### 📈 장르 KPI 트렌드
    특정 장르·태그의 연도별 수익·판매량 흐름을 시각화하고,
    Claude AI가 시장 경쟁 구도와 투자 가치를 분석합니다.

    **주요 기능**
    - 연도별 수익·판매량 선 그래프
    - 상위 게임 수익 비교
    - 출시연도 vs 수익 산점도
    - AI 심층 트렌드 분석
    """)
    if st.button("→ 장르 KPI 트렌드 분석", use_container_width=True):
        st.switch_page("pages/1_장르_KPI_트렌드.py")

with col_b:
    st.markdown("""
    ### 🏪 시장 현황 분석
    특정 기간 신규 출시 게임의 시장 추세를 파악하고,
    월별 출시 패턴과 장르별 수익 분포를 분석합니다.

    **주요 기능**
    - 월별 출시 게임 수 추세
    - 장르별 수익 비중 파이차트
    - 판매량 분포 히스토그램
    - AI 시장 현황 분석
    """)
    if st.button("→ 시장 현황 분석", use_container_width=True):
        st.switch_page("pages/2_시장_현황_분석.py")

with col_c:
    st.markdown("""
    ### 🛠 개발 전략 가이드
    목표 장르·규모에 맞는 게임 개발 전략을 제안하고,
    성공작 벤치마크와 최적 가격 전략을 제시합니다.

    **주요 기능**
    - 벤치마크 성공작 테이블
    - 가격대별 수익 박스플롯
    - 성공 공통 태그 분석
    - AI 맞춤 개발 전략 가이드
    """)
    if st.button("→ 개발 전략 가이드", use_container_width=True):
        st.switch_page("pages/3_개발_가이드.py")

st.divider()

col_d, col_empty = st.columns([1, 2])
with col_d:
    st.markdown("""
    ### 📋 커스텀 AI 리포트
    원하는 분석을 자유 프롬프트로 입력하면
    Claude AI가 완전한 HTML 리포트를 자동 생성합니다.

    **주요 기능**
    - 장르·게임·태그·판매량 복합 필터
    - 게임 이름 검색 + 선택
    - 조회 데이터 항목 선택 (DAU, CCU, 판매량 등)
    - 자유 프롬프트 → HTML 리포트 생성
    - HTML 파일 다운로드
    """)
    if st.button("→ 커스텀 AI 리포트 생성", use_container_width=True):
        st.switch_page("pages/4_커스텀_리포트.py")

st.divider()

# ── 장르별 현황 미리보기 ──────────────────────────────────
st.subheader("🎯 장르별 시장 현황 (상위 10개)")

genre_stats = get_genre_stats(games)
import pandas as pd

genre_rows = []
for genre, stat in list(genre_stats.items())[:10]:
    genre_rows.append({
        "장르": genre,
        "게임 수": stat["game_count"],
        "평균 수익 ($)": f"${stat['avg_revenue']:,.0f}",
        "평균 판매량": f"{stat['avg_sales']:,.0f}장",
        "평균 리뷰 점수": f"{stat['avg_score']:.1f}/100",
        "총 수익 ($)": f"${stat['total_revenue']:,.0f}",
    })

st.dataframe(
    pd.DataFrame(genre_rows),
    use_container_width=True,
    hide_index=True,
)

# ── 연도별 트렌드 미리보기 ────────────────────────────────
st.subheader("📅 연도별 시장 성장 추세")

import plotly.graph_objects as go

yearly = get_yearly_trends(games)
years = [yr for yr in sorted(yearly.keys()) if yr >= 2015]
revenues_by_year = [yearly[yr]["revenue"] / 1e6 for yr in years]
sales_by_year = [yearly[yr]["sales"] / 1e6 for yr in years]

fig = go.Figure()
fig.add_trace(go.Bar(
    x=years,
    y=revenues_by_year,
    name="연도별 수익 증분 (백만$)",
    marker_color="#4fc3f7",
    yaxis="y",
))
fig.add_trace(go.Scatter(
    x=years,
    y=sales_by_year,
    name="연도별 판매 증분 (백만장)",
    line=dict(color="#ff7043", width=2),
    mode="lines+markers",
    yaxis="y2",
))
fig.update_layout(
    title="전체 데이터셋 연도별 수익·판매량 트렌드",
    xaxis_title="연도",
    yaxis=dict(title="수익 증분 (백만 $)", showgrid=False),
    yaxis2=dict(title="판매 증분 (백만 장)", overlaying="y", side="right"),
    legend=dict(orientation="h", y=1.1),
    height=380,
    plot_bgcolor="#0e1117",
    paper_bgcolor="#0e1117",
    font=dict(color="white"),
)
st.plotly_chart(fig, use_container_width=True)

# ── 푸터 ─────────────────────────────────────────────────
st.divider()
st.caption(
    f"데이터: Gamalytic API (수집 기준: 누적 판매량 100만장+) | "
    f"마지막 업데이트: 2026-02-25 | "
    f"Powered by Claude claude-opus-4-6"
)
