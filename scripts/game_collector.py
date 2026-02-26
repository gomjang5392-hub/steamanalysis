"""
Gamalytic API 게임 상세 데이터 수집 및 CSV 변환 모듈
Steam ID를 입력받아 게임 데이터를 가져오고 카테고리별 CSV로 저장합니다.
"""

import csv
import re
import requests
import time
from datetime import datetime
from pathlib import Path


# 프로젝트 경로
PROJECT_ROOT = Path(__file__).parent.parent
GAME_DATA_DIR = PROJECT_ROOT / "Game Detail data"
BASE_URL = "https://api.gamalytic.com"


def load_api_key():
    """프로젝트 루트의 .env 파일에서 API 키를 로드합니다."""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GAMALYTIC_API_KEY="):
                    return line.split("=", 1)[1]
    return None


def timestamp_to_date(ts):
    """밀리초 타임스탬프를 YYYY-MM-DD 문자열로 변환합니다."""
    if ts is None or ts == 0:
        return ""
    try:
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return ""


def sanitize_name(name):
    """게임명을 파일시스템 안전한 폴더명으로 변환합니다."""
    # 파일시스템에서 사용 불가한 문자 제거
    sanitized = re.sub(r'[<>:"/\\|?*]', '', name)
    # 연속 공백 정리
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    # 길이 제한
    if len(sanitized) > 100:
        sanitized = sanitized[:100].strip()
    return sanitized


def fetch_game(steam_id, api_key=None):
    """Gamalytic API에서 게임 상세 데이터를 가져옵니다."""
    if api_key is None:
        api_key = load_api_key()
    if not api_key:
        return None, "API 키가 설정되지 않았습니다. .env 파일을 확인하세요."

    url = f"{BASE_URL}/game/{steam_id}"
    params = {"api_key": api_key}

    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 404:
            return None, f"Steam ID {steam_id}에 해당하는 게임을 찾을 수 없습니다."
        response.raise_for_status()
        data = response.json()
        if not data or not data.get("name"):
            return None, f"Steam ID {steam_id}에 대한 유효한 데이터가 없습니다."
        return data, None
    except requests.exceptions.Timeout:
        return None, "API 요청 시간이 초과되었습니다. 다시 시도해주세요."
    except requests.exceptions.RequestException as e:
        return None, f"API 요청 실패: {str(e)}"


# ─── CSV 변환 함수 ───────────────────────────────────────


def export_game_info(game):
    """기본 게임 정보 CSV 데이터를 생성합니다."""
    return [{
        "steam_id": game.get("steamId", ""),
        "name": game.get("name", ""),
        "description": game.get("description", ""),
        "price": game.get("price", 0),
        "header_image_url": game.get("headerImageUrl", ""),
        "capsule_image_url": game.get("capsuleImageUrl", ""),
        "item_type": game.get("itemType", ""),
        "publisher_class": game.get("publisherClass", ""),
        "early_access": game.get("earlyAccess", False),
        "unreleased": game.get("unreleased", False),
        "release_date": timestamp_to_date(game.get("releaseDate")),
        "first_release_date": timestamp_to_date(game.get("firstReleaseDate")),
        "ea_release_date": timestamp_to_date(game.get("EAReleaseDate")),
        "early_access_exit_date": timestamp_to_date(game.get("earlyAccessExitDate")),
        "developers": "|".join(game.get("developers", [])),
        "publishers": "|".join(game.get("publishers", [])),
    }]


def export_player_stats(game):
    """플레이어 통계 CSV 데이터를 생성합니다."""
    return [{
        "copies_sold": game.get("copiesSold", 0),
        "revenue": game.get("revenue", 0),
        "owners": game.get("owners", 0),
        "wishlists": game.get("wishlists", 0),
        "reviews": game.get("reviews", 0),
        "reviews_steam": game.get("reviewsSteam", 0),
        "review_score": game.get("reviewScore", 0),
        "steam_percent": game.get("steamPercent", 0),
        "followers": game.get("followers", 0),
        "players": game.get("players", 0),
        "avg_playtime_hours": round(game.get("avgPlaytime", 0), 2),
        "accuracy": game.get("accuracy", 0),
    }]


def export_country_data(game):
    """국가별 유저 비율 CSV 데이터를 생성합니다."""
    country_data = game.get("countryData", {})
    rows = []
    for code, pct in sorted(country_data.items(), key=lambda x: x[1], reverse=True):
        rows.append({"country_code": code, "percentage": pct})
    return rows


def export_playtime_distribution(game):
    """플레이타임 분포 CSV 데이터를 생성합니다."""
    pt = game.get("playtimeData", {})
    rows = []
    dist = pt.get("distribution", {})
    for bucket, pct in dist.items():
        rows.append({"time_bucket": bucket, "percentage": pct})
    median = pt.get("median")
    if median is not None:
        rows.append({"time_bucket": "median", "percentage": round(median, 2)})
    return rows


def export_audience_overlap(game):
    """중복 유저 게임 CSV 데이터를 생성합니다."""
    rows = []
    for item in game.get("audienceOverlap", []):
        rows.append({
            "steam_id": item.get("steamId", ""),
            "overlap_coefficient": round(item.get("link", 0), 6),
            "name": item.get("name", ""),
            "header_url": item.get("headerUrl", ""),
            "release_date": timestamp_to_date(item.get("releaseDate")),
            "price": item.get("price", 0),
            "genres": "|".join(item.get("genres", [])),
            "copies_sold": item.get("copiesSold", 0),
            "revenue": item.get("revenue", 0),
        })
    return rows


def export_also_played(game):
    """함께 플레이한 게임 CSV 데이터를 생성합니다."""
    rows = []
    for item in game.get("alsoPlayed", []):
        rows.append({
            "steam_id": item.get("steamId", ""),
            "play_coefficient": round(item.get("link", 0), 6),
            "name": item.get("name", ""),
            "header_url": item.get("headerUrl", ""),
            "release_date": timestamp_to_date(item.get("releaseDate")),
            "price": item.get("price", 0),
            "genres": "|".join(item.get("genres", [])),
            "copies_sold": item.get("copiesSold", 0),
            "revenue": item.get("revenue", 0),
        })
    return rows


def export_history(game):
    """일별 히스토리 CSV 데이터를 생성합니다."""
    rows = []
    for h in game.get("history", []):
        rows.append({
            "date": timestamp_to_date(h.get("timeStamp")),
            "reviews": h.get("reviews", ""),
            "price": h.get("price", ""),
            "score": h.get("score", ""),
            "rank": h.get("rank", ""),
            "followers": h.get("followers", ""),
            "wishlists": h.get("wishlists", ""),
            "players_ccu": h.get("players", ""),
            "avg_playtime_hours": h.get("avgPlaytime", ""),
            "sales": h.get("sales", ""),
            "revenue": h.get("revenue", ""),
        })
    return rows


def export_tags_genres_features(game):
    """장르, 태그, 기능, 언어 CSV 데이터를 생성합니다."""
    return [{
        "genres": "|".join(game.get("genres", [])),
        "tags": "|".join(game.get("tags", [])),
        "features": "|".join(game.get("features", [])),
        "languages": "|".join(game.get("languages", [])),
        "language_count": len(game.get("languages", [])),
        "developers": "|".join(game.get("developers", [])),
        "publishers": "|".join(game.get("publishers", [])),
    }]


def export_estimate_details(game):
    """추정 상세 CSV 데이터를 생성합니다."""
    est = game.get("estimateDetails", {})
    return [{
        "rank_based": est.get("rankBased", ""),
        "playtime_based": est.get("playtimeBased", ""),
        "review_based": est.get("reviewBased", ""),
    }]


# ─── CSV 저장 ────────────────────────────────────────────


def write_csv(rows, filepath):
    """딕셔너리 리스트를 CSV 파일로 저장합니다."""
    if not rows:
        return 0

    # 모든 행에서 필드 수집
    all_fields = {}
    for row in rows:
        for key in row.keys():
            all_fields[key] = True
    fieldnames = list(all_fields.keys())

    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    return len(rows)


# CSV 내보내기 정의: (함수, 파일명, 설명)
CSV_EXPORTS = [
    (export_game_info, "game_info.csv", "기본 게임 정보"),
    (export_player_stats, "player_stats.csv", "플레이어 통계"),
    (export_country_data, "country_data.csv", "국가별 유저 비율"),
    (export_playtime_distribution, "playtime_distribution.csv", "플레이타임 분포"),
    (export_audience_overlap, "audience_overlap.csv", "중복 유저 게임"),
    (export_also_played, "also_played.csv", "함께 플레이한 게임"),
    (export_history, "history.csv", "일별 히스토리"),
    (export_tags_genres_features, "tags_genres_features.csv", "장르/태그/기능"),
    (export_estimate_details, "estimate_details.csv", "추정 상세"),
]


def save_all_csvs(game_data, output_dir=None):
    """게임 데이터를 카테고리별 CSV 파일로 일괄 저장합니다.

    Returns:
        list of dict: [{name, file, rows, description}, ...]
    """
    game_name = game_data.get("name", "Unknown")
    folder_name = sanitize_name(game_name)

    if output_dir is None:
        output_dir = GAME_DATA_DIR / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for export_func, filename, description in CSV_EXPORTS:
        filepath = output_dir / filename
        rows = export_func(game_data)
        count = write_csv(rows, filepath)
        results.append({
            "name": filename,
            "file": str(filepath),
            "rows": count,
            "description": description,
        })

    return results, str(output_dir)


def get_collected_games():
    """이미 수집된 게임 목록을 반환합니다."""
    games = []
    if not GAME_DATA_DIR.exists():
        return games

    for folder in sorted(GAME_DATA_DIR.iterdir()):
        if not folder.is_dir():
            continue

        # game_info.csv에서 게임 정보 읽기
        info_file = folder / "game_info.csv"
        steam_id = ""
        name = folder.name
        if info_file.exists():
            with open(info_file, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    steam_id = row.get("steam_id", "")
                    name = row.get("name", folder.name)
                    break

        csv_files = list(folder.glob("*.csv"))
        games.append({
            "folder": folder.name,
            "steam_id": steam_id,
            "name": name,
            "csv_count": len(csv_files),
            "path": str(folder),
        })

    return games
