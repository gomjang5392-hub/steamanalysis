"""
Gamalytic API 대량 게임 데이터 수집기

동작 방식:
  1. /steam-games/list 로 조건에 맞는 게임 ID 전체 수집 (페이지네이션)
  2. /game/<appid> 로 게임별 전체 상세 데이터 수집
  3. raw_data/games/<appid>.json 으로 저장

재실행 시 이미 수집된 게임은 건너뜁니다 (_progress.json 참고).
"""

import json
import time
import requests
from datetime import datetime
from pathlib import Path


# ─── 저장 경로 ────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR   = PROJECT_ROOT / "raw_data" / "games"
PROGRESS_FILE = OUTPUT_DIR / "_progress.json"


# ─── API 설정 ─────────────────────────────────────────────────────────────────

BASE_URL      = "https://api.gamalytic.com"
REQUEST_DELAY = 0.5   # 요청 간 기본 대기(초)
RETRY_DELAY   = 10.0  # 실패·Rate-Limit 시 재시도 대기(초)
MAX_RETRIES   = 3     # 요청 최대 재시도 횟수


# ─── 수집 필터  ───────────────────────────────────────────────────────────────
# 아래 값을 수정해 원하는 조건으로 수집하세요.

FILTERS = {
    "sold_min":   1_000_000,   # 누적 판매량 100만 장 이상
    "sort":       "copiesSold",
    "sort_mode":  "desc",

    # ── 출시일 범위 (주석 해제 후 날짜 변경) ──────────────────────────────────
    # "date_min": "2015-01-01",
    # "date_max": "2025-12-31",

    # ── 최소 리뷰 수 (주석 해제 후 숫자 변경) ────────────────────────────────
    # "reviews_min": 100,
}


# ─── 날짜 변환 ────────────────────────────────────────────────────────────────

def to_ms_timestamp(date_str: str) -> int:
    """'YYYY-MM-DD' 문자열을 밀리초 타임스탬프로 변환합니다."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)


def build_params(filters: dict) -> dict:
    """필터 딕셔너리에서 날짜 문자열을 타임스탬프로 변환합니다."""
    params = {}
    for k, v in filters.items():
        if k in ("date_min", "date_max") and isinstance(v, str):
            params[k] = to_ms_timestamp(v)
        else:
            params[k] = v
    return params


# ─── API 키 로드 ──────────────────────────────────────────────────────────────

def load_api_key() -> str:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("GAMALYTIC_API_KEY="):
                    return line.split("=", 1)[1].strip()
    raise ValueError(".env 파일에서 GAMALYTIC_API_KEY를 찾을 수 없습니다.")


# ─── 진행 상황 추적 ───────────────────────────────────────────────────────────

def load_progress() -> dict:
    """이전 수집 진행 상황을 불러옵니다."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "started_at": datetime.now().isoformat(),
        "done": [],
        "failed": [],
    }


def save_progress(progress: dict):
    progress["updated_at"] = datetime.now().isoformat()
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2)


# ─── API 요청 (재시도 포함) ───────────────────────────────────────────────────

def api_get(path: str, params: dict, api_key: str) -> dict | None:
    """GET 요청을 수행합니다. Rate-Limit·오류 시 자동 재시도합니다."""
    url = f"{BASE_URL}/{path}"
    request_params = {**params, "api_key": api_key}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=request_params, timeout=30)

            if resp.status_code == 429:
                wait = RETRY_DELAY * attempt
                print(f"    ⚠ Rate Limit — {wait:.0f}초 대기 후 재시도 ({attempt}/{MAX_RETRIES})")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return resp.json()

        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                print(f"    ⚠ 오류({attempt}/{MAX_RETRIES}): {e}  — {RETRY_DELAY}초 후 재시도")
                time.sleep(RETRY_DELAY)
            else:
                print(f"    ✗ 최종 실패: {e}")
                return None

    return None


# ─── 1단계: 게임 ID 목록 수집 ────────────────────────────────────────────────

def collect_game_ids(api_key: str) -> list[str]:
    """필터 조건에 맞는 모든 게임의 steamId를 수집합니다."""
    base_params = build_params(FILTERS)
    base_params["fields"] = "steamId,name,copiesSold,revenue,reviews"
    base_params["limit"]  = 100

    all_ids: list[str] = []
    page = 0

    print("\n[1단계] 게임 목록 수집 중...")
    while True:
        base_params["page"] = page
        data = api_get("steam-games/list", base_params, api_key)

        if not data or not data.get("result"):
            print("  → 더 이상 결과 없음.")
            break

        results  = data["result"]
        total    = data.get("total", "?")
        total_pg = data.get("pages", 1)

        for item in results:
            sid = str(item.get("steamId", "")).strip()
            if sid:
                all_ids.append(sid)

        print(f"  페이지 {page + 1}/{total_pg}  — 누적 {len(all_ids)}개 / 전체 {total}개")

        if page + 1 >= total_pg:
            break
        page += 1

    print(f"\n  → 총 {len(all_ids)}개 게임 ID 수집 완료")
    return all_ids


# ─── 2단계: 게임별 상세 데이터 수집 ──────────────────────────────────────────

def collect_game_details(appids: list[str], api_key: str) -> dict:
    """각 게임의 전체 상세 데이터를 수집해 JSON으로 저장합니다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    progress = load_progress()

    done_set   = set(progress["done"])
    failed_set = set(progress["failed"])

    # 아직 수집 안 된 항목만 처리
    remaining = [aid for aid in appids if aid not in done_set]
    already   = len(appids) - len(remaining)

    print(f"\n[2단계] 게임 상세 데이터 수집 중...")
    print(f"  전체: {len(appids)}개 | 기수집: {already}개 | 남은: {len(remaining)}개\n")

    for i, appid in enumerate(remaining, start=1):
        out_file = OUTPUT_DIR / f"{appid}.json"
        label    = f"[{i}/{len(remaining)}] {appid}"

        data = api_get(f"game/{appid}", {}, api_key)

        if data:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            name = data.get("name", "Unknown")
            sold = data.get("copiesSold", 0)
            print(f"  ✓ {label}  →  {name}  ({sold:,} 판매)")

            done_set.add(appid)
            progress["done"] = list(done_set)
            failed_set.discard(appid)
            progress["failed"] = list(failed_set)
        else:
            print(f"  ✗ {label}  →  수집 실패")
            failed_set.add(appid)
            progress["failed"] = list(failed_set)

        # 10개 단위로 진행 상황 저장 (중단 시 복구 가능)
        if i % 10 == 0:
            save_progress(progress)

    save_progress(progress)
    return progress


# ─── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    api_key = load_api_key()

    print("=" * 60)
    print("Gamalytic 대량 게임 데이터 수집기")
    print(f"시작:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"저장:   {OUTPUT_DIR}")
    print(f"필터:   {FILTERS}")
    print("=" * 60)

    # 1단계: 조건에 맞는 게임 ID 목록
    appids = collect_game_ids(api_key)

    if not appids:
        print("\n조건에 맞는 게임이 없습니다. FILTERS를 확인하세요.")
        return

    # 2단계: 게임별 상세 데이터 수집
    progress = collect_game_details(appids, api_key)

    # 완료 요약
    print("\n" + "=" * 60)
    print("수집 완료")
    print(f"  성공: {len(progress['done'])}개")
    print(f"  실패: {len(progress['failed'])}개")
    if progress["failed"]:
        print(f"  실패 목록: {progress['failed'][:10]}{'...' if len(progress['failed']) > 10 else ''}")
    print(f"  저장 위치: {OUTPUT_DIR}")
    print(f"완료:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
