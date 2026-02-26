"""
장르/태그별 KPI 트렌드 + 유저 활동 + 시계열 히스토리 + 국가별 분포 페이지
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="장르 KPI 트렌드", page_icon="📈", layout="wide")

from analysis.data_loader import (
    load_all_games, filter_games,
    get_yearly_trends, get_top_games,
    get_genre_stats, get_tag_stats,
    get_all_tags, get_all_genres,
    get_history_aggregate, get_history_for_game,
    get_country_aggregate, get_activity_summary,
    get_audience_overlap_top, summarize_full_for_claude,
    _release_year, _parse_field,
)
from analysis.claude_client import stream_analysis, check_api_key
from analysis.prompts import SYSTEM_PROMPT, build_genre_trend_prompt

# ── 데이터 로드 ───────────────────────────────────────────
games = load_all_games()
all_tags  = get_all_tags(games, min_count=5)
all_genres = get_all_genres(games)

# ── 사이드바 ──────────────────────────────────────────────
with st.sidebar:
    st.title("📈 장르 KPI 트렌드")

    analysis_type = st.radio("분석 기준", ["태그", "장르"], horizontal=True)

    if analysis_type == "태그":
        popular = ["FPS","RPG","Battle Royale","Survival","Open World",
                   "Multiplayer","Strategy","Horror","Puzzle","Platformer",
                   "Simulation","Racing","MOBA","Roguelike","Soulslike","Sandbox"]
        defaults = [t for t in popular if t in all_tags][:2]
        selected = st.multiselect("태그 선택 (최대 5개)", all_tags,
                                  default=defaults, max_selections=5)
    else:
        selected = st.multiselect("장르 선택 (최대 5개)", all_genres,
                                  default=all_genres[:2] if all_genres else [],
                                  max_selections=5)

    st.divider()
    year_min, year_max = st.slider("출시 연도 범위", 2010, 2025, (2015, 2025))
    reviews_min = st.number_input("최소 리뷰 수", 0, value=0, step=1000)

    st.divider()
    st.markdown("**조회 데이터 항목 선택**")
    show_sales      = st.checkbox("판매·수익 트렌드",    value=True)
    show_activity   = st.checkbox("유저 활동 지표",       value=True)
    show_history    = st.checkbox("시계열 히스토리",      value=True)
    show_country    = st.checkbox("국가별 분포",          value=True)
    show_overlap    = st.checkbox("유저 겹침 분석",       value=False)
    show_game_table = st.checkbox("상세 게임 테이블",     value=True)

    selected_metrics = []
    if show_activity: selected_metrics.append("유저 활동 지표")
    if show_history:  selected_metrics.append("시계열 히스토리")
    if show_country:  selected_metrics.append("국가별 데이터")
    if show_overlap:  selected_metrics.append("유저 겹침")

    st.divider()
    user_question = st.text_area("AI 추가 질문",
        placeholder="예: 이 장르에서 인디 게임이 성공하려면?", height=90)

    ok, _ = check_api_key()
    if ok:
        st.success("✅ Claude 연결됨")
    else:
        st.warning("⚠️ Claude API 키 미설정")

# ── 메인 ─────────────────────────────────────────────────
st.title("📈 장르·태그 KPI 트렌드 분석")

if not selected:
    st.info("사이드바에서 태그 또는 장르를 선택하세요.")
    st.stop()

# 필터링
kw = dict(tags=selected) if analysis_type == "태그" else dict(genres=selected)
filtered = filter_games(games, **kw,
                        year_min=year_min, year_max=year_max,
                        reviews_min=reviews_min if reviews_min > 0 else None)

selected_label = ", ".join(selected)
st.caption(f"**{selected_label}** | 기간: {year_min}~{year_max} | **{len(filtered):,}개** 게임")

if not filtered:
    st.warning("조건에 맞는 게임이 없습니다.")
    st.stop()

# ── 요약 KPI 카드 ─────────────────────────────────────────
revenues  = [g.get("revenue") or 0 for g in filtered]
sales_lst = [g.get("copiesSold") or 0 for g in filtered]
scores    = [g.get("reviewScore") or 0 for g in filtered if g.get("reviewScore")]
ccus      = [g.get("players") or 0 for g in filtered if g.get("players")]
playtimes = [g.get("avgPlaytime") or 0 for g in filtered if g.get("avgPlaytime")]
wishlists = [g.get("wishlists") or 0 for g in filtered if g.get("wishlists")]

c1,c2,c3,c4,c5,c6 = st.columns(6)
c1.metric("게임 수",        f"{len(filtered):,}개")
c2.metric("평균 수익",      f"${(sum(revenues)/len(revenues)/1e6):.1f}M" if revenues else "-")
c3.metric("평균 판매량",    f"{(sum(sales_lst)/len(sales_lst)/1e6):.2f}M장" if sales_lst else "-")
c4.metric("평균 리뷰 점수", f"{(sum(scores)/len(scores)):.1f}" if scores else "-")
c5.metric("평균 CCU",       f"{(sum(ccus)/len(ccus)):,.0f}" if ccus else "-")
c6.metric("평균 플레이타임",f"{(sum(playtimes)/len(playtimes)):.0f}h" if playtimes else "-")

st.divider()

# ══════════════════════════════════════════════════════════
# 탭 구성
# ══════════════════════════════════════════════════════════
tab_labels = []
if show_sales:    tab_labels.append("💰 판매·수익")
if show_activity: tab_labels.append("👥 유저 활동")
if show_history:  tab_labels.append("📅 시계열 히스토리")
if show_country:  tab_labels.append("🌍 국가별 분포")
if show_overlap:  tab_labels.append("🔗 유저 겹침")
if show_game_table: tab_labels.append("📋 게임 목록")
tab_labels.append("🤖 AI 분석")

tabs = st.tabs(tab_labels)
tab_map = {label: tab for label, tab in zip(tab_labels, tabs)}

# ── 탭: 판매·수익 ─────────────────────────────────────────
if show_sales and "💰 판매·수익" in tab_map:
    with tab_map["💰 판매·수익"]:
        st.subheader("연도별 수익·판매량 트렌드")

        yearly = get_yearly_trends(filtered)
        years  = [yr for yr in sorted(yearly.keys()) if yr >= year_min]
        y_rev  = [yearly[yr]["revenue"] / 1e6 for yr in years]
        y_sal  = [yearly[yr]["sales"] / 1e6 for yr in years]
        y_cnt  = [yearly[yr]["game_count"] for yr in years]

        fig = go.Figure()
        fig.add_trace(go.Bar(x=years, y=y_rev, name="수익 증분 (백만$)",
                             marker_color="rgba(79,195,247,0.8)"))
        fig.add_trace(go.Scatter(x=years, y=y_sal, name="판매 증분 (백만장)",
                                 line=dict(color="#ff7043", width=2),
                                 mode="lines+markers", yaxis="y2"))
        fig.add_trace(go.Scatter(x=years, y=y_cnt, name="활성 게임 수",
                                 line=dict(color="#a5d6a7", width=1, dash="dot"),
                                 mode="lines+markers", yaxis="y2"))
        fig.update_layout(
            yaxis=dict(title="수익 증분 (백만$)"),
            yaxis2=dict(title="판매/게임 수", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.12), height=380,
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="white"))
        st.plotly_chart(fig, use_container_width=True)

        # 상위 10개 수익 + 산점도
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("상위 10개 게임 수익")
            top10 = get_top_games(filtered, 10, "revenue")
            fig2 = go.Figure(go.Bar(
                x=[(g.get("revenue") or 0)/1e6 for g in top10][::-1],
                y=[g.get("name","")[:28] for g in top10][::-1],
                orientation="h", marker_color="rgba(255,183,77,0.85)"))
            fig2.update_layout(xaxis_title="수익 (백만$)", height=340,
                plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="white"))
            st.plotly_chart(fig2, use_container_width=True)

        with col_r:
            st.subheader("출시연도 vs 수익 (버블=판매량)")
            rows = []
            for g in filtered:
                ts = g.get("releaseDate") or g.get("firstReleaseDate")
                if not ts: continue
                rows.append({"name": g.get("name",""), "year": datetime.fromtimestamp(int(ts)/1000).year,
                             "rev_m": (g.get("revenue") or 0)/1e6,
                             "sal_m": (g.get("copiesSold") or 0)/1e6,
                             "score": g.get("reviewScore") or 0})
            if rows:
                df = pd.DataFrame(rows)
                fig3 = px.scatter(df, x="year", y="rev_m", size="sal_m", color="score",
                                  hover_name="name", color_continuous_scale="Viridis",
                                  labels={"year":"출시연도","rev_m":"수익(백만$)","score":"리뷰점수"},
                                  size_max=40)
                fig3.update_layout(height=340, plot_bgcolor="#0e1117",
                    paper_bgcolor="#0e1117", font=dict(color="white"))
                st.plotly_chart(fig3, use_container_width=True)

# ── 탭: 유저 활동 지표 ────────────────────────────────────
if show_activity and "👥 유저 활동" in tab_map:
    with tab_map["👥 유저 활동"]:
        st.subheader("유저 활동 지표 분포")
        activity = get_activity_summary(filtered)

        # 지표 요약 카드
        metric_cols = st.columns(4)
        labels = {
            "players_ccu": ("CCU (동시접속)", ""),
            "avg_playtime": ("평균 플레이타임", "h"),
            "followers": ("팔로워", ""),
            "wishlists": ("위시리스트", ""),
        }
        for i, (key, (label, unit)) in enumerate(labels.items()):
            st_data = activity.get(key, {})
            metric_cols[i].metric(
                f"{label} 평균",
                f"{st_data.get('avg', 0):,.0f}{unit}"
            )

        # 4개 분포 차트
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**CCU (동시접속자) 분포**")
            ccu_vals = [g.get("players") or 0 for g in filtered if (g.get("players") or 0) > 0]
            if ccu_vals:
                import numpy as np
                fig_ccu = go.Figure(go.Histogram(
                    x=[v/1000 for v in ccu_vals], nbinsx=30,
                    marker_color="rgba(79,195,247,0.8)"))
                fig_ccu.update_layout(xaxis_title="CCU (천 명)", yaxis_title="게임 수",
                    height=300, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="white"))
                st.plotly_chart(fig_ccu, use_container_width=True)

            st.markdown("**팔로워 vs 수익 상관관계**")
            rows = [{"name": g.get("name",""), "followers": g.get("followers") or 0,
                     "revenue_m": (g.get("revenue") or 0)/1e6,
                     "score": g.get("reviewScore") or 0}
                    for g in filtered if g.get("followers")]
            if rows:
                df_f = pd.DataFrame(rows)
                fig_fol = px.scatter(df_f, x="followers", y="revenue_m", color="score",
                                     hover_name="name", color_continuous_scale="Blues",
                                     labels={"followers":"팔로워","revenue_m":"수익(백만$)"}, size_max=12)
                fig_fol.update_layout(height=300, plot_bgcolor="#0e1117",
                    paper_bgcolor="#0e1117", font=dict(color="white"))
                st.plotly_chart(fig_fol, use_container_width=True)

        with col2:
            st.markdown("**플레이타임 분포**")
            pt_vals = [g.get("avgPlaytime") or 0 for g in filtered if (g.get("avgPlaytime") or 0) > 0]
            if pt_vals:
                fig_pt = go.Figure(go.Histogram(
                    x=[v for v in pt_vals if v < 200], nbinsx=30,
                    marker_color="rgba(255,183,77,0.8)"))
                fig_pt.update_layout(xaxis_title="평균 플레이타임 (시간)", yaxis_title="게임 수",
                    height=300, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="white"))
                st.plotly_chart(fig_pt, use_container_width=True)

            st.markdown("**리뷰 점수 분포**")
            score_vals = [g.get("reviewScore") or 0 for g in filtered if g.get("reviewScore")]
            if score_vals:
                fig_sc = go.Figure(go.Histogram(
                    x=score_vals, nbinsx=20,
                    marker_color="rgba(165,214,167,0.8)"))
                fig_sc.update_layout(xaxis_title="리뷰 점수", yaxis_title="게임 수",
                    height=300, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="white"))
                st.plotly_chart(fig_sc, use_container_width=True)

        # 플레이타임 구간 분포 (전체 집계)
        st.markdown("**플레이타임 구간별 유저 비율 (전체 평균)**")
        bucket_sums = {}
        cnt = 0
        for g in filtered:
            dist = (_parse_field(g.get("playtimeData"), default={}) or {}).get("distribution") or {}
            if dist:
                for b, pct in dist.items():
                    bucket_sums[b] = bucket_sums.get(b, 0) + pct
                cnt += 1
        if bucket_sums and cnt:
            order = ["0-1h","1-2h","2-5h","5-10h","10-20h","20-50h","50-100h","100-500h","500-1000h"]
            bkts  = [b for b in order if b in bucket_sums]
            avgs  = [round(bucket_sums[b]/cnt, 1) for b in bkts]
            fig_pt_dist = go.Figure(go.Bar(x=bkts, y=avgs, marker_color="rgba(206,147,216,0.85)"))
            fig_pt_dist.update_layout(xaxis_title="플레이타임 구간", yaxis_title="평균 비율 (%)",
                height=280, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="white"))
            st.plotly_chart(fig_pt_dist, use_container_width=True)

        # Top 10 CCU 게임
        st.markdown("**CCU 상위 10개 게임**")
        top_ccu = sorted(filtered, key=lambda x: x.get("players") or 0, reverse=True)[:10]
        ccu_rows = [{"게임명": g.get("name",""), "CCU": f"{(g.get('players') or 0):,}",
                     "리뷰점수": g.get("reviewScore", 0),
                     "플레이타임(h)": round(g.get("avgPlaytime") or 0, 1),
                     "팔로워": f"{(g.get('followers') or 0):,}",
                     "위시리스트": f"{(g.get('wishlists') or 0):,}"}
                    for g in top_ccu]
        st.dataframe(pd.DataFrame(ccu_rows), use_container_width=True, hide_index=True)

# ── 탭: 시계열 히스토리 ───────────────────────────────────
if show_history and "📅 시계열 히스토리" in tab_map:
    with tab_map["📅 시계열 히스토리"]:
        st.subheader("시계열 히스토리 (연도별 집계)")

        hist_freq = st.radio("집계 단위", ["yearly", "monthly"], horizontal=True,
                             format_func=lambda x: "연도별" if x=="yearly" else "월별",
                             key="hist_freq")
        hist_data = get_history_aggregate(filtered, freq=hist_freq,
                                          year_min=year_min, year_max=year_max)

        if not hist_data:
            st.info("히스토리 데이터가 없습니다.")
        else:
            periods = list(hist_data.keys())
            df_h = pd.DataFrame([{"period": p, **v} for p, v in hist_data.items()])

            metric_opt = st.selectbox("차트 지표 선택", [
                "판매 증분 + 수익 증분", "CCU (동시접속자)", "리뷰 점수",
                "평균 플레이타임", "평균 가격", "팔로워"
            ], key="hist_metric")

            if metric_opt == "판매 증분 + 수익 증분":
                fig_h = go.Figure()
                fig_h.add_trace(go.Bar(x=df_h.period, y=df_h.revenue_inc/1e6,
                                       name="수익 증분 (백만$)", marker_color="rgba(79,195,247,0.8)"))
                fig_h.add_trace(go.Scatter(x=df_h.period, y=df_h.sales_inc/1e6,
                                           name="판매 증분 (백만장)",
                                           line=dict(color="#ff7043",width=2), yaxis="y2"))
                fig_h.update_layout(yaxis=dict(title="수익(백만$)"),
                                    yaxis2=dict(title="판매(백만장)",overlaying="y",side="right"),
                                    height=380, plot_bgcolor="#0e1117",
                                    paper_bgcolor="#0e1117", font=dict(color="white"),
                                    legend=dict(orientation="h",y=1.12))

            elif metric_opt == "CCU (동시접속자)":
                fig_h = go.Figure()
                fig_h.add_trace(go.Scatter(x=df_h.period, y=df_h.avg_ccu,
                                           name="평균 CCU", line=dict(color="#4fc3f7",width=2),
                                           mode="lines+markers", fill="tozeroy",
                                           fillcolor="rgba(79,195,247,0.15)"))
                fig_h.add_trace(go.Scatter(x=df_h.period, y=df_h.max_ccu,
                                           name="최대 CCU", line=dict(color="#ff7043",width=1,dash="dot"),
                                           mode="lines"))
                fig_h.update_layout(yaxis_title="CCU", height=380,
                                    plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                    font=dict(color="white"), legend=dict(orientation="h",y=1.12))

            elif metric_opt == "리뷰 점수":
                fig_h = go.Figure(go.Scatter(
                    x=df_h.period, y=df_h.avg_score,
                    line=dict(color="#a5d6a7",width=2), mode="lines+markers",
                    fill="tozeroy", fillcolor="rgba(165,214,167,0.1)"))
                fig_h.update_layout(yaxis_title="평균 리뷰 점수", height=380,
                                    plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="white"))

            elif metric_opt == "평균 플레이타임":
                fig_h = go.Figure(go.Bar(
                    x=df_h.period, y=df_h.avg_playtime,
                    marker_color="rgba(255,183,77,0.85)"))
                fig_h.update_layout(yaxis_title="평균 플레이타임 (시간)", height=380,
                                    plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="white"))

            elif metric_opt == "평균 가격":
                fig_h = go.Figure(go.Scatter(
                    x=df_h.period, y=df_h.avg_price,
                    line=dict(color="#ce93d8",width=2), mode="lines+markers"))
                fig_h.update_layout(yaxis_title="평균 가격 ($)", height=380,
                                    plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="white"))

            else:  # 팔로워
                fig_h = go.Figure(go.Scatter(
                    x=df_h.period, y=df_h.avg_followers,
                    line=dict(color="#80cbc4",width=2), mode="lines+markers",
                    fill="tozeroy", fillcolor="rgba(128,203,196,0.15)"))
                fig_h.update_layout(yaxis_title="평균 팔로워", height=380,
                                    plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="white"))

            st.plotly_chart(fig_h, use_container_width=True)

            # 전체 지표 테이블
            with st.expander("전체 지표 수치 보기"):
                df_show = df_h.copy()
                df_show.columns = ["기간","판매증분","수익증분","평균CCU","최대CCU","총CCU",
                                   "평균점수","평균플레이타임","평균가격","평균팔로워","평균위시리스트","게임수"]
                df_show["수익증분"] = df_show["수익증분"].apply(lambda x: f"${x:,.0f}")
                df_show["판매증분"] = df_show["판매증분"].apply(lambda x: f"{x:,}")
                df_show["평균CCU"] = df_show["평균CCU"].apply(lambda x: f"{x:,.0f}")
                st.dataframe(df_show, use_container_width=True, hide_index=True)

            # 단일 게임 히스토리 (선택)
            st.divider()
            st.subheader("단일 게임 상세 히스토리")
            game_names = [g.get("name","") for g in filtered]
            sel_game_name = st.selectbox("게임 선택", sorted(game_names), key="single_game_hist")
            sel_game = next((g for g in filtered if g.get("name") == sel_game_name), None)
            if sel_game:
                sg_hist = get_history_for_game(sel_game, freq="monthly")
                if sg_hist:
                    df_sg = pd.DataFrame([{"period": p, **v} for p, v in sg_hist.items()])
                    sg_metric = st.selectbox("지표", ["sales_inc","revenue_inc","ccu","score","playtime","followers","wishlists"], key="sg_metric",
                                             format_func=lambda x: {"sales_inc":"판매증분","revenue_inc":"수익증분",
                                                                     "ccu":"CCU","score":"점수","playtime":"플레이타임",
                                                                     "followers":"팔로워","wishlists":"위시리스트"}.get(x,x))
                    fig_sg = go.Figure(go.Scatter(
                        x=df_sg.period, y=df_sg[sg_metric],
                        line=dict(color="#4fc3f7",width=1.5), mode="lines"))
                    fig_sg.update_layout(title=f"{sel_game_name} — {sg_metric}",
                                         height=320, plot_bgcolor="#0e1117",
                                         paper_bgcolor="#0e1117", font=dict(color="white"))
                    st.plotly_chart(fig_sg, use_container_width=True)

# ── 탭: 국가별 분포 ───────────────────────────────────────
if show_country and "🌍 국가별 분포" in tab_map:
    with tab_map["🌍 국가별 분포"]:
        st.subheader("국가별 플레이어 비율")

        weight_opt = st.radio("가중 기준", ["revenue","sales","equal"], horizontal=True,
                              format_func=lambda x: {"revenue":"수익가중","sales":"판매량가중","equal":"동일가중"}.get(x,x),
                              key="country_weight")
        countries = get_country_aggregate(filtered, weight_by=weight_opt)

        if not countries:
            st.info("국가별 데이터가 없습니다.")
        else:
            names = list(countries.keys())[:20]
            pcts  = [countries[n] for n in names]

            col_bar, col_pie = st.columns(2)
            with col_bar:
                fig_c1 = go.Figure(go.Bar(
                    x=pcts[::-1], y=names[::-1], orientation="h",
                    marker_color="rgba(79,195,247,0.8)"))
                fig_c1.update_layout(xaxis_title="비율 (%)", height=500,
                                     plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                     font=dict(color="white"))
                st.plotly_chart(fig_c1, use_container_width=True)

            with col_pie:
                fig_c2 = go.Figure(go.Pie(
                    labels=names[:10], values=pcts[:10],
                    hole=0.35, textinfo="label+percent"))
                fig_c2.update_layout(height=500, paper_bgcolor="#0e1117",
                                     font=dict(color="white"), showlegend=False)
                st.plotly_chart(fig_c2, use_container_width=True)

            # 국가별 데이터를 가진 게임 상세
            with st.expander("국가별 상세 데이터 (상위 20개 게임)"):
                country_rows = []
                for g in sorted(filtered, key=lambda x: x.get("revenue") or 0, reverse=True)[:20]:
                    cd = _parse_field(g.get("countryData"), default={})
                    if not cd: continue
                    row = {"게임명": g.get("name","?")}
                    top5 = sorted(cd.items(), key=lambda x: x[1], reverse=True)[:5]
                    for code, pct in top5:
                        row[code.upper()] = f"{pct}%"
                    country_rows.append(row)
                if country_rows:
                    st.dataframe(pd.DataFrame(country_rows), use_container_width=True, hide_index=True)

# ── 탭: 유저 겹침 분석 ────────────────────────────────────
if show_overlap and "🔗 유저 겹침" in tab_map:
    with tab_map["🔗 유저 겹침"]:
        st.subheader("유저 겹침 분석 (audienceOverlap)")
        st.caption(
            "선택 장르/태그 게임들과 유저를 공유하는 외부 게임. "
            "**추정 공유 유저** = 유저 겹침 지수(Link) × 외부 게임 판매량 — 실제 접근 가능한 유저 규모를 반영합니다."
        )

        ol_sort = st.selectbox(
            "정렬 기준",
            ["reach_score", "avg_link", "copies_sold", "overlap_game_count"],
            format_func=lambda x: {
                "reach_score": "추정 공유 유저 (Link × 판매량)",
                "avg_link": "유저 겹침 지수 (Link)",
                "copies_sold": "외부 게임 판매량",
                "overlap_game_count": "겹친 게임 수 (광범위성)",
            }[x],
            key="ol_sort_1",
        )
        overlaps = get_audience_overlap_top(filtered, top_n=30, sort_by=ol_sort)

        if not overlaps:
            st.info("겹침 데이터가 부족합니다.")
        else:
            # ── 테이블 ──────────────────────────────────────────
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

            st.caption(
                "겹침 광범위성: 필터된 게임 중 해당 외부 게임을 audienceOverlap에 포함하는 비율. "
                "값이 클수록 해당 장르 전반에서 공통으로 경쟁·연관된 게임."
            )

            # ── 버블 차트: X=Link, Y=판매량(로그), 버블=겹침 광범위성 ──
            st.markdown("#### 타겟 유저 맵 — Link × 유저 규모")
            st.caption("오른쪽 위(고Link + 대규모)일수록 핵심 타겟 유저 풀")

            import math
            bubble_data = [o for o in overlaps if o["copies_sold"] > 0]
            if bubble_data:
                max_reach = max(o["reach_score"] for o in bubble_data) or 1
                fig_bubble = go.Figure(go.Scatter(
                    x=[o["avg_link"] for o in bubble_data],
                    y=[o["copies_sold"] / 1_000_000 for o in bubble_data],
                    mode="markers+text",
                    text=[o["name"][:20] for o in bubble_data],
                    textposition="top center",
                    textfont=dict(size=9, color="rgba(255,255,255,0.7)"),
                    marker=dict(
                        size=[max(8, min(50, o["reach_score"] / max_reach * 50)) for o in bubble_data],
                        color=[o["avg_link"] for o in bubble_data],
                        colorscale="YlOrRd",
                        showscale=True,
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
                fig_bubble.update_layout(
                    xaxis_title="유저 겹침 지수 (Link)",
                    yaxis_title="외부 게임 판매량 (백만 장)",
                    yaxis_type="log",
                    height=500,
                    plot_bgcolor="#0e1117",
                    paper_bgcolor="#0e1117",
                    font=dict(color="white"),
                )
                fig_bubble.add_annotation(
                    x=max(o["avg_link"] for o in bubble_data) * 0.85,
                    y=math.log10(max(o["copies_sold"] for o in bubble_data) * 0.8),
                    text="핵심 타겟 영역",
                    showarrow=False,
                    font=dict(color="rgba(255,200,100,0.6)", size=11),
                )
                st.plotly_chart(fig_bubble, use_container_width=True)

            # ── 바 차트: 추정 공유 유저 순 ──────────────────────
            top15 = sorted(overlaps, key=lambda x: x["reach_score"], reverse=True)[:15]
            fig_bar = go.Figure(go.Bar(
                x=[o["reach_score"] / 1_000_000 for o in top15][::-1],
                y=[o["name"][:25] for o in top15][::-1],
                orientation="h",
                marker=dict(
                    color=[o["avg_link"] for o in top15][::-1],
                    colorscale="YlOrRd",
                    showscale=True,
                    colorbar=dict(title="Link"),
                ),
                customdata=[[f"{o['avg_link']:.3f}", f"{o['copies_sold']/1e6:.1f}M"] for o in top15][::-1],
                hovertemplate=(
                    "<b>%{y}</b><br>추정 공유 유저: %{x:.2f}M<br>"
                    "Link: %{customdata[0]}<br>판매량: %{customdata[1]}<extra></extra>"
                ),
            ))
            fig_bar.update_layout(
                xaxis_title="추정 공유 유저 (백만 명)",
                height=440,
                plot_bgcolor="#0e1117",
                paper_bgcolor="#0e1117",
                font=dict(color="white"),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

# ── 탭: 게임 목록 ─────────────────────────────────────────
if show_game_table and "📋 게임 목록" in tab_map:
    with tab_map["📋 게임 목록"]:
        st.subheader(f"전체 게임 목록 ({len(filtered)}개)")

        sort_by = st.selectbox("정렬 기준", ["revenue","copiesSold","reviewScore","players","avgPlaytime","wishlists"],
                               format_func=lambda x: {"revenue":"수익","copiesSold":"판매량",
                                                       "reviewScore":"리뷰점수","players":"CCU",
                                                       "avgPlaytime":"플레이타임","wishlists":"위시리스트"}.get(x,x),
                               key="table_sort")
        sorted_games = sorted(filtered, key=lambda x: x.get(sort_by) or 0, reverse=True)

        rows = []
        for g in sorted_games:
            ts = g.get("releaseDate") or g.get("firstReleaseDate")
            yr = datetime.fromtimestamp(int(ts)/1000).year if ts else "?"
            rows.append({
                "게임명": g.get("name","?"),
                "출시": yr,
                "장르": ", ".join((g.get("genres") or [])[:3]),
                "가격($)": g.get("price") or 0,
                "수익($M)": round((g.get("revenue") or 0)/1e6, 2),
                "판매량(M)": round((g.get("copiesSold") or 0)/1e6, 2),
                "리뷰점수": g.get("reviewScore") or 0,
                "리뷰수": f"{(g.get('reviews') or 0):,}",
                "CCU": f"{(g.get('players') or 0):,}",
                "플레이타임(h)": round(g.get("avgPlaytime") or 0, 1),
                "팔로워": f"{(g.get('followers') or 0):,}",
                "위시리스트": f"{(g.get('wishlists') or 0):,}",
                "Steam 비율": f"{(g.get('steamPercent') or 0):.2f}",
                "태그": ", ".join((g.get("tags") or [])[:5]),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── 탭: AI 분석 ───────────────────────────────────────────
with tab_map["🤖 AI 분석"]:
    st.subheader("Claude AI 심층 분석")
    st.caption(f"선택된 데이터 항목: {', '.join(selected_metrics) if selected_metrics else '기본 (판매·수익)'}")

    ok, msg = check_api_key()
    if not ok:
        st.error(f"Claude API 키 미설정: {msg}")
    else:
        if st.button("🔍 AI 분석 실행", type="primary"):
            yearly = get_yearly_trends(filtered)
            if analysis_type == "태그":
                stats = {k: v for k, v in get_tag_stats(filtered).items() if k in selected}
            else:
                stats = {k: v for k, v in get_genre_stats(filtered).items() if k in selected}

            # 선택된 추가 데이터 포함
            data_summary = summarize_full_for_claude(filtered, selected_metrics, max_games=25)

            prompt = build_genre_trend_prompt(
                selected=selected,
                yearly_data=yearly,
                top_games=get_top_games(filtered, 25, "revenue"),
                genre_stats=stats,
                user_question=user_question,
            )
            # 추가 데이터 요약 삽입
            if selected_metrics:
                prompt = prompt.replace("## 분석 요청", f"## 추가 데이터\n{data_summary}\n\n## 분석 요청")

            placeholder = st.empty()
            full_text = ""
            with st.spinner("Claude AI 분석 중..."):
                for chunk in stream_analysis(prompt, SYSTEM_PROMPT):
                    full_text += chunk
                    placeholder.markdown(full_text)
