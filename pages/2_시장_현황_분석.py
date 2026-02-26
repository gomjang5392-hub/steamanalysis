"""
특정 기간 신규 출시 게임 시장 추세 분석 + 유저 활동 + 시계열 + 국가 데이터
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="시장 현황 분석", page_icon="🏪", layout="wide")

from analysis.data_loader import (
    load_all_games, filter_games, get_genre_stats,
    get_monthly_releases, get_all_genres,
    get_history_aggregate, get_country_aggregate,
    get_activity_summary, get_audience_overlap_top,
    summarize_full_for_claude, _parse_field,
)
from analysis.claude_client import stream_analysis, check_api_key
from analysis.prompts import SYSTEM_PROMPT, build_market_overview_prompt

games      = load_all_games()
all_genres = get_all_genres(games)

# ── 사이드바 ──────────────────────────────────────────────
with st.sidebar:
    st.title("🏪 시장 현황 분석")

    period_option = st.selectbox("분석 기간",
        ["2024년 이후","2023년 이후","2022년 이후","2020년 이후","직접 입력"])

    if period_option == "직접 입력":
        year_min = st.number_input("시작 연도", 2010, 2025, value=2022)
        year_max = st.number_input("종료 연도", 2010, 2025, value=2025)
    else:
        year_min = {"2024년 이후":2024,"2023년 이후":2023,
                    "2022년 이후":2022,"2020년 이후":2020}[period_option]
        year_max = 2025

    genre_filter = st.multiselect("장르 필터 (미선택=전체)", all_genres, default=[])
    sold_min = st.number_input("최소 판매량", 0, value=0, step=100_000)

    st.divider()
    st.markdown("**조회 데이터 항목**")
    show_market   = st.checkbox("시장 출시 추세",   value=True)
    show_activity = st.checkbox("유저 활동 지표",   value=True)
    show_history  = st.checkbox("시계열 히스토리",  value=True)
    show_country  = st.checkbox("국가별 분포",      value=True)
    show_overlap  = st.checkbox("유저 겹침 분석",   value=False)
    show_table    = st.checkbox("전체 게임 테이블", value=True)

    selected_metrics = (
        (["유저 활동 지표"] if show_activity else []) +
        (["시계열 히스토리"] if show_history  else []) +
        (["국가별 데이터"]  if show_country  else []) +
        (["유저 겹침"]      if show_overlap  else [])
    )

    st.divider()
    user_question = st.text_area("AI 추가 질문",
        placeholder="예: 이 기간 가장 급성장한 장르는?", height=90)

    ok, _ = check_api_key()
    if ok:
        st.success("✅ Claude 연결됨")
    else:
        st.warning("⚠️ Claude API 키 미설정")

# ── 메인 ─────────────────────────────────────────────────
st.title("🏪 시장 현황 분석")

filtered = filter_games(games,
    genres=genre_filter if genre_filter else None,
    year_min=year_min, year_max=year_max,
    sold_min=sold_min if sold_min > 0 else None)

period_label = period_option if period_option != "직접 입력" else f"{year_min}~{year_max}년"
genre_label  = f" | 장르: {', '.join(genre_filter)}" if genre_filter else ""
st.caption(f"기간: **{period_label}**{genre_label} | **{len(filtered):,}개** 게임")

if not filtered:
    st.warning("조건에 맞는 게임이 없습니다.")
    st.stop()

# ── KPI 카드 ─────────────────────────────────────────────
revenues  = [g.get("revenue") or 0 for g in filtered]
sales_lst = [g.get("copiesSold") or 0 for g in filtered]
scores    = [g.get("reviewScore") or 0 for g in filtered if g.get("reviewScore")]
hit_cnt   = sum(1 for s in sales_lst if s >= 1_000_000)

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("출시 게임 수",   f"{len(filtered):,}개")
c2.metric("총 수익",        f"${sum(revenues)/1e9:.2f}B")
c3.metric("평균 수익",      f"${sum(revenues)/len(revenues)/1e6:.2f}M")
c4.metric("히트작(100만+)", f"{hit_cnt}개")
c5.metric("평균 리뷰점수",  f"{sum(scores)/len(scores):.1f}" if scores else "-")

st.divider()

# ── 탭 구성 ──────────────────────────────────────────────
tab_labels = (
    (["📅 출시 추세"]       if show_market   else []) +
    (["👥 유저 활동"]       if show_activity else []) +
    (["📈 시계열 히스토리"] if show_history  else []) +
    (["🌍 국가별 분포"]     if show_country  else []) +
    (["🔗 유저 겹침"]       if show_overlap  else []) +
    (["📋 게임 목록"]       if show_table    else []) +
    ["🤖 AI 분석"]
)
tabs    = st.tabs(tab_labels)
tab_map = {l: t for l, t in zip(tab_labels, tabs)}

# ── 출시 추세 ─────────────────────────────────────────────
if show_market and "📅 출시 추세" in tab_map:
    with tab_map["📅 출시 추세"]:
        st.subheader("월별 신규 출시 게임 수")
        monthly = get_monthly_releases(filtered)
        df_m = pd.DataFrame(monthly)
        if not df_m.empty:
            df_m = df_m[df_m.month.str[:4].astype(int).between(year_min, year_max)]
        fig1 = go.Figure(go.Bar(x=df_m.month, y=df_m["count"],
                                marker_color="rgba(79,195,247,0.8)"))
        fig1.update_layout(xaxis_title="출시 월", yaxis_title="게임 수",
                           height=300, plot_bgcolor="#0e1117",
                           paper_bgcolor="#0e1117", font=dict(color="white"))
        st.plotly_chart(fig1, use_container_width=True)

        col1, col2 = st.columns(2)
        genre_stats = get_genre_stats(filtered)

        with col1:
            st.subheader("장르별 수익 비중")
            top_g = list(genre_stats.items())[:8]
            fig2 = go.Figure(go.Pie(
                labels=[n for n,_ in top_g],
                values=[s["total_revenue"] for _,s in top_g],
                hole=0.4, textinfo="label+percent"))
            fig2.update_layout(height=340, paper_bgcolor="#0e1117",
                               font=dict(color="white"), showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        with col2:
            st.subheader("판매량 분포 (로그 스케일)")
            log_sales = [np.log10(s) for s in sales_lst if s > 0]
            fig3 = go.Figure(go.Histogram(x=log_sales, nbinsx=30,
                                          marker_color="rgba(255,183,77,0.8)"))
            fig3.update_layout(
                xaxis=dict(title="판매량 (log10)",
                           tickvals=[6,6.5,7,7.5,8],
                           ticktext=["100만","300만","1천만","3천만","1억"]),
                yaxis_title="게임 수", height=340,
                plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="white"))
            st.plotly_chart(fig3, use_container_width=True)

        st.subheader("리뷰 점수 vs 수익")
        rows = [{"name":g.get("name",""),"score":g.get("reviewScore") or 0,
                 "rev_m":(g.get("revenue") or 0)/1e6,
                 "sal_m":(g.get("copiesSold") or 0)/1e6}
                for g in filtered if g.get("reviewScore")]
        if rows:
            df_sc = pd.DataFrame(rows)
            fig4 = px.scatter(df_sc, x="score", y="rev_m", size="sal_m",
                              hover_name="name", color="score",
                              color_continuous_scale="Blues", size_max=40,
                              labels={"score":"리뷰점수","rev_m":"수익(백만$)"})
            fig4.update_layout(height=380, plot_bgcolor="#0e1117",
                               paper_bgcolor="#0e1117", font=dict(color="white"))
            st.plotly_chart(fig4, use_container_width=True)

# ── 유저 활동 ─────────────────────────────────────────────
if show_activity and "👥 유저 활동" in tab_map:
    with tab_map["👥 유저 활동"]:
        st.subheader("유저 활동 지표")
        activity = get_activity_summary(filtered)

        kpi_cols = st.columns(4)
        kpi_data = [
            ("평균 리뷰점수",  activity.get("review_score",{}).get("avg",0), ""),
            ("평균 플레이타임",activity.get("avg_playtime",{}).get("avg",0), "h"),
            ("평균 팔로워",    activity.get("followers",{}).get("avg",0), ""),
            ("평균 위시리스트",activity.get("wishlists",{}).get("avg",0), ""),
        ]
        for i,(label,val,unit) in enumerate(kpi_data):
            kpi_cols[i].metric(label, f"{val:,.0f}{unit}")

        col1, col2 = st.columns(2)
        with col1:
            pt_vals = [g.get("avgPlaytime") or 0 for g in filtered if (g.get("avgPlaytime") or 0) > 0]
            if pt_vals:
                fig_pt = go.Figure(go.Histogram(
                    x=[v for v in pt_vals if v < 200], nbinsx=25,
                    marker_color="rgba(255,183,77,0.8)"))
                fig_pt.update_layout(xaxis_title="평균 플레이타임 (h)", yaxis_title="게임 수",
                    height=300, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="white"),
                    title="플레이타임 분포")
                st.plotly_chart(fig_pt, use_container_width=True)

        with col2:
            # 팔로워 상위 10
            top10_fol = sorted(filtered, key=lambda x: x.get("followers") or 0, reverse=True)[:10]
            fig_fol2 = go.Figure(go.Bar(
                x=[(g.get("followers") or 0)/1000 for g in top10_fol][::-1],
                y=[g.get("name","")[:25] for g in top10_fol][::-1],
                orientation="h", marker_color="rgba(79,195,247,0.8)"))
            fig_fol2.update_layout(xaxis_title="팔로워 (천)", height=300,
                plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="white"),
                title="팔로워 상위 10개 게임")
            st.plotly_chart(fig_fol2, use_container_width=True)

        # 플레이타임 구간
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
            bkts = [b for b in order if b in bucket_sums]
            avgs = [round(bucket_sums[b]/cnt,1) for b in bkts]
            fig_bd = go.Figure(go.Bar(x=bkts, y=avgs, marker_color="rgba(206,147,216,0.85)"))
            fig_bd.update_layout(xaxis_title="플레이타임 구간", yaxis_title="평균 비율 (%)",
                height=260, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                font=dict(color="white"), title="플레이타임 구간별 유저 비율")
            st.plotly_chart(fig_bd, use_container_width=True)

# ── 시계열 히스토리 ───────────────────────────────────────
if show_history and "📈 시계열 히스토리" in tab_map:
    with tab_map["📈 시계열 히스토리"]:
        st.subheader("기간 내 게임들의 시계열 집계 트렌드")

        hist_data = get_history_aggregate(filtered, freq="yearly",
                                          year_min=year_min, year_max=year_max)
        if not hist_data:
            st.info("히스토리 데이터가 없습니다.")
        else:
            df_h = pd.DataFrame([{"period": p, **v} for p, v in hist_data.items()])

            metric_tabs = st.tabs(["수익·판매", "동시접속(히스토리)", "점수·플레이타임", "가격·팔로워"])

            with metric_tabs[0]:
                fig = go.Figure()
                fig.add_trace(go.Bar(x=df_h.period, y=df_h.revenue_inc/1e6,
                                     name="수익증분(백만$)", marker_color="rgba(79,195,247,0.8)"))
                fig.add_trace(go.Scatter(x=df_h.period, y=df_h.sales_inc/1e6,
                                         name="판매증분(백만장)", yaxis="y2",
                                         line=dict(color="#ff7043",width=2)))
                fig.update_layout(yaxis=dict(title="수익(백만$)"),
                                  yaxis2=dict(title="판매(백만장)",overlaying="y",side="right"),
                                  height=360, plot_bgcolor="#0e1117",
                                  paper_bgcolor="#0e1117", font=dict(color="white"))
                st.plotly_chart(fig, use_container_width=True)

            with metric_tabs[1]:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df_h.period, y=df_h.avg_ccu,
                                         name="평균 CCU", fill="tozeroy",
                                         fillcolor="rgba(79,195,247,0.15)",
                                         line=dict(color="#4fc3f7",width=2)))
                fig.add_trace(go.Scatter(x=df_h.period, y=df_h.max_ccu,
                                         name="최대 CCU (최상위 게임)", line=dict(color="#ff7043",width=1,dash="dot")))
                fig.update_layout(yaxis_title="CCU", height=360,
                                  plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                  font=dict(color="white"))
                st.plotly_chart(fig, use_container_width=True)

            with metric_tabs[2]:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df_h.period, y=df_h.avg_score,
                                         name="평균 리뷰점수", line=dict(color="#a5d6a7",width=2),
                                         mode="lines+markers"))
                fig.add_trace(go.Bar(x=df_h.period, y=df_h.avg_playtime,
                                     name="평균 플레이타임(h)", yaxis="y2",
                                     marker_color="rgba(255,183,77,0.6)"))
                fig.update_layout(yaxis=dict(title="리뷰 점수"),
                                  yaxis2=dict(title="플레이타임(h)",overlaying="y",side="right"),
                                  height=360, plot_bgcolor="#0e1117",
                                  paper_bgcolor="#0e1117", font=dict(color="white"))
                st.plotly_chart(fig, use_container_width=True)

            with metric_tabs[3]:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df_h.period, y=df_h.avg_price,
                                         name="평균 가격($)", line=dict(color="#ce93d8",width=2)))
                fig.add_trace(go.Scatter(x=df_h.period, y=df_h.avg_followers,
                                         name="평균 팔로워", yaxis="y2",
                                         line=dict(color="#80cbc4",width=2)))
                fig.update_layout(yaxis=dict(title="평균 가격($)"),
                                  yaxis2=dict(title="팔로워",overlaying="y",side="right"),
                                  height=360, plot_bgcolor="#0e1117",
                                  paper_bgcolor="#0e1117", font=dict(color="white"))
                st.plotly_chart(fig, use_container_width=True)

# ── 국가별 분포 ───────────────────────────────────────────
if show_country and "🌍 국가별 분포" in tab_map:
    with tab_map["🌍 국가별 분포"]:
        st.subheader("국가별 플레이어 비율")
        weight_opt = st.radio("가중 기준", ["revenue","sales","equal"], horizontal=True,
                              format_func=lambda x: {"revenue":"수익가중","sales":"판매가중","equal":"동일가중"}.get(x,x))
        countries = get_country_aggregate(filtered, weight_by=weight_opt)
        if countries:
            names = list(countries.keys())[:20]
            pcts  = [countries[n] for n in names]
            col1, col2 = st.columns(2)
            with col1:
                fig_c = go.Figure(go.Bar(x=pcts[::-1], y=names[::-1],
                                         orientation="h", marker_color="rgba(79,195,247,0.8)"))
                fig_c.update_layout(xaxis_title="비율 (%)", height=500,
                                    plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                    font=dict(color="white"))
                st.plotly_chart(fig_c, use_container_width=True)
            with col2:
                fig_p = go.Figure(go.Pie(labels=names[:10], values=pcts[:10],
                                         hole=0.35, textinfo="label+percent"))
                fig_p.update_layout(height=500, paper_bgcolor="#0e1117",
                                    font=dict(color="white"), showlegend=False)
                st.plotly_chart(fig_p, use_container_width=True)

# ── 유저 겹침 ─────────────────────────────────────────────
if show_overlap and "🔗 유저 겹침" in tab_map:
    with tab_map["🔗 유저 겹침"]:
        st.subheader("유저 겹침 분석 (audienceOverlap)")
        st.caption(
            "해당 기간 출시 게임들과 유저를 공유하는 외부 게임. "
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
            key="ol_sort_2",
        )
        overlaps = get_audience_overlap_top(filtered, top_n=30, sort_by=ol_sort)

        if not overlaps:
            st.info("겹침 데이터가 부족합니다.")
        else:
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

            # ── 버블 차트 ──────────────────────────────────────
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

# ── 게임 목록 ─────────────────────────────────────────────
if show_table and "📋 게임 목록" in tab_map:
    with tab_map["📋 게임 목록"]:
        st.subheader(f"전체 게임 목록 ({len(filtered)}개)")
        sort_by = st.selectbox("정렬 기준",
            ["revenue","copiesSold","reviewScore","avgPlaytime","wishlists"],
            format_func=lambda x: {"revenue":"수익","copiesSold":"판매량","reviewScore":"리뷰점수",
                                   "avgPlaytime":"플레이타임","wishlists":"위시리스트"}.get(x,x))
        rows = []
        for g in sorted(filtered, key=lambda x: x.get(sort_by) or 0, reverse=True):
            ts = g.get("releaseDate") or g.get("firstReleaseDate")
            yr = datetime.fromtimestamp(int(ts)/1000).strftime("%Y-%m") if ts else "?"
            rows.append({"게임명":g.get("name",""),"출시":yr,
                         "장르":", ".join((g.get("genres") or [])[:3]),
                         "가격($)":f"${g.get('price') or 0:.2f}",
                         "수익($M)":f"{(g.get('revenue') or 0)/1e6:.2f}",
                         "판매량(M)":f"{(g.get('copiesSold') or 0)/1e6:.2f}",
                         "리뷰점수":g.get("reviewScore") or 0,
                         "플레이타임(h)":f"{(g.get('avgPlaytime') or 0):.1f}".rstrip('0').rstrip('.'),
                         "팔로워":f"{(g.get('followers') or 0):,}",
                         "위시리스트":f"{(g.get('wishlists') or 0):,}",
                         "국가Top1": sorted((_parse_field(g.get("countryData"), default={}) or {}).items(),
                                           key=lambda x:x[1],reverse=True)[0][0].upper()
                                     if _parse_field(g.get("countryData"), default={}) else "-"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── AI 분석 ───────────────────────────────────────────────
with tab_map["🤖 AI 분석"]:
    st.subheader("Claude AI 시장 분석")
    ok, msg = check_api_key()
    if not ok:
        st.error(f"Claude API 키 미설정: {msg}")
    else:
        if st.button("🔍 AI 시장 분석 실행", type="primary"):
            data_summary = summarize_full_for_claude(filtered, selected_metrics, max_games=25)
            prompt = build_market_overview_prompt(
                period_label=period_label,
                games=filtered,
                monthly_data=get_monthly_releases(filtered),
                genre_dist=get_genre_stats(filtered),
                user_question=user_question,
            )
            if selected_metrics:
                prompt = prompt.replace("## 분석 요청", f"## 추가 데이터\n{data_summary}\n\n## 분석 요청")

            placeholder = st.empty()
            full_text = ""
            with st.spinner("Claude AI 분석 중..."):
                for chunk in stream_analysis(prompt, SYSTEM_PROMPT):
                    full_text += chunk
                    placeholder.markdown(full_text)
