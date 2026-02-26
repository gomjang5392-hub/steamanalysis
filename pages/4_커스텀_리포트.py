"""
프롬프트 기반 커스텀 HTML 리포트 생성 페이지
기본 지표 + 유저 활동 / 시계열 히스토리 / 국가별 데이터 / 유저 겹침 선택 가능
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="커스텀 리포트", page_icon="📋", layout="wide")

from analysis.data_loader import (
    load_all_games, filter_games, get_all_tags, get_all_genres,
    get_yearly_trends, get_activity_summary,
    get_history_aggregate, get_country_aggregate,
    get_audience_overlap_top, summarize_full_for_claude,
)
from analysis.claude_client import stream_report, check_api_key
from analysis.prompts import SYSTEM_PROMPT_REPORT, build_custom_report_prompt

# ── 데이터 로드 ───────────────────────────────────────────
games          = load_all_games()
all_tags       = get_all_tags(games, min_count=3)
all_genres     = get_all_genres(games)
all_game_names = sorted({g.get("name","") for g in games if g.get("name")})

all_sales = [g.get("copiesSold") or 0 for g in games]
SALES_MIN = int(min(all_sales))
SALES_MAX = int(max(all_sales))

# ── 헤더 ─────────────────────────────────────────────────
st.title("📋 커스텀 AI 리포트 생성기")
st.caption("데이터 필터 → 조회 항목 선택 → 프롬프트 입력 → HTML 리포트 다운로드")

ok, msg = check_api_key()
if not ok:
    st.error(f"Claude API 키 미설정: {msg}  \n`.env` 파일에 `ANTHROPIC_API_KEY`를 입력하세요.")
    st.stop()

st.divider()

# ════════════════════════════════════════════════════════
# SECTION 1: 데이터 필터
# ════════════════════════════════════════════════════════
st.subheader("① 데이터 필터")

# 게임 바스켓 session_state 초기화
if "game_basket" not in st.session_state:
    st.session_state.game_basket = []

col_f1, col_f2 = st.columns(2)

with col_f1:
    with st.expander("🎭 장르 선택", expanded=True):
        selected_genres = st.multiselect(
            "장르 선택 (미선택 = 전체)",
            options=all_genres, default=[], key="filter_genres")

    with st.expander("🔍 게임 검색 및 선택", expanded=True):
        st.caption("검색 후 클릭 → 목록에 누적 추가 / 다른 게임 검색해서 계속 추가 가능")

        search_query = st.text_input(
            "게임명 검색",
            placeholder="예: Counter-Strike, Minecraft ...",
            key="game_search",
        )

        # 검색 결과에서 추가하는 콜백
        def _add_games():
            for g in st.session_state.get("_game_pick", []):
                if g not in st.session_state.game_basket:
                    st.session_state.game_basket.append(g)
            st.session_state["_game_pick"] = []

        if search_query.strip():
            matched = [
                n for n in all_game_names
                if search_query.lower() in n.lower()
                and n not in st.session_state.game_basket
            ][:50]
            if matched:
                st.multiselect(
                    f"검색 결과 {len(matched)}개 — 클릭하면 바로 아래 목록에 추가",
                    options=matched,
                    default=[],
                    key="_game_pick",
                    on_change=_add_games,
                )
            else:
                st.caption("검색 결과 없음 (이미 모두 선택됐거나 해당 게임 없음)")
        else:
            st.caption("게임명을 입력하면 결과가 표시됩니다.")

        # 바스켓 표시 + 개별 제거
        basket = st.session_state.game_basket
        if basket:
            st.markdown(f"**선택된 게임 ({len(basket)}개)** — 이 게임들만 필터링")

            # 제거용 콜백
            def _remove_games():
                to_remove = set(st.session_state.get("_basket_remove", []))
                st.session_state.game_basket = [
                    g for g in st.session_state.game_basket if g not in to_remove
                ]
                st.session_state["_basket_remove"] = []

            st.multiselect(
                "제거할 게임 선택 (클릭 즉시 제거됨)",
                options=basket,
                default=[],
                key="_basket_remove",
                on_change=_remove_games,
                placeholder="제거할 게임을 여기서 선택...",
            )

            if st.button("🗑 전체 초기화", key="clear_basket"):
                st.session_state.game_basket = []
                st.rerun()
        else:
            st.info("선택된 게임 없음 — 검색 후 클릭해서 추가하세요.")

    selected_games = st.session_state.game_basket

with col_f2:
    with st.expander("🏷 태그 선택", expanded=True):
        selected_tags = st.multiselect(
            "태그 선택 (중복 선택 가능)",
            options=all_tags, default=[], key="filter_tags")

    with st.expander("📅 출시 연도 범위", expanded=True):
        year_min_input, year_max_input = st.slider(
            "출시 연도", 2010, 2025, (2010, 2025), key="filter_year")

    with st.expander("📊 판매량 범위", expanded=True):
        st.caption(f"전체 범위: {SALES_MIN:,} ~ {SALES_MAX:,}장")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            sold_min_input = st.number_input("최소 판매량",
                min_value=SALES_MIN, max_value=SALES_MAX,
                value=SALES_MIN, step=500_000, format="%d", key="sold_min")
        with col_s2:
            sold_max_input = st.number_input("최대 판매량",
                min_value=SALES_MIN, max_value=SALES_MAX,
                value=SALES_MAX, step=500_000, format="%d", key="sold_max")
        st.caption(f"선택 범위: {sold_min_input:,} ~ {sold_max_input:,}장")

st.divider()

# ════════════════════════════════════════════════════════
# SECTION 2: 조회 데이터 항목 선택
# ════════════════════════════════════════════════════════
st.subheader("② 조회할 데이터 항목")

# ── 2-A: 기본 지표 (게임별 필드) ─────────────────────────
st.markdown("**기본 지표** — 게임별 수치 데이터")

BASIC_FIELDS = {
    "판매량":         "누적 판매량 (copies sold)",
    "수익":           "누적 수익 ($)",
    "리뷰점수":       "리뷰 점수 (0~100)",
    "리뷰수":         "리뷰 개수",
    "평균플레이타임": "평균 플레이타임 (시간)",
    "가격":           "현재 판매 가격 ($)",
    "팔로워":         "Steam 팔로워 수",
    "위시리스트":     "위시리스트 수",
    "CCU":            "현재 플레이어 수 (동시접속 추정)",
    "오너수":         "Steam 오너 수 (소유자)",
}

field_cols = st.columns(5)
selected_fields = []
for i, (field, desc) in enumerate(BASIC_FIELDS.items()):
    with field_cols[i % 5]:
        if st.checkbox(field, value=True, help=desc, key=f"field_{field}"):
            selected_fields.append(field)

# ── 2-B: 데이터 카테고리 (집계 분석) ─────────────────────
st.markdown("**데이터 카테고리** — 집계·시계열·분포 분석 (리포트에 차트로 포함)")

cat_cols = st.columns(4)
with cat_cols[0]:
    inc_activity = st.checkbox("👥 유저 활동 지표",
        value=True,
        help="CCU 분포, 플레이타임 구간, 팔로워·위시리스트 통계")
with cat_cols[1]:
    inc_history = st.checkbox("📅 시계열 히스토리",
        value=True,
        help="연도별 판매증분·수익증분·평균CCU·리뷰점수 트렌드")
with cat_cols[2]:
    inc_country = st.checkbox("🌍 국가별 데이터",
        value=True,
        help="국가별 플레이어 비율 (수익 가중 평균)")
with cat_cols[3]:
    inc_overlap = st.checkbox("🔗 유저 겹침 분석",
        value=False,
        help="audienceOverlap 기반 경쟁·연관 게임 상위 목록")

selected_categories = (
    (["유저 활동 지표"] if inc_activity else []) +
    (["시계열 히스토리"] if inc_history  else []) +
    (["국가별 데이터"]  if inc_country  else []) +
    (["유저 겹침"]      if inc_overlap  else [])
)

# 선택 요약 태그
if selected_categories:
    st.caption(f"선택된 카테고리: {' · '.join(selected_categories)}")

st.divider()

# ════════════════════════════════════════════════════════
# SECTION 3: 프롬프트 입력
# ════════════════════════════════════════════════════════
st.subheader("③ 분석 프롬프트 입력")

example_prompts = {
    "시장 기회 분석":  "현재 데이터에서 포화되지 않은 시장 기회를 찾아주세요. 경쟁이 낮으면서 수익성이 높은 틈새 장르나 태그를 식별하고 진입 전략을 제시해주세요.",
    "히트작 공통점":   "데이터에서 상업적으로 성공한 게임들의 공통적인 특성을 분석해주세요. 장르, 가격, 태그, 플레이타임 패턴을 중심으로 성공 공식을 도출해주세요.",
    "인디 개발 전략":  "인디 개발사(소규모 팀, 제한된 예산) 관점에서 현실적인 성공 전략을 분석해주세요. 최적 가격대, 추천 장르, 핵심 마케팅 포인트를 포함해주세요.",
    "투자 ROI 분석":   "장르별 평균 개발 비용 대비 수익률을 추정하고 투자 가치가 높은 게임 유형을 분석해주세요. 위험도와 기대 수익 매트릭스를 제시해주세요.",
    "국가별 시장 전략":"국가별 플레이어 분포를 기반으로 가장 중요한 타겟 시장을 분석하고, 각 시장에 맞는 게임 개발·마케팅 전략을 제시해주세요.",
    "CCU 트렌드 분석": "동시접속자(CCU) 데이터를 중심으로 시장의 유저 참여도 트렌드를 분석해주세요. CCU가 높은 게임의 공통점과 지속적인 유저 유지 전략을 도출해주세요.",
}

ex_cols = st.columns(3)
for i, (label, prompt_text) in enumerate(example_prompts.items()):
    with ex_cols[i % 3]:
        if st.button(label, use_container_width=True, key=f"ex_{i}"):
            st.session_state["user_prompt_input"] = prompt_text

user_prompt = st.text_area(
    "분석 요청 내용",
    value=st.session_state.get("user_prompt_input", ""),
    height=130,
    placeholder="예: 현재 Steam 시장에서 성장 가능성이 높은 장르를 분석하고, 신규 개발사가 진입하기 좋은 틈새 시장을 찾아주세요.",
    key="main_prompt",
)

st.divider()

# ════════════════════════════════════════════════════════
# SECTION 4: 필터 결과 미리보기
# ════════════════════════════════════════════════════════

# 필터 적용
def apply_filters():
    result = games
    if selected_games:
        result = [g for g in result if g.get("name") in selected_games]
    else:
        if selected_genres:
            result = filter_games(result, genres=selected_genres)
        if selected_tags:
            result = filter_games(result, tags=selected_tags)
        result = filter_games(result, year_min=year_min_input, year_max=year_max_input)
        result = [g for g in result
                  if sold_min_input <= (g.get("copiesSold") or 0) <= sold_max_input]

    parts = []
    if selected_games:
        names_str = ", ".join(selected_games[:3])
        parts.append(f"게임: {names_str}{'...' if len(selected_games)>3 else ''}")
    if selected_genres: parts.append(f"장르: {', '.join(selected_genres)}")
    if selected_tags:   parts.append(f"태그: {', '.join(selected_tags)}")
    if year_min_input > 2010 or year_max_input < 2025:
        parts.append(f"출시: {year_min_input}~{year_max_input}년")
    if sold_min_input > SALES_MIN or sold_max_input < SALES_MAX:
        parts.append(f"판매량: {sold_min_input:,}~{sold_max_input:,}장")
    if not parts: parts.append("전체 데이터")
    return result, " | ".join(parts)

filtered, filter_summary = apply_filters()

# ── FIELD_MAP (기본 지표 매핑) ────────────────────────────
FIELD_MAP = {
    "판매량": "copiesSold", "수익": "revenue",
    "리뷰점수": "reviewScore", "리뷰수": "reviews",
    "평균플레이타임": "avgPlaytime", "가격": "price",
    "팔로워": "followers", "위시리스트": "wishlists",
    "CCU": "players", "오너수": "owners",
}

# ── 미리보기 탭 구성 ──────────────────────────────────────
preview_tabs_labels = ["📋 게임 목록"]
if inc_activity: preview_tabs_labels.append("👥 유저 활동")
if inc_history:  preview_tabs_labels.append("📅 시계열")
if inc_country:  preview_tabs_labels.append("🌍 국가별")
if inc_overlap:  preview_tabs_labels.append("🔗 유저 겹침")

with st.expander(
    f"데이터 미리보기 — {len(filtered):,}개 게임 | {filter_summary}",
    expanded=True
):
    if not filtered:
        st.warning("조건에 맞는 게임이 없습니다. 필터를 조정하세요.")
    else:
        preview_tabs = st.tabs(preview_tabs_labels)
        ptab = {l: t for l, t in zip(preview_tabs_labels, preview_tabs)}

        # ── 게임 목록 탭 ─────────────────────────────────
        with ptab["📋 게임 목록"]:
            preview_rows = []
            for g in sorted(filtered, key=lambda x: x.get("revenue") or 0, reverse=True)[:15]:
                ts = g.get("releaseDate") or g.get("firstReleaseDate")
                yr = datetime.fromtimestamp(int(ts)/1000).year if ts else "?"
                row = {"게임명": g.get("name","?"), "출시": yr,
                       "장르": ", ".join((g.get("genres") or [])[:2]),
                       "태그": ", ".join((g.get("tags") or [])[:3])}
                for field in selected_fields:
                    key = FIELD_MAP.get(field, "")
                    val = g.get(key, 0) or 0
                    if field == "수익":
                        row[field] = f"${val/1e6:.1f}M"
                    elif field == "판매량":
                        row[field] = f"{val/1e6:.2f}M"
                    elif isinstance(val, float):
                        row[field] = round(val, 1)
                    else:
                        row[field] = f"{val:,}" if val > 999 else val
                preview_rows.append(row)
            st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
            if len(filtered) > 15:
                st.caption(f"수익 기준 상위 15개 표시 (전체 {len(filtered):,}개)")

        # ── 유저 활동 탭 ─────────────────────────────────
        if inc_activity and "👥 유저 활동" in ptab:
            with ptab["👥 유저 활동"]:
                activity = get_activity_summary(filtered)

                # KPI 행
                a_cols = st.columns(5)
                kpi_items = [
                    ("CCU 평균",      "players_ccu",    ""),
                    ("리뷰점수 평균", "review_score",   ""),
                    ("플레이타임 평균","avg_playtime",  "h"),
                    ("팔로워 평균",   "followers",      ""),
                    ("위시리스트 평균","wishlists",     ""),
                ]
                for i, (label, key, unit) in enumerate(kpi_items):
                    val = activity.get(key, {}).get("avg", 0)
                    a_cols[i].metric(label, f"{val:,.0f}{unit}")

                col1, col2, col3 = st.columns(3)

                with col1:
                    # CCU 분포
                    ccu_vals = [g.get("players") or 0 for g in filtered if (g.get("players") or 0) > 0]
                    if ccu_vals:
                        fig = go.Figure(go.Histogram(
                            x=[v/1000 for v in ccu_vals], nbinsx=25,
                            marker_color="rgba(79,195,247,0.8)"))
                        fig.update_layout(xaxis_title="CCU (천명)", yaxis_title="게임 수",
                            height=250, margin=dict(t=30,b=30), title="CCU 분포",
                            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                            font=dict(color="white"))
                        st.plotly_chart(fig, use_container_width=True)

                with col2:
                    # 플레이타임 구간 비율
                    bucket_sums = {}; cnt = 0
                    for g in filtered:
                        dist = (g.get("playtimeData") or {}).get("distribution") or {}
                        if dist:
                            for b, pct in dist.items():
                                bucket_sums[b] = bucket_sums.get(b, 0) + pct
                            cnt += 1
                    if bucket_sums and cnt:
                        order = ["0-1h","1-2h","2-5h","5-10h","10-20h","20-50h","50-100h","100-500h"]
                        bkts = [b for b in order if b in bucket_sums]
                        avgs = [round(bucket_sums[b]/cnt, 1) for b in bkts]
                        fig = go.Figure(go.Bar(x=bkts, y=avgs,
                                               marker_color="rgba(255,183,77,0.8)"))
                        fig.update_layout(xaxis_title="플레이타임 구간",
                            yaxis_title="비율 (%)", height=250, margin=dict(t=30,b=30),
                            title="플레이타임 구간 분포",
                            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                            font=dict(color="white"))
                        st.plotly_chart(fig, use_container_width=True)

                with col3:
                    # 리뷰점수 분포
                    scores = [g.get("reviewScore") or 0 for g in filtered if g.get("reviewScore")]
                    if scores:
                        fig = go.Figure(go.Histogram(x=scores, nbinsx=20,
                                                      marker_color="rgba(165,214,167,0.8)"))
                        fig.update_layout(xaxis_title="리뷰 점수", yaxis_title="게임 수",
                            height=250, margin=dict(t=30,b=30), title="리뷰점수 분포",
                            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                            font=dict(color="white"))
                        st.plotly_chart(fig, use_container_width=True)

                # CCU 상위 10
                top10 = sorted(filtered, key=lambda x: x.get("players") or 0, reverse=True)[:10]
                rows = [{"게임명": g.get("name",""), "CCU": f"{(g.get('players') or 0):,}",
                         "플레이타임(h)": round(g.get("avgPlaytime") or 0, 1),
                         "리뷰점수": g.get("reviewScore") or 0,
                         "팔로워": f"{(g.get('followers') or 0):,}",
                         "위시리스트": f"{(g.get('wishlists') or 0):,}"}
                        for g in top10]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # ── 시계열 탭 ────────────────────────────────────
        if inc_history and "📅 시계열" in ptab:
            with ptab["📅 시계열"]:
                hist = get_history_aggregate(filtered, freq="yearly")
                if not hist:
                    st.info("히스토리 데이터가 없습니다.")
                else:
                    df_h = pd.DataFrame([{"period": p, **v} for p, v in hist.items()])

                    h_tabs = st.tabs(["수익·판매", "CCU", "점수·플레이타임", "가격·팔로워"])

                    with h_tabs[0]:
                        fig = go.Figure()
                        fig.add_trace(go.Bar(x=df_h.period, y=df_h.revenue_inc/1e6,
                            name="수익증분(백만$)", marker_color="rgba(79,195,247,0.8)"))
                        fig.add_trace(go.Scatter(x=df_h.period, y=df_h.sales_inc/1e6,
                            name="판매증분(백만장)", yaxis="y2",
                            line=dict(color="#ff7043", width=2), mode="lines+markers"))
                        fig.update_layout(height=300,
                            yaxis=dict(title="수익(백만$)"),
                            yaxis2=dict(title="판매(백만장)", overlaying="y", side="right"),
                            legend=dict(orientation="h", y=1.12),
                            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                            font=dict(color="white"))
                        st.plotly_chart(fig, use_container_width=True)

                    with h_tabs[1]:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=df_h.period, y=df_h.avg_ccu,
                            name="평균 CCU", fill="tozeroy",
                            fillcolor="rgba(79,195,247,0.15)",
                            line=dict(color="#4fc3f7", width=2)))
                        fig.add_trace(go.Scatter(x=df_h.period, y=df_h.max_ccu,
                            name="최대 CCU", line=dict(color="#ff7043", width=1, dash="dot")))
                        fig.update_layout(height=300, yaxis_title="CCU",
                            legend=dict(orientation="h", y=1.12),
                            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                            font=dict(color="white"))
                        st.plotly_chart(fig, use_container_width=True)

                    with h_tabs[2]:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=df_h.period, y=df_h.avg_score,
                            name="평균점수", line=dict(color="#a5d6a7", width=2),
                            mode="lines+markers"))
                        fig.add_trace(go.Bar(x=df_h.period, y=df_h.avg_playtime,
                            name="평균플레이타임(h)", yaxis="y2",
                            marker_color="rgba(255,183,77,0.5)"))
                        fig.update_layout(height=300,
                            yaxis=dict(title="리뷰점수"),
                            yaxis2=dict(title="플레이타임(h)", overlaying="y", side="right"),
                            legend=dict(orientation="h", y=1.12),
                            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                            font=dict(color="white"))
                        st.plotly_chart(fig, use_container_width=True)

                    with h_tabs[3]:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=df_h.period, y=df_h.avg_price,
                            name="평균가격($)", line=dict(color="#ce93d8", width=2)))
                        fig.add_trace(go.Scatter(x=df_h.period, y=df_h.avg_followers,
                            name="평균팔로워", yaxis="y2",
                            line=dict(color="#80cbc4", width=2)))
                        fig.update_layout(height=300,
                            yaxis=dict(title="평균가격($)"),
                            yaxis2=dict(title="팔로워", overlaying="y", side="right"),
                            legend=dict(orientation="h", y=1.12),
                            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                            font=dict(color="white"))
                        st.plotly_chart(fig, use_container_width=True)

                    # 전체 수치 테이블
                    with st.expander("전체 수치 보기"):
                        df_show = df_h.rename(columns={
                            "period":"기간","sales_inc":"판매증분","revenue_inc":"수익증분($)",
                            "avg_ccu":"평균CCU","max_ccu":"최대CCU","total_ccu":"총CCU",
                            "avg_score":"평균점수","avg_playtime":"플레이타임(h)",
                            "avg_price":"평균가격($)","avg_followers":"평균팔로워",
                            "avg_wishlists":"평균위시리스트","total_games":"게임수"})
                        st.dataframe(df_show, use_container_width=True, hide_index=True)

        # ── 국가별 탭 ────────────────────────────────────
        if inc_country and "🌍 국가별" in ptab:
            with ptab["🌍 국가별"]:
                weight = st.radio("가중 기준", ["revenue","sales","equal"], horizontal=True,
                    format_func=lambda x: {"revenue":"수익가중","sales":"판매가중","equal":"동일가중"}.get(x,x),
                    key="prev_country_weight")
                countries = get_country_aggregate(filtered, weight_by=weight)
                if countries:
                    names = list(countries.keys())[:20]
                    pcts  = [countries[n] for n in names]
                    col1, col2 = st.columns(2)
                    with col1:
                        fig = go.Figure(go.Bar(
                            x=pcts[::-1], y=names[::-1], orientation="h",
                            marker_color="rgba(79,195,247,0.8)"))
                        fig.update_layout(xaxis_title="비율 (%)", height=460,
                            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                            font=dict(color="white"))
                        st.plotly_chart(fig, use_container_width=True)
                    with col2:
                        fig = go.Figure(go.Pie(
                            labels=names[:10], values=pcts[:10],
                            hole=0.35, textinfo="label+percent"))
                        fig.update_layout(height=460, paper_bgcolor="#0e1117",
                            font=dict(color="white"), showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)

        # ── 유저 겹침 탭 ─────────────────────────────────
        if inc_overlap and "🔗 유저 겹침" in ptab:
            with ptab["🔗 유저 겹침"]:
                st.caption(
                    "**추정 공유 유저** = 유저 겹침 지수(Link) × 외부 게임 판매량 "
                    "— 실제 접근 가능한 유저 규모를 반영합니다."
                )
                overlaps = get_audience_overlap_top(filtered, top_n=30, sort_by="reach_score")
                if overlaps:
                    ol_rows = []
                    for o in overlaps:
                        reach_m = o["reach_score"] / 1_000_000
                        copies_m = o["copies_sold"] / 1_000_000
                        ol_rows.append({
                            "게임명": o["name"],
                            "유저 겹침 지수 (Link)": f"{o['avg_link']:.3f}",
                            "외부 게임 판매량(M)": f"{copies_m:.1f}",
                            "추정 공유 유저(M)": f"{reach_m:.2f}",
                            "겹침 광범위성": f"{o['overlap_pct']}%",
                            "장르": ", ".join(o["genres"][:3]) if o["genres"] else "-",
                        })
                    st.dataframe(pd.DataFrame(ol_rows), use_container_width=True, hide_index=True)

                    # 버블 차트
                    import math as _math
                    bubble_data = [o for o in overlaps if o["copies_sold"] > 0]
                    if bubble_data:
                        max_reach = max(o["reach_score"] for o in bubble_data) or 1
                        fig_b = go.Figure(go.Scatter(
                            x=[o["avg_link"] for o in bubble_data],
                            y=[o["copies_sold"] / 1_000_000 for o in bubble_data],
                            mode="markers+text",
                            text=[o["name"][:20] for o in bubble_data],
                            textposition="top center",
                            textfont=dict(size=9, color="rgba(255,255,255,0.7)"),
                            marker=dict(
                                size=[max(8, min(50, o["reach_score"] / max_reach * 50)) for o in bubble_data],
                                color=[o["avg_link"] for o in bubble_data],
                                colorscale="YlOrRd", showscale=True,
                                colorbar=dict(title="Link"),
                                line=dict(width=1, color="rgba(255,255,255,0.3)"),
                            ),
                            customdata=[[
                                o["name"],
                                f"{o['avg_link']:.3f}",
                                f"{o['copies_sold']/1e6:.1f}M",
                                f"{o['reach_score']/1e6:.2f}M",
                                f"{o['overlap_pct']}%",
                            ] for o in bubble_data],
                            hovertemplate=(
                                "<b>%{customdata[0]}</b><br>"
                                "Link: %{customdata[1]}<br>"
                                "판매량: %{customdata[2]}<br>"
                                "추정 공유 유저: %{customdata[3]}<br>"
                                "겹침 광범위성: %{customdata[4]}<extra></extra>"
                            ),
                        ))
                        fig_b.update_layout(
                            xaxis_title="유저 겹침 지수 (Link)",
                            yaxis_title="외부 게임 판매량 (백만 장)",
                            yaxis_type="log", height=480,
                            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                            font=dict(color="white"),
                        )
                        st.plotly_chart(fig_b, use_container_width=True)
                else:
                    st.info("겹침 데이터가 부족합니다.")

st.divider()

# ════════════════════════════════════════════════════════
# SECTION 5: HTML 리포트 생성
# ════════════════════════════════════════════════════════
st.subheader("④ HTML 리포트 생성")

# 포함 데이터 요약 뱃지
if selected_categories:
    badge_md = " · ".join(f"`{c}`" for c in selected_categories)
    st.caption(f"리포트에 포함될 추가 데이터: {badge_md}")
else:
    st.caption("리포트에 포함될 데이터: 기본 지표만")

# ── ⚙️ 프롬프트 고급 설정 ─────────────────────────────────
with st.expander("⚙️ 프롬프트 고급 설정", expanded=False):
    st.caption(
        "Claude에게 전달되는 시스템 프롬프트와 HTML 출력 지침을 직접 편집할 수 있습니다. "
        "기본값으로 되돌리려면 초기화 버튼을 누르세요."
    )

    col_sp, col_reset_sp = st.columns([5, 1])
    with col_sp:
        st.markdown("**시스템 프롬프트** — Claude의 역할·행동 방식 정의")
    with col_reset_sp:
        if st.button("초기화", key="reset_sys"):
            st.session_state.pop("custom_system_prompt", None)
            st.rerun()

    custom_system_prompt = st.text_area(
        "시스템 프롬프트",
        value=st.session_state.get("custom_system_prompt", SYSTEM_PROMPT_REPORT),
        height=200,
        key="sys_prompt_input",
        label_visibility="collapsed",
    )
    st.session_state["custom_system_prompt"] = custom_system_prompt

    st.divider()

    _DEFAULT_HTML_REQUIREMENTS = """\
- <!DOCTYPE html> 부터 시작하는 완전한 HTML 문서
- 전문 비즈니스 다크 테마 디자인 (배경 #0f172a, 카드 #1e293b, 강조 #38bdf8)
- Chart.js (https://cdn.jsdelivr.net/npm/chart.js) 활용한 인터랙티브 차트:
  * 장르별 수익 도넛 차트
  * 연도별 트렌드 라인 차트 (yearly_trends 있을 시)
  * 상위 10개 게임 수평 바 차트
  * 공통 태그 Top 15 바 차트
- 최상단: 리포트 제목 + 생성 날짜 + 필터 조건 요약
- Executive Summary 섹션 (핵심 인사이트 5개)
- KPI 카드 행 (aggregate_stats 기반)
- 차트 섹션
- 상위 30개 게임 상세 테이블
- 주요 발견사항 및 전략적 시사점 섹션
- 모든 텍스트는 한국어
- 리포트 제목은 분석 내용을 반영해 자동 생성"""

    col_hr, col_reset_hr = st.columns([5, 1])
    with col_hr:
        st.markdown("**HTML 출력 지침** — 차트 종류·디자인·섹션 구성 등")
    with col_reset_hr:
        if st.button("초기화", key="reset_html"):
            st.session_state.pop("custom_html_requirements", None)
            st.rerun()

    custom_html_requirements = st.text_area(
        "HTML 출력 지침",
        value=st.session_state.get("custom_html_requirements", _DEFAULT_HTML_REQUIREMENTS),
        height=200,
        key="html_req_input",
        label_visibility="collapsed",
    )
    st.session_state["custom_html_requirements"] = custom_html_requirements

col_btn1, col_btn2, _ = st.columns([1, 1, 4])
with col_btn1:
    generate_btn = st.button("🚀 리포트 생성", type="primary",
        use_container_width=True,
        disabled=len(filtered) == 0 or not user_prompt.strip())

if not user_prompt.strip():
    st.caption("⚠️ 프롬프트를 입력하면 생성 버튼이 활성화됩니다.")
if not filtered:
    st.caption("⚠️ 필터 조건에 맞는 게임이 없습니다.")

if generate_btn:
    # 최대 200개로 제한 (프롬프트 토큰 관리)
    if len(filtered) > 200:
        st.info(f"데이터가 많아 수익 기준 상위 200개로 분석합니다. (전체: {len(filtered)}개)")
        analysis_games = sorted(filtered, key=lambda x: x.get("revenue") or 0, reverse=True)[:200]
    else:
        analysis_games = filtered

    # 적용할 시스템 프롬프트·HTML 지침 (고급 설정 반영)
    active_system_prompt = st.session_state.get("custom_system_prompt", SYSTEM_PROMPT_REPORT)
    active_html_req = st.session_state.get("custom_html_requirements", None)

    # 기본 리포트 프롬프트
    yearly = get_yearly_trends(analysis_games)
    base_prompt = build_custom_report_prompt(
        user_prompt=user_prompt,
        filtered_games=analysis_games,
        selected_fields=selected_fields,
        filter_summary=filter_summary,
        yearly_trends=yearly,
    )

    # HTML 지침이 커스텀으로 변경된 경우 치환
    if active_html_req:
        _default_req_start = "## HTML 보고서 요구사항"
        _default_req_end = "오직 HTML 코드만 반환하세요. 앞뒤 설명 없이 <!DOCTYPE html>로 시작하세요."
        if _default_req_start in base_prompt:
            before_req = base_prompt[:base_prompt.index(_default_req_start)]
            base_prompt = (
                f"{before_req}"
                f"## HTML 보고서 요구사항\n{active_html_req}\n\n"
                f"오직 HTML 코드만 반환하세요. 앞뒤 설명 없이 <!DOCTYPE html>로 시작하세요."
            )

    # 카테고리 추가 데이터 삽입
    if selected_categories:
        extra_summary = summarize_full_for_claude(
            analysis_games, selected_categories, max_games=20)
        base_prompt = base_prompt.replace(
            "오직 HTML 코드만 반환하세요",
            f"## 추가 분석 데이터\n{extra_summary}\n\n오직 HTML 코드만 반환하세요"
        )

    status = st.empty()
    status.info("Claude AI가 HTML 리포트를 생성 중입니다... (60~90초 소요)")
    prog = st.progress(0)

    try:
        chunks = []
        for i, chunk in enumerate(stream_report(base_prompt, active_system_prompt)):
            chunks.append(chunk)
            prog.progress(min(i / 300, 0.95))

        full_html = "".join(chunks)
        prog.progress(1.0)
        status.success(f"리포트 생성 완료! ({len(full_html):,} 글자)")

        # HTML 정제
        if "<!DOCTYPE html>" in full_html:
            full_html = full_html[full_html.index("<!DOCTYPE html>"):]
        elif "<html" in full_html:
            full_html = full_html[full_html.index("<html"):]

        st.session_state["generated_html"]   = full_html
        st.session_state["generated_at"]     = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.session_state["report_filter"]    = filter_summary
        st.session_state["report_categories"]= selected_categories

    except Exception as e:
        prog.empty()
        status.error(f"리포트 생성 실패: {e}")

# ════════════════════════════════════════════════════════
# SECTION 6: 리포트 표시 + 다운로드
# ════════════════════════════════════════════════════════
if "generated_html" in st.session_state:
    full_html   = st.session_state["generated_html"]
    gen_at      = st.session_state.get("generated_at", "")
    rpt_filter  = st.session_state.get("report_filter", "")
    rpt_cats    = st.session_state.get("report_categories", [])

    st.divider()
    st.subheader("⑤ 생성된 리포트")

    dl1, dl2, _ = st.columns([1, 1, 4])
    with dl1:
        st.download_button(
            "⬇️ HTML 다운로드",
            data=full_html.encode("utf-8"),
            file_name=f"steam_report_{gen_at}.html",
            mime="text/html",
            use_container_width=True,
            type="primary",
        )
    with dl2:
        if st.button("🗑 초기화", use_container_width=True):
            del st.session_state["generated_html"]
            st.rerun()

    meta_parts = [f"필터: {rpt_filter}"]
    if rpt_cats:
        meta_parts.append(f"포함 데이터: {', '.join(rpt_cats)}")
    st.caption("  |  ".join(meta_parts))

    st.divider()
    tab_prev, tab_src = st.tabs(["🖥 미리보기", "📄 HTML 소스"])
    with tab_prev:
        components.html(full_html, height=950, scrolling=True)
    with tab_src:
        st.code(full_html, language="html")
