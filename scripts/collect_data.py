"""
Gamalytic API 데이터 수집 스크립트
- 매출 상위 게임
- 장르별 게임
- 최근 출시 게임
- 인디 게임
등 다양한 기준으로 포괄적으로 Steam 게임 데이터를 수집합니다.
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "raw_data"

# .env 파일에서 API 키 로드
def load_api_key():
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GAMALYTIC_API_KEY="):
                    return line.split("=", 1)[1]
    raise ValueError(".env 파일에서 GAMALYTIC_API_KEY를 찾을 수 없습니다.")

API_KEY = load_api_key()
BASE_URL = "https://api.gamalytic.com"

# API 요청 간 대기 시간 (초) - rate limit 방지
REQUEST_DELAY = 0.5


def api_request(endpoint, params=None):
    """Gamalytic API 요청을 수행합니다."""
    url = f"{BASE_URL}/{endpoint}"
    if params is None:
        params = {}
    params["api_key"] = API_KEY

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        time.sleep(REQUEST_DELAY)
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"  [오류] API 요청 실패: {url} - {e}")
        return None


def fetch_game_list(category_name, params, max_pages=10):
    """게임 목록을 페이지 단위로 수집합니다."""
    all_games = []
    page = 0

    while page < max_pages:
        request_params = {**params, "page": page, "limit": 100}
        print(f"  [{category_name}] 페이지 {page + 1}/{max_pages} 수집 중...")

        data = api_request("steam-games/list", request_params)
        if data is None or not data.get("result"):
            break

        all_games.extend(data["result"])
        total_pages = data.get("pages", 0)
        print(f"    -> {len(data['result'])}개 게임 수집 (총 {data.get('total', '?')}개 중)")

        if page + 1 >= total_pages:
            break
        page += 1

    return all_games


def fetch_game_details(steam_ids, category_name):
    """개별 게임의 상세 데이터를 수집합니다."""
    details = []
    total = len(steam_ids)

    for i, steam_id in enumerate(steam_ids):
        print(f"  [{category_name}] 상세 데이터 {i + 1}/{total}: ID {steam_id}")
        data = api_request(f"game/{steam_id}")
        if data:
            details.append(data)

    return details


def save_data(data, filename):
    """데이터를 JSON 파일로 저장합니다."""
    filepath = RAW_DATA_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  -> 저장 완료: {filepath} ({len(data) if isinstance(data, list) else 1}건)")


def collect_top_revenue_games():
    """매출 상위 게임 수집 (상위 500개)"""
    print("\n=== 1. 매출 상위 게임 수집 ===")
    params = {
        "sort": "revenue",
        "sort_mode": "desc",
    }
    games = fetch_game_list("매출 상위", params, max_pages=5)
    save_data(games, "top_revenue_games_list.json")

    # 상위 100개 게임의 상세 데이터 수집
    top_ids = [g["steamId"] for g in games[:100]]
    details = fetch_game_details(top_ids, "매출 상위 상세")
    save_data(details, "top_revenue_games_details.json")

    return games


def collect_top_selling_games():
    """판매량 상위 게임 수집 (상위 500개)"""
    print("\n=== 2. 판매량 상위 게임 수집 ===")
    params = {
        "sort": "copiesSold",
        "sort_mode": "desc",
    }
    games = fetch_game_list("판매량 상위", params, max_pages=5)
    save_data(games, "top_selling_games_list.json")
    return games


def collect_by_genre():
    """주요 장르별 게임 수집"""
    print("\n=== 3. 장르별 게임 수집 ===")
    genres = [
        "Action", "Adventure", "RPG", "Strategy", "Simulation",
        "Indie", "Casual", "Racing", "Sports", "Puzzle"
    ]

    all_genre_data = {}
    for genre in genres:
        print(f"\n  --- 장르: {genre} ---")
        params = {
            "sort": "revenue",
            "sort_mode": "desc",
            "genres": genre,
        }
        games = fetch_game_list(f"장르-{genre}", params, max_pages=3)
        all_genre_data[genre] = games
        save_data(games, f"genre_{genre.lower()}_games.json")

    return all_genre_data


def collect_by_tags():
    """인기 태그별 게임 수집"""
    print("\n=== 4. 인기 태그별 게임 수집 ===")
    tags = [
        "Roguelike", "Survival", "Open World", "Multiplayer",
        "Singleplayer", "Co-op", "VR", "Early Access",
        "Free To Play", "Horror"
    ]

    all_tag_data = {}
    for tag in tags:
        print(f"\n  --- 태그: {tag} ---")
        params = {
            "sort": "revenue",
            "sort_mode": "desc",
            "tags": tag,
        }
        games = fetch_game_list(f"태그-{tag}", params, max_pages=2)
        all_tag_data[tag] = games
        save_data(games, f"tag_{tag.lower().replace(' ', '_')}_games.json")

    return all_tag_data


def collect_recent_releases():
    """최근 출시 게임 수집 (최근 6개월)"""
    print("\n=== 5. 최근 출시 게임 수집 ===")
    six_months_ago = datetime.now() - timedelta(days=180)
    date_min = int(six_months_ago.timestamp() * 1000)

    params = {
        "sort": "revenue",
        "sort_mode": "desc",
        "date_min": date_min,
    }
    games = fetch_game_list("최근 출시", params, max_pages=5)
    save_data(games, "recent_releases_list.json")

    # 상위 50개 상세 데이터
    top_ids = [g["steamId"] for g in games[:50]]
    details = fetch_game_details(top_ids, "최근 출시 상세")
    save_data(details, "recent_releases_details.json")

    return games


def collect_indie_gems():
    """인디 게임 중 평점 높은 게임 수집"""
    print("\n=== 6. 인디 보석 게임 수집 ===")
    params = {
        "sort": "reviewScore",
        "sort_mode": "desc",
        "genres": "Indie",
        "reviews_min": 100,
        "score_min": 90,
    }
    games = fetch_game_list("인디 보석", params, max_pages=3)
    save_data(games, "indie_gems_list.json")

    # 상위 50개 상세
    top_ids = [g["steamId"] for g in games[:50]]
    details = fetch_game_details(top_ids, "인디 보석 상세")
    save_data(details, "indie_gems_details.json")

    return games


def collect_free_to_play():
    """F2P 게임 수집"""
    print("\n=== 7. Free-to-Play 게임 수집 ===")
    params = {
        "sort": "revenue",
        "sort_mode": "desc",
        "price_max": 0,
    }
    games = fetch_game_list("F2P", params, max_pages=3)
    save_data(games, "free_to_play_list.json")
    return games


def collect_high_playtime():
    """평균 플레이타임이 높은 게임 수집"""
    print("\n=== 8. 높은 플레이타임 게임 수집 ===")
    params = {
        "sort": "avgPlaytime",
        "sort_mode": "desc",
        "reviews_min": 500,
    }
    games = fetch_game_list("높은 플레이타임", params, max_pages=3)
    save_data(games, "high_playtime_list.json")
    return games


def collect_steam_stats():
    """Steam 전체 통계 데이터 수집"""
    print("\n=== 9. Steam 전체 통계 수집 ===")
    data = api_request("steam-games/stats")
    if data:
        save_data(data, "steam_overall_stats.json")
    return data


def main():
    """전체 데이터 수집 실행"""
    print("=" * 60)
    print("Gamalytic 데이터 수집 시작")
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"저장 경로: {RAW_DATA_DIR}")
    print("=" * 60)

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    results = {}

    # 1. 매출 상위
    results["top_revenue"] = collect_top_revenue_games()

    # 2. 판매량 상위
    results["top_selling"] = collect_top_selling_games()

    # 3. 장르별
    results["by_genre"] = collect_by_genre()

    # 4. 태그별
    results["by_tag"] = collect_by_tags()

    # 5. 최근 출시
    results["recent"] = collect_recent_releases()

    # 6. 인디 보석
    results["indie_gems"] = collect_indie_gems()

    # 7. F2P
    results["f2p"] = collect_free_to_play()

    # 8. 높은 플레이타임
    results["high_playtime"] = collect_high_playtime()

    # 9. Steam 전체 통계
    results["stats"] = collect_steam_stats()

    # 수집 결과 요약
    print("\n" + "=" * 60)
    print("수집 완료 요약")
    print("=" * 60)

    summary = {
        "collection_date": datetime.now().isoformat(),
        "categories": {}
    }

    for key, value in results.items():
        if isinstance(value, list):
            count = len(value)
        elif isinstance(value, dict) and not isinstance(value, type(None)):
            if any(isinstance(v, list) for v in value.values()):
                count = sum(len(v) for v in value.values() if isinstance(v, list))
            else:
                count = 1
        else:
            count = 0
        summary["categories"][key] = count
        print(f"  {key}: {count}건")

    save_data(summary, "collection_summary.json")

    print(f"\n완료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
