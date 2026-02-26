"""
Gamalytic Game Data Collector - Streamlit 웹 애플리케이션
Steam ID를 입력하면 Gamalytic API에서 게임 상세 데이터를 가져와 CSV로 저장합니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
from scripts.game_collector import (
    fetch_game,
    save_all_csvs,
    get_collected_games,
    load_api_key,
    sanitize_name,
    GAME_DATA_DIR,
)

# ─── 페이지 설정 ──────────────────────────────────────────

st.set_page_config(
    page_title="Gamalytic Game Data Collector",
    page_icon="🎮",
    layout="wide",
)

st.title("Gamalytic Game Data Collector")
st.caption("Steam ID를 입력하여 게임 데이터를 수집하고 CSV로 저장합니다.")

# API 키 상태 확인
api_key = load_api_key()
if not api_key:
    st.error("API 키가 설정되지 않았습니다. .env 파일에 GAMALYTIC_API_KEY를 설정하세요.")
    st.stop()

st.sidebar.success(f"API Key: ****{api_key[-4:]}")
st.sidebar.info(f"저장 경로: {GAME_DATA_DIR}")

# ─── 탭 구성 ──────────────────────────────────────────────

tab1, tab2 = st.tabs(["게임 데이터 수집", "수집 이력"])

# ─── 탭 1: 게임 데이터 수집 ──────────────────────────────

with tab1:
    col_input, col_examples = st.columns([3, 2])

    with col_input:
        steam_id = st.text_input(
            "Steam ID 입력",
            placeholder="예: 730",
            help="Steam 스토어 URL에서 확인 가능합니다. (store.steampowered.com/app/[Steam ID]/...)",
        )

    with col_examples:
        st.markdown("**예시 Steam ID**")
        st.markdown(
            "`730` CS2 · `1086940` BG3 · `1245620` Elden Ring · "
            "`2358720` Black Myth · `578080` PUBG"
        )

    if st.button("데이터 수집 및 저장", type="primary", disabled=not steam_id):
        # 입력 검증
        clean_id = steam_id.strip()
        if not clean_id.isdigit():
            st.error("Steam ID는 숫자만 입력할 수 있습니다.")
        else:
            # API 호출
            with st.spinner(f"Steam ID {clean_id} 데이터를 가져오는 중..."):
                game_data, error = fetch_game(clean_id, api_key)

            if error:
                st.error(error)
            else:
                # 게임 미리보기
                st.divider()
                st.subheader(game_data.get("name", "Unknown"))

                col_img, col_info = st.columns([1, 2])
                with col_img:
                    header_url = game_data.get("headerImageUrl", "")
                    if header_url:
                        st.image(header_url, use_container_width=True)

                with col_info:
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("가격", f"${game_data.get('price', 0):.2f}")
                    m2.metric("리뷰 점수", f"{game_data.get('reviewScore', 0)}%")
                    m3.metric("판매량", f"{game_data.get('copiesSold', 0):,}")
                    m4.metric("매출", f"${game_data.get('revenue', 0):,.0f}")

                    m5, m6, m7, m8 = st.columns(4)
                    m5.metric("소유자", f"{game_data.get('owners', 0):,}")
                    m6.metric("팔로워", f"{game_data.get('followers', 0):,}")
                    m7.metric("위시리스트", f"{game_data.get('wishlists', 0):,}")
                    m8.metric("평균 플레이타임", f"{game_data.get('avgPlaytime', 0):.1f}h")

                    genres = game_data.get("genres", [])
                    if genres:
                        st.markdown("**장르:** " + " · ".join(genres))

                # CSV 저장
                st.divider()
                with st.spinner("CSV 파일 저장 중..."):
                    results, output_path = save_all_csvs(game_data)

                st.success(f"저장 완료: `{output_path}`")

                # 저장 결과 테이블
                st.markdown("**생성된 CSV 파일:**")
                for r in results:
                    st.markdown(f"- `{r['name']}` — {r['description']} ({r['rows']}행)")

# ─── 탭 2: 수집 이력 ─────────────────────────────────────

with tab2:
    games = get_collected_games()

    if not games:
        st.info("아직 수집된 게임이 없습니다. '게임 데이터 수집' 탭에서 시작하세요.")
    else:
        st.subheader(f"수집된 게임 ({len(games)}개)")
        st.dataframe(
            games,
            column_config={
                "steam_id": st.column_config.TextColumn("Steam ID", width=80),
                "name": st.column_config.TextColumn("게임명", width=250),
                "csv_count": st.column_config.NumberColumn("CSV 파일 수", width=100),
                "folder": st.column_config.TextColumn("폴더", width=200),
                "path": st.column_config.TextColumn("전체 경로", width=400),
            },
            use_container_width=True,
            hide_index=True,
        )
