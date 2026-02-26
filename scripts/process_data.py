"""
수집된 Gamalytic JSON 데이터를 정리하여 CSV로 변환하는 스크립트
"""

import json
import csv
import os
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "raw_data"
PROCESSED_DIR = PROJECT_ROOT / "processed_data"


def load_json(filename):
    """JSON 파일 로드"""
    filepath = RAW_DATA_DIR / filename
    if not filepath.exists():
        print(f"  [스킵] 파일 없음: {filepath}")
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def timestamp_to_date(ts):
    """밀리초 타임스탬프를 날짜 문자열로 변환"""
    if ts is None or ts == 0:
        return ""
    try:
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return ""


def flatten_game_list(games):
    """게임 리스트 데이터를 플랫한 딕셔너리 리스트로 변환"""
    rows = []
    for game in games:
        row = {
            "steam_id": game.get("steamId", ""),
            "name": game.get("name", ""),
            "price": game.get("price", 0),
            "copies_sold": game.get("copiesSold", 0),
            "revenue": game.get("revenue", 0),
            "reviews": game.get("reviews", 0),
            "review_score": game.get("reviewScore", 0),
            "release_date": timestamp_to_date(game.get("releaseDate")),
            "first_release_date": timestamp_to_date(game.get("firstReleaseDate")),
            "early_access": game.get("earlyAccess", False),
            "unreleased": game.get("unreleased", False),
            "genres": "|".join(game.get("genres", [])),
            "developers": "|".join(game.get("developers", [])),
            "publishers": "|".join(game.get("publishers", [])),
            "publisher_class": game.get("publisherClass", ""),
        }
        rows.append(row)
    return rows


def flatten_game_detail(game):
    """게임 상세 데이터를 플랫한 딕셔너리로 변환"""
    row = {
        "steam_id": game.get("steamId", ""),
        "name": game.get("name", ""),
        "description": game.get("description", ""),
        "price": game.get("price", 0),
        "copies_sold": game.get("copiesSold", 0),
        "revenue": game.get("revenue", 0),
        "owners": game.get("owners", 0),
        "reviews": game.get("reviews", 0),
        "review_score": game.get("reviewScore", 0),
        "followers": game.get("followers", 0),
        "avg_playtime_hours": round(game.get("avgPlaytime", 0), 2),
        "release_date": timestamp_to_date(game.get("releaseDate")),
        "first_release_date": timestamp_to_date(game.get("firstReleaseDate")),
        "early_access": game.get("earlyAccess", False),
        "unreleased": game.get("unreleased", False),
        "genres": "|".join(game.get("genres", [])),
        "tags": "|".join(game.get("tags", [])[:10]),
        "features": "|".join(game.get("features", [])),
        "languages": "|".join(game.get("languages", [])),
        "language_count": len(game.get("languages", [])),
        "developers": "|".join(game.get("developers", [])),
        "publishers": "|".join(game.get("publishers", [])),
        "publisher_class": game.get("publisherClass", ""),
    }

    # 국가별 데이터 상위 5개
    country_data = game.get("countryData", {})
    if country_data:
        sorted_countries = sorted(country_data.items(), key=lambda x: x[1], reverse=True)[:5]
        for i, (country, pct) in enumerate(sorted_countries, 1):
            row[f"top_country_{i}"] = country
            row[f"top_country_{i}_pct"] = pct

    return row


def save_csv(rows, filename):
    """딕셔너리 리스트를 CSV로 저장"""
    if not rows:
        print(f"  [스킵] 데이터 없음: {filename}")
        return

    filepath = PROCESSED_DIR / filename
    # 모든 행에서 등장하는 필드를 수집 (일부 행에만 있는 필드 포함)
    all_fields = {}
    for row in rows:
        for key in row.keys():
            all_fields[key] = True
    fieldnames = list(all_fields.keys())

    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    print(f"  -> CSV 저장: {filepath} ({len(rows)}행)")


def process_list_files():
    """리스트 형태의 JSON 파일들을 CSV로 변환"""
    list_files = [
        ("top_revenue_games_list.json", "top_revenue_games.csv"),
        ("top_selling_games_list.json", "top_selling_games.csv"),
        ("recent_releases_list.json", "recent_releases.csv"),
        ("indie_gems_list.json", "indie_gems.csv"),
        ("free_to_play_list.json", "free_to_play.csv"),
        ("high_playtime_list.json", "high_playtime.csv"),
    ]

    for json_file, csv_file in list_files:
        print(f"\n처리: {json_file}")
        data = load_json(json_file)
        if data:
            rows = flatten_game_list(data)
            save_csv(rows, csv_file)


def process_detail_files():
    """상세 데이터 JSON 파일들을 CSV로 변환"""
    detail_files = [
        ("top_revenue_games_details.json", "top_revenue_details.csv"),
        ("recent_releases_details.json", "recent_releases_details.csv"),
        ("indie_gems_details.json", "indie_gems_details.csv"),
    ]

    for json_file, csv_file in detail_files:
        print(f"\n처리: {json_file}")
        data = load_json(json_file)
        if data:
            rows = [flatten_game_detail(game) for game in data]
            save_csv(rows, csv_file)


def process_genre_files():
    """장르별 데이터를 통합 CSV로 변환"""
    print("\n처리: 장르별 데이터 통합")
    genres = [
        "Action", "Adventure", "RPG", "Strategy", "Simulation",
        "Indie", "Casual", "Racing", "Sports", "Puzzle"
    ]

    all_rows = []
    for genre in genres:
        filename = f"genre_{genre.lower()}_games.json"
        data = load_json(filename)
        if data:
            rows = flatten_game_list(data)
            for row in rows:
                row["category_genre"] = genre
            all_rows.extend(rows)

    save_csv(all_rows, "all_genres_combined.csv")


def process_tag_files():
    """태그별 데이터를 통합 CSV로 변환"""
    print("\n처리: 태그별 데이터 통합")
    tags = [
        "Roguelike", "Survival", "Open World", "Multiplayer",
        "Singleplayer", "Co-op", "VR", "Early Access",
        "Free To Play", "Horror"
    ]

    all_rows = []
    for tag in tags:
        filename = f"tag_{tag.lower().replace(' ', '_')}_games.json"
        data = load_json(filename)
        if data:
            rows = flatten_game_list(data)
            for row in rows:
                row["category_tag"] = tag
            all_rows.extend(rows)

    save_csv(all_rows, "all_tags_combined.csv")


def create_master_dataset():
    """모든 수집된 게임을 중복 제거하여 마스터 데이터셋 생성"""
    print("\n처리: 마스터 데이터셋 생성")
    seen_ids = set()
    all_games = []

    # 모든 리스트 JSON 파일에서 게임 수집
    for json_file in RAW_DATA_DIR.glob("*_list.json"):
        data = load_json(json_file.name)
        if data and isinstance(data, list):
            for game in data:
                steam_id = game.get("steamId")
                if steam_id and steam_id not in seen_ids:
                    seen_ids.add(steam_id)
                    all_games.append(game)

    # 장르/태그별 파일에서도 수집
    for json_file in RAW_DATA_DIR.glob("genre_*.json"):
        data = load_json(json_file.name)
        if data and isinstance(data, list):
            for game in data:
                steam_id = game.get("steamId")
                if steam_id and steam_id not in seen_ids:
                    seen_ids.add(steam_id)
                    all_games.append(game)

    for json_file in RAW_DATA_DIR.glob("tag_*.json"):
        data = load_json(json_file.name)
        if data and isinstance(data, list):
            for game in data:
                steam_id = game.get("steamId")
                if steam_id and steam_id not in seen_ids:
                    seen_ids.add(steam_id)
                    all_games.append(game)

    rows = flatten_game_list(all_games)
    save_csv(rows, "master_all_games.csv")
    print(f"  총 고유 게임 수: {len(all_games)}")


def main():
    """전체 데이터 처리 실행"""
    print("=" * 60)
    print("데이터 정리 및 CSV 변환 시작")
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # 리스트 데이터 처리
    process_list_files()

    # 상세 데이터 처리
    process_detail_files()

    # 장르별 통합
    process_genre_files()

    # 태그별 통합
    process_tag_files()

    # 마스터 데이터셋
    create_master_dataset()

    print("\n" + "=" * 60)
    print("데이터 정리 완료!")
    print(f"완료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"출력 경로: {PROCESSED_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
