"""
신규 게임 개발 전략 가이드 + 유저 활동 + 시계열 + 국가 데이터
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

st.set_page_config(page_title="개발 전략 가이드", page_icon="🛠", layout="wide")

from analysis.data_loader import (
    load_all_games, filter_games, get_top_games,
    get_common_tags, get_price_buckets,
    get_all_tags, get_all_genres,
    get_history_aggregate, get_country_aggregate,
    get_activity_summary, get_audience_overlap_top,
    summarize_full_for_claude,
)
from analysis.claude_client import stream_analysis, check_api_key
from analysis.prompts import SYSTEM_PROMPT, build_dev_guide_prompt

games      = load_all_games()
all_tags   = get_all_tags(games, min_count=5)
all_genres = get_all_genres(games)

# ── 사이드바 ──────────────────────────────────────────────
with st.sidebar:
    st.title("🛠 개발 전략 가이드")

    analysis_type = st.radio("기준 선택", ["태그", "장르"], horizontal=True)
    if analysis_type == "태그":
        popular = ["FPS","RPG","Survival","Open World","Battle Royale","Horror",
                   "Puzzle","Platformer","Simulation","Racing","Strategy","Roguelike"]
        defaults = [t for t in popular if t in all_tags][:2]
        selected = st.multiselect("목표 태그", all_tags, default=defaults, max_selections=5)
    else:
        selected = st.multiselect("목표 장르", all_genres,
                                  default=all_genres[:2] if all_genres else [], max_selections=5)

    st.divider()
    scale = st.selectbox("개발 규모", ["인디","AA","AAA"])
    scale_sold_map = {"인디": 0, "AA": 500_000, "AAA": 2_000_000}
    extra = st.text_area("추가 조건", placeholder="예: 1인 개발, 예산 $50만", height=70)
    top_n = st.slider("벤치마크 게임 수", 10, 50, 20)
    year_min, year_max = st.slider("출시 연도 범위", 2010, 2025, (2010, 2025), key="year_range_3")

    st.divider()
    st.markdown("**조회 데이터 항목**")
    show_activity = st.checkbox("유저 활동 지표",   value=True)
    show_history  = st.checkbox("시계열 히스토리",  value=True)
    show_country  = st.checkbox("국가별 분포",      value=True)
    show_overlap  = st.checkbox("유저 겹침 분석",   value=False)

    selected_metrics = (
        (["유저 활동 지표"] if show_activity else []) +
        (["시계열 히스토리"] if show_history  else []) +
        (["국가별 데이터"]  if show_country  else []) +
        (["유저 겹침"]      if show_overlap  else [])
    )

    st.divider()
    user_question = st.text_area("AI 추가 질문",
        placeholder="예: 현재 시장에서 부족한 서브장르는?", height=70)

    ok, _ = check_api_key()
    if ok:
        st.success("✅ Claude 연결됨")
    else:
        st.warning("⚠️ Claude API 키 미설정")

# ── 메인 ─────────────────────────────────────────────────
st.title("🛠 게임 개발 전략 가이드")

if not selected:
    st.info("사이드바에서 태그 또는 장르를 선택하세요.")
    st.stop()

sold_min = scale_sold_map[scale]
kw = dict(tags=selected) if analysis_type == "태그" else dict(genres=selected)
filtered = filter_games(games, **kw,
                        sold_min=sold_min if sold_min > 0 else None,
                        year_min=year_min, year_max=year_max)

selected_label = ", ".join(selected)
st.caption(f"분석: **{selected_label}** | 규모: **{scale}** | 출시: {year_min}~{year_max}년 | 기준 판매량: {sold_min:,}장+ | **{len(filtered):,}개** 게임")

if not filtered:
    st.warning("조건에 맞는 게임이 없습니다.")
    st.stop()

# ── KPI 카드 ─────────────────────────────────────────────
revenues  = [g.get("revenue") or 0 for g in filtered]
sales_lst = [g.get("copiesSold") or 0 for g in filtered]
scores    = [g.get("reviewScore") or 0 for g in filtered if g.get("reviewScore")]
playtimes = [g.get("avgPlaytime") or 0 for g in filtered if g.get("avgPlaytime")]
ccus      = [g.get("players") or 0 for g in filtered if g.get("players")]

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("분석 게임 수",   f"{len(filtered):,}개")
c2.metric("평균 수익",      f"${sum(revenues)/len(revenues)/1e6:.2f}M")
c3.metric("평균 판매량",    f"{sum(sales_lst)/len(sales_lst)/1e6:.2f}M장")
c4.metric("평균 리뷰 점수", f"{sum(scores)/len(scores):.1f}" if scores else "-")
c5.metric("평균 CCU",       f"{sum(ccus)/len(ccus):,.0f}" if ccus else "-")

st.divider()

# ── 탭 ───────────────────────────────────────────────────
tab_labels = (
    ["🏆 벤치마크"] +
    (["👥 유저 활동"]       if show_activity else []) +
    (["📈 시계열 히스토리"] if show_history  else []) +
    (["🌍 국가별 분포"]     if show_country  else []) +
    (["🔗 유저 겹침"]       if show_overlap  else []) +
    ["🤖 AI 전략 가이드"]
)
tabs    = st.tabs(tab_labels)
tab_map = {l: t for l, t in zip(tab_labels, tabs)}

# ── 벤치마크 ─────────────────────────────────────────────
with tab_map["🏆 벤치마크"]:
    st.subheader(f"벤치마크 성공작 Top {top_n}")
    top_games = get_top_games(filtered, top_n, "revenue")

    rows = []
    for i, g in enumerate(top_games, 1):
        ts = g.get("releaseDate") or g.get("firstReleaseDate")
        yr = datetime.fromtimestamp(int(ts)/1000).year if ts else "?"
        rows.append({"#":i,"게임명":g.get("name",""),"출시":yr,
                     "가격($)":g.get("price") or 0,
                     "수익($M)":round((g.get("revenue") or 0)/1e6,2),
                     "판매량(M)":round((g.get("copiesSold") or 0)/1e6,2),
                     "리뷰점수":g.get("reviewScore") or 0,
                     "CCU":f"{(g.get('players') or 0):,}",
                     "플레이타임(h)":round(g.get("avgPlaytime") or 0,1),
                     "팔로워":f"{(g.get('followers') or 0):,}",
                     "위시리스트":f"{(g.get('wishlists') or 0):,}",
                     "태그":", ".join((g.get("tags") or [])[:4])})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("💰 가격대별 수익 분포")
        price_data = get_price_buckets(filtered)
        df_p = pd.DataFrame(price_data)
        order = ["무료","$0~5","$5~10","$10~20","$20~30","$30~60","$60+"]
        df_p["price_bucket"] = pd.Categorical(df_p["price_bucket"], categories=order, ordered=True)
        df_p = df_p.sort_values("price_bucket")
        fig_box = px.box(df_p, x="price_bucket", y="revenue", color="price_bucket",
                         log_y=True, labels={"price_bucket":"가격대","revenue":"수익($)"})
        fig_box.update_layout(showlegend=False, height=380,
                              plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                              font=dict(color="white"))
        st.plotly_chart(fig_box, use_container_width=True)

    with col2:
        st.subheader("🏷 성공작 공통 태그 Top 15")
        common_tags = get_common_tags(filtered, 15)
        if common_tags:
            tag_names = [t for t,_ in common_tags]
            tag_cnts  = [c for _,c in common_tags]
            fig_tags = go.Figure(go.Bar(
                x=tag_cnts[::-1], y=tag_names[::-1],
                orientation="h", marker_color="rgba(129,199,132,0.85)"))
            fig_tags.update_layout(xaxis_title="게임 수", height=380,
                                   plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                   font=dict(color="white"))
            st.plotly_chart(fig_tags, use_container_width=True)

    st.subheader("⏱ 평균 플레이타임 분포")
    pt_vals = [g.get("avgPlaytime") or 0 for g in filtered if (g.get("avgPlaytime") or 0) > 0]
    if pt_vals:
        fig_pt = go.Figure(go.Histogram(
            x=[v for v in pt_vals if v < 200], nbinsx=25,
            marker_color="rgba(255,138,101,0.8)"))
        fig_pt.update_layout(xaxis_title="평균 플레이타임 (h)", yaxis_title="게임 수",
                             height=280, plot_bgcolor="#0e1117",
                             paper_bgcolor="#0e1117", font=dict(color="white"))
        st.plotly_chart(fig_pt, use_container_width=True)

# ── 유저 활동 ─────────────────────────────────────────────
if show_activity and "👥 유저 활동" in tab_map:
    with tab_map["👥 유저 활동"]:
        st.subheader("유저 활동 지표 분석")
        activity = get_activity_summary(filtered)

        kpi_cols = st.columns(5)
        for i, (key, label, unit) in enumerate([
            ("players_ccu","평균 CCU",""),
            ("avg_playtime","평균 플레이타임","h"),
            ("followers","평균 팔로워",""),
            ("wishlists","평균 위시리스트",""),
            ("review_score","평균 리뷰점수",""),
        ]):
            kpi_cols[i].metric(label, f"{activity.get(key,{}).get('avg',0):,.0f}{unit}")

        col1, col2 = st.columns(2)

        with col1:
            # CCU vs 판매량
            rows = [{"name":g.get("name",""),
                     "ccu_k":(g.get("players") or 0)/1000,
                     "sales_m":(g.get("copiesSold") or 0)/1e6,
                     "score":g.get("reviewScore") or 0}
                    for g in filtered if g.get("players")]
            if rows:
                df_cs = pd.DataFrame(rows)
                fig_cs = px.scatter(df_cs, x="ccu_k", y="sales_m", color="score",
                                    hover_name="name", color_continuous_scale="Viridis",
                                    labels={"ccu_k":"CCU(천)","sales_m":"판매량(백만장)","score":"점수"},
                                    size_max=12)
                fig_cs.update_layout(title="CCU vs 판매량", height=320,
                                     plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                     font=dict(color="white"))
                st.plotly_chart(fig_cs, use_container_width=True)

        with col2:
            # 플레이타임 vs 리뷰점수
            rows2 = [{"name":g.get("name",""),
                      "pt":g.get("avgPlaytime") or 0,
                      "score":g.get("reviewScore") or 0,
                      "rev_m":(g.get("revenue") or 0)/1e6}
                     for g in filtered if g.get("reviewScore") and (g.get("avgPlaytime") or 0) < 200]
            if rows2:
                df_ps = pd.DataFrame(rows2)
                fig_ps = px.scatter(df_ps, x="pt", y="score", color="rev_m",
                                    hover_name="name", color_continuous_scale="Blues",
                                    labels={"pt":"플레이타임(h)","score":"리뷰점수","rev_m":"수익(백만$)"},
                                    size_max=12)
                fig_ps.update_layout(title="플레이타임 vs 리뷰점수", height=320,
                                     plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                     font=dict(color="white"))
                st.plotly_chart(fig_ps, use_container_width=True)

        # 플레이타임 구간 분포
        bucket_sums = {}
        cnt = 0
        for g in filtered:
            dist = (g.get("playtimeData") or {}).get("distribution") or {}
            if dist:
                for b, pct in dist.items():
                    bucket_sums[b] = bucket_sums.get(b, 0) + pct
                cnt += 1
        if bucket_sums and cnt:
            order = ["0-1h","1-2h","2-5h","5-10h","10-20h","20-50h","50-100h","100-500h","500-1000h"]
            bkts = [b for b in order if b in bucket_sums]
            avgs = [round(bucket_sums[b]/cnt,1) for b in bkts]
            fig_bd = go.Figure(go.Bar(x=bkts, y=avgs, marker_color="rgba(206,147,216,0.85)"))
            fig_bd.update_layout(xaxis_title="플레이타임 구간", yaxis_title="평균 비율(%)",
                height=260, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                font=dict(color="white"), title="성공작의 플레이타임 구간별 유저 비율")
            st.plotly_chart(fig_bd, use_container_width=True)

# ── 시계열 히스토리 ───────────────────────────────────────
if show_history and "📈 시계열 히스토리" in tab_map:
    with tab_map["📈 시계열 히스토리"]:
        st.subheader("장르·태그 시계열 성장 추이")
        hist_data = get_history_aggregate(filtered, freq="yearly")
        if not hist_data:
            st.info("히스토리 데이터가 없습니다.")
        else:
            df_h = pd.DataFrame([{"period":p,**v} for p,v in hist_data.items()])
            col1, col2 = st.columns(2)
            with col1:
                fig_rev = go.Figure()
                fig_rev.add_trace(go.Bar(x=df_h.period, y=df_h.revenue_inc/1e6,
                                         name="수익증분(백만$)", marker_color="rgba(79,195,247,0.8)"))
                fig_rev.add_trace(go.Scatter(x=df_h.period, y=df_h.sales_inc/1e6,
                                             name="판매증분(백만장)", yaxis="y2",
                                             line=dict(color="#ff7043",width=2)))
                fig_rev.update_layout(yaxis=dict(title="수익(백만$)"),
                                      yaxis2=dict(title="판매(백만장)",overlaying="y",side="right"),
                                      height=340, plot_bgcolor="#0e1117",
                                      paper_bgcolor="#0e1117", font=dict(color="white"),
                                      title="연도별 수익·판매 증분")
                st.plotly_chart(fig_rev, use_container_width=True)

            with col2:
                fig_ccu = go.Figure()
                fig_ccu.add_trace(go.Scatter(x=df_h.period, y=df_h.avg_ccu,
                                              name="평균CCU", fill="tozeroy",
                                              fillcolor="rgba(79,195,247,0.15)",
                                              line=dict(color="#4fc3f7",width=2)))
                fig_ccu.update_layout(yaxis_title="평균 CCU", height=340,
                                      plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                      font=dict(color="white"), title="연도별 평균 CCU")
                st.plotly_chart(fig_ccu, use_container_width=True)

            col3, col4 = st.columns(2)
            with col3:
                fig_sc = go.Figure(go.Scatter(x=df_h.period, y=df_h.avg_score,
                                              line=dict(color="#a5d6a7",width=2),
                                              mode="lines+markers", fill="tozeroy",
                                              fillcolor="rgba(165,214,167,0.1)"))
                fig_sc.update_layout(yaxis_title="평균 리뷰 점수", height=300,
                                     plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                     font=dict(color="white"), title="연도별 평균 리뷰 점수")
                st.plotly_chart(fig_sc, use_container_width=True)

            with col4:
                fig_pr = go.Figure(go.Scatter(x=df_h.period, y=df_h.avg_price,
                                              line=dict(color="#ce93d8",width=2),
                                              mode="lines+markers"))
                fig_pr.update_layout(yaxis_title="평균 가격 ($)", height=300,
                                     plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                     font=dict(color="white"), title="연도별 평균 가격")
                st.plotly_chart(fig_pr, use_container_width=True)

# ── 국가별 분포 ───────────────────────────────────────────
if show_country and "🌍 국가별 분포" in tab_map:
    with tab_map["🌍 국가별 분포"]:
        st.subheader("타겟 시장 국가별 분포")
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
                fig_p = go.Figure(go.Pie(labels=names[:12], values=pcts[:12],
                                         hole=0.35, textinfo="label+percent"))
                fig_p.update_layout(height=500, paper_bgcolor="#0e1117",
                                    font=dict(color="white"), showlegend=False)
                st.plotly_chart(fig_p, use_container_width=True)
            st.info(f"💡 **주요 시장**: {', '.join(names[:5])} — 이 장르 성공작 유저의 주요 국가입니다.")

# ── 유저 겹침 ─────────────────────────────────────────────
if show_overlap and "🔗 유저 겹침" in tab_map:
    with tab_map["🔗 유저 겹침"]:
        st.subheader("경쟁·연관 게임 유저 겹침 분석")
        st.caption(
            "성공 벤치마크 게임들과 유저를 공유하는 외부 게임. "
            "**추정 공유 유저** = 유저 겹침 지수(Link) × 외부 게임 판매량 — "
            "마케팅 시 실제 도달 가능한 유저 규모를 반영합니다."
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
            key="ol_sort_3",
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
            st.caption("겹침 광범위성: 벤치마크 게임 중 해당 외부 게임을 audienceOverlap에 포함하는 비율.")

            # ── 버블 차트 ──────────────────────────────────────
            st.markdown("#### 타겟 유저 맵 — Link × 유저 규모")
            st.caption("오른쪽 위(고Link + 대규모)일수록 진입 시 공략해야 할 핵심 타겟 플레이어 풀")

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

# ── AI 전략 가이드 ────────────────────────────────────────
with tab_map["🤖 AI 전략 가이드"]:
    st.subheader("Claude AI 개발 전략 가이드")
    st.caption(f"포함 데이터: {', '.join(selected_metrics) if selected_metrics else '기본 통계'}")

    ok, msg = check_api_key()
    if not ok:
        st.error(f"Claude API 키 미설정: {msg}")
    else:
        if st.button("🔍 AI 전략 가이드 생성", type="primary"):
            data_summary = summarize_full_for_claude(filtered, selected_metrics, max_games=25)
            prompt = build_dev_guide_prompt(
                target=selected, scale=scale, extra_conditions=extra,
                games=filtered, price_data=get_price_buckets(filtered),
                common_tags=get_common_tags(filtered, 15), user_question=user_question,
            )
            if selected_metrics:
                prompt = prompt.replace("## 분석 요청", f"## 추가 데이터\n{data_summary}\n\n## 분석 요청")

            placeholder = st.empty()
            full_text = ""
            with st.spinner("Claude AI 전략 가이드 생성 중..."):
                for chunk in stream_analysis(prompt, SYSTEM_PROMPT):
                    full_text += chunk
                    placeholder.markdown(full_text)
