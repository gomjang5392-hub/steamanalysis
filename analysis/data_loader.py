"""
게임 데이터 로드·필터·집계 모듈
history는 누적 판매량/수익 시계열이므로, 연도별 증분을 계산한다.
"""
import json
import glob
import os
from datetime import datetime
from collections import defaultdict

import streamlit as st


GAMES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "raw_data", "games")
PARQUET_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "raw_data", "games_data.parquet")


def _parse_parquet_value(val):
    """Parquet에서 읽은 값을 원래 Python 타입으로 복원."""
    import math
    # NaN / None 처리
    try:
        if isinstance(val, float) and math.isnan(val):
            return None
    except TypeError:
        pass
    if val is None:
        return None
    # JSON 직렬화된 dict/list 복원 ([ 또는 { 로 시작하는 문자열)
    if isinstance(val, str) and val and val[0] in ('[', '{'):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, (list, dict)):
                return parsed
        except Exception:
            pass
    return val


@st.cache_data(show_spinner="게임 데이터 로딩 중...")
def load_all_games() -> list[dict]:
    """
    Parquet 우선 로드 → 없으면 JSON 폴백.
    Streamlit Cloud 배포 시 Parquet 파일 사용.
    """
    import pandas as pd

    # Parquet 파일이 있으면 우선 사용
    if os.path.exists(PARQUET_PATH):
        df = pd.read_parquet(PARQUET_PATH)
        games = []
        for _, row in df.iterrows():
            game = {col: _parse_parquet_value(row[col]) for col in df.columns}
            games.append(game)
        return games

    # 폴백: JSON 개별 파일 로드 (로컬 개발용)
    pattern = os.path.join(GAMES_DIR, "*.json")
    games = []
    for path in glob.glob(pattern):
        if "_progress" in os.path.basename(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            games.append(data)
        except Exception:
            pass
    return games


def _release_year(game: dict) -> int | None:
    """게임 출시 연도 반환 (ms 타임스탬프 → 연도)."""
    ts = game.get("releaseDate") or game.get("firstReleaseDate")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts) / 1000).year
        except Exception:
            pass
    return None


def filter_games(
    games: list[dict],
    tags: list[str] | None = None,
    genres: list[str] | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    sold_min: int | None = None,
    reviews_min: int | None = None,
) -> list[dict]:
    """조건 조합 필터링."""
    result = []
    for g in games:
        if tags:
            game_tags = g.get("tags") or []
            if not any(t in game_tags for t in tags):
                continue
        if genres:
            game_genres = g.get("genres") or []
            if not any(gr in game_genres for gr in genres):
                continue
        if year_min or year_max:
            yr = _release_year(g)
            if yr is None:
                continue
            if year_min and yr < year_min:
                continue
            if year_max and yr > year_max:
                continue
        if sold_min is not None:
            if (g.get("copiesSold") or 0) < sold_min:
                continue
        if reviews_min is not None:
            if (g.get("reviews") or 0) < reviews_min:
                continue
        result.append(g)
    return result


def _get_yearly_increments(history: list[dict]) -> dict[int, dict]:
    """
    누적 history에서 연도별 증분 (sales, revenue) 계산.
    각 연도의 마지막 값 - 전년도 마지막 값.
    """
    # 연도별 마지막 항목 수집
    by_year: dict[int, dict] = {}
    for item in history:
        ts = item.get("timeStamp")
        if not ts:
            continue
        try:
            yr = datetime.fromtimestamp(int(ts) / 1000).year
        except Exception:
            continue
        by_year[yr] = item  # 같은 연도에서 덮어쓰기 → 마지막 값

    # 정렬된 연도 목록
    years = sorted(by_year.keys())
    increments: dict[int, dict] = {}
    prev_sales = 0
    prev_revenue = 0
    for yr in years:
        item = by_year[yr]
        cur_sales = item.get("sales") or 0
        cur_revenue = item.get("revenue") or 0
        increments[yr] = {
            "sales": max(0, cur_sales - prev_sales),
            "revenue": max(0, cur_revenue - prev_revenue),
            "cumulative_sales": cur_sales,
            "cumulative_revenue": cur_revenue,
            "score": item.get("score") or 0,
        }
        prev_sales = cur_sales
        prev_revenue = cur_revenue
    return increments


def get_yearly_trends(games: list[dict]) -> dict[int, dict]:
    """
    전체 게임 목록의 연도별 집계.
    반환: {year: {revenue, sales, game_count, avg_score}}
    """
    totals: dict[int, dict] = defaultdict(lambda: {"revenue": 0, "sales": 0, "game_count": 0, "score_sum": 0, "score_count": 0})

    for game in games:
        history = game.get("history") or []
        increments = _get_yearly_increments(history)
        for yr, data in increments.items():
            totals[yr]["revenue"] += data["revenue"]
            totals[yr]["sales"] += data["sales"]
            if data["sales"] > 0:
                totals[yr]["game_count"] += 1
            if data["score"] > 0:
                totals[yr]["score_sum"] += data["score"]
                totals[yr]["score_count"] += 1

    result = {}
    for yr, data in sorted(totals.items()):
        result[yr] = {
            "revenue": data["revenue"],
            "sales": data["sales"],
            "game_count": data["game_count"],
            "avg_score": (data["score_sum"] / data["score_count"]) if data["score_count"] > 0 else 0,
        }
    return result


def get_top_games(games: list[dict], n: int = 20, sort_by: str = "revenue") -> list[dict]:
    """상위 N개 게임 반환."""
    def sort_key(g):
        return g.get(sort_by) or 0

    return sorted(games, key=sort_key, reverse=True)[:n]


def get_genre_stats(games: list[dict]) -> dict[str, dict]:
    """장르별 통계 (평균 수익·판매량·리뷰 점수·게임 수)."""
    stats: dict[str, dict] = defaultdict(lambda: {
        "revenue_sum": 0, "sales_sum": 0, "score_sum": 0,
        "count": 0, "score_count": 0
    })

    for g in games:
        for genre in (g.get("genres") or []):
            stats[genre]["revenue_sum"] += g.get("revenue") or 0
            stats[genre]["sales_sum"] += g.get("copiesSold") or 0
            stats[genre]["count"] += 1
            score = g.get("reviewScore") or 0
            if score > 0:
                stats[genre]["score_sum"] += score
                stats[genre]["score_count"] += 1

    result = {}
    for genre, data in sorted(stats.items(), key=lambda x: x[1]["revenue_sum"], reverse=True):
        count = data["count"]
        result[genre] = {
            "game_count": count,
            "avg_revenue": data["revenue_sum"] / count if count else 0,
            "avg_sales": data["sales_sum"] / count if count else 0,
            "avg_score": data["score_sum"] / data["score_count"] if data["score_count"] else 0,
            "total_revenue": data["revenue_sum"],
        }
    return result


def get_tag_stats(games: list[dict]) -> dict[str, dict]:
    """태그별 통계."""
    stats: dict[str, dict] = defaultdict(lambda: {
        "revenue_sum": 0, "sales_sum": 0, "score_sum": 0,
        "count": 0, "score_count": 0
    })

    for g in games:
        for tag in (g.get("tags") or []):
            stats[tag]["revenue_sum"] += g.get("revenue") or 0
            stats[tag]["sales_sum"] += g.get("copiesSold") or 0
            stats[tag]["count"] += 1
            score = g.get("reviewScore") or 0
            if score > 0:
                stats[tag]["score_sum"] += score
                stats[tag]["score_count"] += 1

    result = {}
    for tag, data in sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True):
        count = data["count"]
        result[tag] = {
            "game_count": count,
            "avg_revenue": data["revenue_sum"] / count if count else 0,
            "avg_sales": data["sales_sum"] / count if count else 0,
            "avg_score": data["score_sum"] / data["score_count"] if data["score_count"] else 0,
            "total_revenue": data["revenue_sum"],
        }
    return result


def get_audience_overlap_network(games: list[dict]) -> list[dict]:
    """audienceOverlap 데이터에서 경쟁 관계 추출."""
    edges = []
    seen = set()
    game_ids = {str(g.get("steamId")) for g in games}

    for g in games:
        src_id = str(g.get("steamId"))
        src_name = g.get("name", src_id)
        for overlap in (g.get("audienceOverlap") or []):
            tgt_id = str(overlap.get("steamId"))
            link = overlap.get("link", 0)
            if link < 0.1:
                continue
            key = tuple(sorted([src_id, tgt_id]))
            if key in seen:
                continue
            seen.add(key)
            edges.append({
                "source_id": src_id,
                "source_name": src_name,
                "target_id": tgt_id,
                "target_name": overlap.get("name", tgt_id),
                "link": link,
                "in_dataset": tgt_id in game_ids,
            })
    return edges


def get_common_tags(games: list[dict], top_n: int = 15) -> list[tuple[str, int]]:
    """성공 게임들의 공통 태그 Top N."""
    from collections import Counter
    counter: Counter = Counter()
    for g in games:
        for tag in (g.get("tags") or []):
            counter[tag] += 1
    return counter.most_common(top_n)


def get_price_buckets(games: list[dict]) -> list[dict]:
    """가격대별 게임 목록 (박스플롯용)."""
    buckets = []
    for g in games:
        price = g.get("price") or 0
        if price == 0:
            label = "무료"
        elif price < 5:
            label = "$0~5"
        elif price < 10:
            label = "$5~10"
        elif price < 20:
            label = "$10~20"
        elif price < 30:
            label = "$20~30"
        elif price < 60:
            label = "$30~60"
        else:
            label = "$60+"
        buckets.append({
            "name": g.get("name"),
            "price": price,
            "price_bucket": label,
            "revenue": g.get("revenue") or 0,
            "copiesSold": g.get("copiesSold") or 0,
            "reviewScore": g.get("reviewScore") or 0,
        })
    return buckets


def get_monthly_releases(games: list[dict]) -> list[dict]:
    """월별 신규 출시 게임 수 집계."""
    monthly: dict[str, int] = defaultdict(int)
    for g in games:
        ts = g.get("releaseDate") or g.get("firstReleaseDate")
        if ts:
            try:
                dt = datetime.fromtimestamp(int(ts) / 1000)
                key = dt.strftime("%Y-%m")
                monthly[key] += 1
            except Exception:
                pass
    return [{"month": k, "count": v} for k, v in sorted(monthly.items())]


def summarize_for_claude(games: list[dict], max_games: int = 30) -> str:
    """Claude에게 전달할 데이터 요약 문자열 생성."""
    if not games:
        return "데이터 없음"

    total = len(games)
    revenues = [g.get("revenue") or 0 for g in games]
    sales = [g.get("copiesSold") or 0 for g in games]
    scores = [g.get("reviewScore") or 0 for g in games if g.get("reviewScore")]

    avg_revenue = sum(revenues) / total if total else 0
    avg_sales = sum(sales) / total if total else 0
    avg_score = sum(scores) / len(scores) if scores else 0
    total_revenue = sum(revenues)
    total_sales = sum(sales)

    # 상위 N개 게임
    top_games = sorted(games, key=lambda x: x.get("revenue") or 0, reverse=True)[:max_games]

    lines = [
        f"## 전체 통계 (총 {total}개 게임)",
        f"- 총 수익: ${total_revenue:,.0f}",
        f"- 총 판매량: {total_sales:,}장",
        f"- 평균 수익: ${avg_revenue:,.0f}",
        f"- 평균 판매량: {avg_sales:,.0f}장",
        f"- 평균 리뷰 점수: {avg_score:.1f}/100",
        f"- 히트작 (100만장+): {sum(1 for s in sales if s >= 1_000_000)}개",
        "",
        f"## 상위 {len(top_games)}개 게임",
    ]
    for i, g in enumerate(top_games, 1):
        yr = _release_year(g)
        lines.append(
            f"{i}. {g.get('name', '?')} ({yr}) | "
            f"수익 ${(g.get('revenue') or 0):,.0f} | "
            f"판매 {(g.get('copiesSold') or 0):,}장 | "
            f"리뷰 {g.get('reviewScore', 0)}/100 | "
            f"태그: {', '.join((g.get('tags') or [])[:5])}"
        )

    return "\n".join(lines)


def get_all_tags(games: list[dict], min_count: int = 3) -> list[str]:
    """전체 태그 목록 (등장 횟수 기준 필터)."""
    from collections import Counter
    counter: Counter = Counter()
    for g in games:
        for tag in (g.get("tags") or []):
            counter[tag] += 1
    return [tag for tag, cnt in counter.most_common() if cnt >= min_count]


def get_all_genres(games: list[dict]) -> list[str]:
    """전체 장르 목록."""
    from collections import Counter
    counter: Counter = Counter()
    for g in games:
        for genre in (g.get("genres") or []):
            counter[genre] += 1
    return [genre for genre, _ in counter.most_common()]


# ── 시계열 히스토리 집계 ──────────────────────────────────────────────────────

def get_history_aggregate(
    games: list[dict],
    freq: str = "yearly",
    year_min: int = 2015,
    year_max: int = 2026,
) -> dict:
    """
    여러 게임의 history를 시계열로 집계.

    freq: 'yearly' | 'monthly'
    반환: {period: {
        sales_inc, revenue_inc,        # 증분
        avg_ccu, max_ccu,              # 동시접속자
        avg_score,                     # 리뷰 점수
        avg_playtime,                  # 평균 플레이타임
        avg_price,                     # 평균 가격
        avg_followers,                 # 팔로워
        total_games,                   # 데이터 있는 게임 수
    }}
    """
    # {period: {metric: [values]}}
    period_buckets: dict = defaultdict(lambda: defaultdict(list))

    for game in games:
        history = sorted(game.get("history") or [], key=lambda x: x.get("timeStamp", 0))
        if not history:
            continue

        # 기간별 마지막 항목 수집
        by_period: dict = {}
        for item in history:
            ts = item.get("timeStamp")
            if not ts:
                continue
            try:
                dt = datetime.fromtimestamp(int(ts) / 1000)
            except Exception:
                continue
            if dt.year < year_min or dt.year > year_max:
                continue
            period = dt.year if freq == "yearly" else dt.strftime("%Y-%m")
            by_period[period] = item

        # 증분 계산
        prev_sales = 0
        prev_revenue = 0
        for period in sorted(by_period.keys()):
            item = by_period[period]
            cur_sales = item.get("sales") or 0
            cur_revenue = item.get("revenue") or 0

            period_buckets[period]["sales_inc"].append(max(0, cur_sales - prev_sales))
            period_buckets[period]["revenue_inc"].append(max(0, cur_revenue - prev_revenue))
            period_buckets[period]["ccu"].append(item.get("players") or 0)
            period_buckets[period]["score"].append(item.get("score") or 0)
            period_buckets[period]["playtime"].append(item.get("avgPlaytime") or 0)
            period_buckets[period]["price"].append(item.get("price") or 0)
            period_buckets[period]["followers"].append(item.get("followers") or 0)
            period_buckets[period]["wishlists"].append(item.get("wishlists") or 0)

            prev_sales = cur_sales
            prev_revenue = cur_revenue

    def _avg(lst):
        lst = [x for x in lst if x and x > 0]
        return sum(lst) / len(lst) if lst else 0

    result = {}
    for period, buckets in sorted(period_buckets.items()):
        ccu_list = [x for x in buckets["ccu"] if x > 0]
        result[period] = {
            "sales_inc": sum(buckets["sales_inc"]),
            "revenue_inc": sum(buckets["revenue_inc"]),
            "avg_ccu": _avg(buckets["ccu"]),
            "max_ccu": max(ccu_list) if ccu_list else 0,
            "total_ccu": sum(ccu_list),
            "avg_score": _avg(buckets["score"]),
            "avg_playtime": _avg(buckets["playtime"]),
            "avg_price": _avg(buckets["price"]),
            "avg_followers": _avg(buckets["followers"]),
            "avg_wishlists": _avg(buckets["wishlists"]),
            "total_games": len(buckets["sales_inc"]),
        }
    return result


def get_history_for_game(game: dict, freq: str = "monthly") -> dict:
    """단일 게임의 history를 기간별로 정리."""
    history = sorted(game.get("history") or [], key=lambda x: x.get("timeStamp", 0))
    by_period: dict = {}
    for item in history:
        ts = item.get("timeStamp")
        if not ts:
            continue
        try:
            dt = datetime.fromtimestamp(int(ts) / 1000)
        except Exception:
            continue
        period = dt.year if freq == "yearly" else dt.strftime("%Y-%m")
        by_period[period] = item

    result = {}
    prev_sales = 0
    prev_revenue = 0
    for period in sorted(by_period.keys()):
        item = by_period[period]
        cur_sales = item.get("sales") or 0
        cur_revenue = item.get("revenue") or 0
        result[period] = {
            "sales_inc": max(0, cur_sales - prev_sales),
            "revenue_inc": max(0, cur_revenue - prev_revenue),
            "cumul_sales": cur_sales,
            "cumul_revenue": cur_revenue,
            "ccu": item.get("players") or 0,
            "score": item.get("score") or 0,
            "playtime": item.get("avgPlaytime") or 0,
            "price": item.get("price") or 0,
            "followers": item.get("followers") or 0,
            "wishlists": item.get("wishlists") or 0,
            "reviews": item.get("reviews") or 0,
        }
        prev_sales = cur_sales
        prev_revenue = cur_revenue
    return result


# ── 국가별 집계 ───────────────────────────────────────────────────────────────

def get_country_aggregate(
    games: list[dict],
    weight_by: str = "revenue",
) -> dict[str, float]:
    """
    게임 목록의 국가별 플레이어 비율 가중 평균.
    weight_by: 'revenue' | 'sales' | 'equal'
    반환: {country_code: weighted_avg_pct}
    """
    COUNTRY_NAMES = {
        "us": "미국", "cn": "중국", "ru": "러시아", "de": "독일",
        "gb": "영국", "fr": "프랑스", "br": "브라질", "kr": "한국",
        "jp": "일본", "ca": "캐나다", "au": "호주", "pl": "폴란드",
        "tr": "튀르키예", "ua": "우크라이나", "nl": "네덜란드",
        "se": "스웨덴", "mx": "멕시코", "ar": "아르헨티나",
        "it": "이탈리아", "es": "스페인", "in": "인도", "vn": "베트남",
        "th": "태국", "id": "인도네시아", "sg": "싱가포르",
    }

    weighted: dict[str, float] = defaultdict(float)
    total_weight = 0.0

    for g in games:
        cd = g.get("countryData") or {}
        if not isinstance(cd, dict) or not cd:
            continue
        if weight_by == "revenue":
            w = g.get("revenue") or 1
        elif weight_by == "sales":
            w = g.get("copiesSold") or 1
        else:
            w = 1.0
        total_weight += w
        for code, pct in cd.items():
            weighted[code] += pct * w

    if total_weight == 0:
        return {}

    result = {
        code: round(val / total_weight, 2)
        for code, val in sorted(weighted.items(), key=lambda x: x[1], reverse=True)
    }
    # 국가명 추가
    return {
        f"{COUNTRY_NAMES.get(code, code.upper())} ({code.upper()})": pct
        for code, pct in list(result.items())[:30]
    }


# ── 유저 활동 지표 요약 ───────────────────────────────────────────────────────

def get_activity_summary(games: list[dict]) -> dict:
    """유저 활동 지표 전체 요약."""
    if not games:
        return {}

    def _stats(vals):
        vals = [v for v in vals if v and v > 0]
        if not vals:
            return {"avg": 0, "max": 0, "median": 0, "total": 0}
        vals_sorted = sorted(vals)
        return {
            "avg": sum(vals) / len(vals),
            "max": max(vals),
            "median": vals_sorted[len(vals_sorted) // 2],
            "total": sum(vals),
            "count": len(vals),
        }

    return {
        "players_ccu": _stats([g.get("players") or 0 for g in games]),
        "reviews": _stats([g.get("reviews") or 0 for g in games]),
        "review_score": _stats([g.get("reviewScore") or 0 for g in games]),
        "avg_playtime": _stats([g.get("avgPlaytime") or 0 for g in games]),
        "followers": _stats([g.get("followers") or 0 for g in games]),
        "wishlists": _stats([g.get("wishlists") or 0 for g in games]),
        "owners": _stats([g.get("owners") or 0 for g in games]),
        "steam_percent": _stats([g.get("steamPercent") or 0 for g in games]),
        "price": _stats([g.get("price") or 0 for g in games]),
        "copies_sold": _stats([g.get("copiesSold") or 0 for g in games]),
        "revenue": _stats([g.get("revenue") or 0 for g in games]),
    }


def get_audience_overlap_top(
    games: list[dict],
    top_n: int = 30,
    sort_by: str = "reach_score",
) -> list[dict]:
    """
    전체 게임 목록에서 가장 많이 겹치는 외부 게임 순위.

    sort_by:
      'reach_score'       - 추정 공유 유저 수 (avg_link × copiesSold)
      'avg_link'          - 평균 Link 비율
      'overlap_game_count'- 겹친 게임 수 (광범위성)
      'copies_sold'       - 외부 게임 판매량
    """
    from collections import Counter
    overlap_count: Counter = Counter()
    overlap_data: dict = defaultdict(list)

    for g in games:
        for ao in (g.get("audienceOverlap") or []):
            sid = ao.get("steamId")
            link = ao.get("link") or 0
            if link > 0.05:
                overlap_count[sid] += 1
                overlap_data[sid].append({
                    "name": ao.get("name", sid),
                    "link": link,
                    "genres": ao.get("genres") or [],
                    "copiesSold": ao.get("copiesSold") or 0,
                    "revenue": ao.get("revenue") or 0,
                    "ccu": ao.get("players") or 0,
                })

    total_games = len(games)
    result = []
    for sid, cnt in overlap_count.most_common(top_n * 2):
        items = overlap_data[sid]
        avg_link = sum(x["link"] for x in items) / len(items)

        # 판매량: 여러 게임에서 참조된 값 중 최댓값 사용 (데이터 일관성)
        copies_sold = max((x["copiesSold"] for x in items), default=0)
        revenue = max((x["revenue"] for x in items), default=0)
        ccu = max((x["ccu"] for x in items), default=0)

        # 추정 공유 유저 = avg_link × 외부 게임 판매량
        reach_score = avg_link * copies_sold

        # 겹침 광범위성 = 필터된 게임 중 몇 %가 이 게임을 포함하는지
        overlap_pct = round(cnt / total_games * 100, 1) if total_games > 0 else 0

        result.append({
            "steamId": sid,
            "name": items[0]["name"],
            "overlap_game_count": cnt,
            "overlap_pct": overlap_pct,
            "avg_link": round(avg_link, 3),
            "copies_sold": copies_sold,
            "revenue": revenue,
            "ccu": ccu,
            "reach_score": reach_score,
            "genres": items[0]["genres"],
        })

    sort_keys = {
        "reach_score": lambda x: x["reach_score"],
        "avg_link": lambda x: x["avg_link"],
        "overlap_game_count": lambda x: x["overlap_game_count"],
        "copies_sold": lambda x: x["copies_sold"],
    }
    key_fn = sort_keys.get(sort_by, sort_keys["reach_score"])
    return sorted(result, key=key_fn, reverse=True)[:top_n]


def summarize_full_for_claude(
    games: list[dict],
    selected_metrics: list[str],
    max_games: int = 30,
) -> str:
    """
    Claude에게 전달할 전체 데이터 요약.
    selected_metrics: 포함할 데이터 카테고리 목록
    """
    lines = []
    total = len(games)
    if total == 0:
        return "데이터 없음"

    # 기본 통계
    revenues = [g.get("revenue") or 0 for g in games]
    sales = [g.get("copiesSold") or 0 for g in games]

    lines.append(f"## 기본 통계 (총 {total}개 게임)")
    lines.append(f"- 총 수익: ${sum(revenues):,.0f}")
    lines.append(f"- 총 판매량: {sum(sales):,}장")
    lines.append(f"- 평균 수익: ${sum(revenues)/total:,.0f}")
    lines.append(f"- 평균 판매량: {sum(sales)/total:,.0f}장")

    # 유저 활동 지표
    if "유저 활동 지표" in selected_metrics:
        activity = get_activity_summary(games)
        lines.append("\n## 유저 활동 지표")
        for key, stats in activity.items():
            label_map = {
                "players_ccu": "CCU(동시접속)",
                "reviews": "리뷰 수",
                "review_score": "리뷰 점수",
                "avg_playtime": "평균 플레이타임(h)",
                "followers": "팔로워",
                "wishlists": "위시리스트",
            }
            label = label_map.get(key, key)
            if key in label_map:
                lines.append(
                    f"- {label}: 평균 {stats.get('avg',0):,.0f} / "
                    f"최대 {stats.get('max',0):,.0f} / "
                    f"중앙값 {stats.get('median',0):,.0f}"
                )

    # 시계열 트렌드
    if "시계열 히스토리" in selected_metrics:
        hist = get_history_aggregate(games, freq="yearly")
        lines.append("\n## 연도별 히스토리 트렌드")
        for yr, data in sorted(hist.items()):
            lines.append(
                f"- {yr}년: 판매증분={data['sales_inc']:,} / "
                f"수익증분=${data['revenue_inc']:,.0f} / "
                f"평균CCU={data['avg_ccu']:,.0f} / "
                f"평균점수={data['avg_score']:.1f}"
            )

    # 국가별 데이터
    if "국가별 데이터" in selected_metrics:
        countries = get_country_aggregate(games)
        lines.append("\n## 국가별 플레이어 비율 (상위 15개)")
        for country, pct in list(countries.items())[:15]:
            lines.append(f"- {country}: {pct:.2f}%")

    # 유저 겹침
    if "유저 겹침" in selected_metrics:
        overlaps = get_audience_overlap_top(games, top_n=10, sort_by="reach_score")
        lines.append("\n## 주요 타겟 유저 겹침 게임 (추정 공유 유저 순)")
        for item in overlaps:
            reach_m = item["reach_score"] / 1_000_000
            copies_m = item["copies_sold"] / 1_000_000
            lines.append(
                f"- {item['name']}: link={item['avg_link']:.3f}, "
                f"판매량={copies_m:.1f}M, 추정 공유 유저={reach_m:.1f}M, "
                f"필터 게임 {item['overlap_pct']}%와 겹침"
            )

    # 상위 게임 목록
    top_games = sorted(games, key=lambda x: x.get("revenue") or 0, reverse=True)[:max_games]
    lines.append(f"\n## 상위 {len(top_games)}개 게임")
    for i, g in enumerate(top_games, 1):
        ts = g.get("releaseDate") or g.get("firstReleaseDate")
        yr = datetime.fromtimestamp(int(ts) / 1000).year if ts else "?"
        line = (
            f"{i}. {g.get('name', '?')} ({yr}) | "
            f"수익 ${(g.get('revenue') or 0):,.0f} | "
            f"판매 {(g.get('copiesSold') or 0):,}장 | "
            f"점수 {g.get('reviewScore', 0)}"
        )
        if "유저 활동 지표" in selected_metrics:
            line += (
                f" | CCU {(g.get('players') or 0):,} | "
                f"플레이타임 {(g.get('avgPlaytime') or 0):.0f}h"
            )
        lines.append(line)

    return "\n".join(lines)
