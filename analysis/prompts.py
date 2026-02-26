"""
분석 유형별 시스템 프롬프트 + 사용자 프롬프트 빌더.
"""
from analysis.data_loader import _parse_field

SYSTEM_PROMPT = """당신은 Steam 게임 시장 전문 애널리스트입니다.

Gamalytic API로 수집한 실제 Steam 게임 데이터를 기반으로 분석을 제공합니다.
이 데이터는 누적 판매량 100만 장 이상의 상업적으로 성공한 게임들로 구성되어 있습니다.

분석 시 다음 원칙을 따르세요:
1. 데이터에 기반한 구체적인 수치와 인사이트를 제공하세요
2. 트렌드의 원인을 게임 시장 맥락에서 설명하세요
3. 실용적인 비즈니스 인사이트를 포함하세요
4. 한국어로 명확하고 구조적으로 답변하세요
5. 마크다운 형식(헤더, 불릿, 강조)을 활용하세요"""


def build_genre_trend_prompt(
    selected: list[str],
    yearly_data: dict,
    top_games: list[dict],
    genre_stats: dict,
    user_question: str = "",
) -> str:
    """장르/태그 KPI 트렌드 분석 프롬프트."""
    selected_str = ", ".join(selected) if selected else "전체"

    # 연도별 트렌드 포맷
    trend_lines = []
    for yr, data in sorted(yearly_data.items()):
        if yr < 2015:
            continue
        trend_lines.append(
            f"  {yr}년: 수익 ${data['revenue']:,.0f} | "
            f"판매 {data['sales']:,}장 | "
            f"게임 수 {data['game_count']}개"
        )

    # 상위 게임 목록
    game_lines = []
    for i, g in enumerate(top_games[:20], 1):
        from datetime import datetime
        ts = g.get("releaseDate") or g.get("firstReleaseDate")
        yr = datetime.fromtimestamp(int(ts) / 1000).year if ts else "?"
        game_lines.append(
            f"  {i}. {g.get('name', '?')} ({yr}) | "
            f"수익 ${(g.get('revenue') or 0):,.0f} | "
            f"판매 {(g.get('copiesSold') or 0):,}장 | "
            f"리뷰 {g.get('reviewScore', 0)}/100"
        )

    # 장르/태그 통계
    stat_lines = []
    for name, stat in list(genre_stats.items())[:10]:
        stat_lines.append(
            f"  - {name}: {stat['game_count']}개 게임, "
            f"평균 수익 ${stat['avg_revenue']:,.0f}, "
            f"평균 점수 {stat['avg_score']:.1f}"
        )

    question_section = f"\n## 사용자 질문\n{user_question}" if user_question else ""

    return f"""# {selected_str} 장르/태그 KPI 트렌드 분석 요청

## 분석 대상
선택된 장르/태그: {selected_str}
총 게임 수: {len(top_games)}개

## 연도별 트렌드 (2015~)
{chr(10).join(trend_lines) if trend_lines else "데이터 없음"}

## 상위 성공작 목록
{chr(10).join(game_lines) if game_lines else "데이터 없음"}

## 세부 통계
{chr(10).join(stat_lines) if stat_lines else "데이터 없음"}
{question_section}

## 분석 요청
위 데이터를 바탕으로 다음을 분석해주세요:
1. **트렌드 핵심 요약**: 이 장르/태그의 시장 성장 또는 쇠퇴 패턴
2. **성공 요인 분석**: 상위 게임들의 공통점과 차별점
3. **시장 경쟁 구도**: 현재 시장 포화도와 진입 가능성
4. **투자 가치 평가**: 이 장르에 투자/개발 시 기대 수익
5. **향후 전망**: 향후 2~3년 시장 예측

한국어로 답변해주세요."""


def build_market_overview_prompt(
    period_label: str,
    games: list[dict],
    monthly_data: list[dict],
    genre_dist: dict,
    user_question: str = "",
) -> str:
    """시장 현황 분석 프롬프트."""
    from datetime import datetime

    total = len(games)
    revenues = [g.get("revenue") or 0 for g in games]
    sales = [g.get("copiesSold") or 0 for g in games]

    total_revenue = sum(revenues)
    avg_revenue = total_revenue / total if total else 0
    hit_count = sum(1 for s in sales if s >= 1_000_000)

    # 상위 10개 게임
    top_games = sorted(games, key=lambda x: x.get("revenue") or 0, reverse=True)[:15]
    top_lines = []
    for i, g in enumerate(top_games, 1):
        ts = g.get("releaseDate") or g.get("firstReleaseDate")
        yr = datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m") if ts else "?"
        top_lines.append(
            f"  {i}. {g.get('name', '?')} ({yr}) | "
            f"수익 ${(g.get('revenue') or 0):,.0f} | "
            f"판매 {(g.get('copiesSold') or 0):,}장"
        )

    # 월별 출시 (최근 12개)
    monthly_lines = []
    for item in monthly_data[-12:]:
        monthly_lines.append(f"  {item['month']}: {item['count']}개 출시")

    # 장르 분포 (상위 8개)
    genre_lines = []
    for genre, stat in list(genre_dist.items())[:8]:
        genre_lines.append(
            f"  - {genre}: {stat['game_count']}개, "
            f"총 수익 ${stat['total_revenue']:,.0f}"
        )

    question_section = f"\n## 사용자 질문\n{user_question}" if user_question else ""

    return f"""# {period_label} Steam 시장 현황 분석 요청

## 기간 요약
- 분석 대상: {total}개 게임 ({period_label})
- 총 수익 합계: ${total_revenue:,.0f}
- 평균 게임당 수익: ${avg_revenue:,.0f}
- 히트작 (100만장+): {hit_count}개

## 월별 신규 출시 추세 (최근 12개월)
{chr(10).join(monthly_lines) if monthly_lines else "데이터 없음"}

## 장르별 수익 분포
{chr(10).join(genre_lines) if genre_lines else "데이터 없음"}

## 주요 성공작
{chr(10).join(top_lines) if top_lines else "데이터 없음"}
{question_section}

## 분석 요청
위 데이터를 바탕으로 다음을 분석해주세요:
1. **시장 현황 요약**: 해당 기간 Steam 시장의 핵심 특징
2. **주목할 트렌드**: 성장 중인 장르와 쇠퇴 중인 장르
3. **성공 패턴**: 히트작들의 공통 특성
4. **시장 집중도**: 소수 대작 vs 다수 중소작 구조 분석
5. **인사이트**: 개발사/퍼블리셔를 위한 전략적 시사점

한국어로 답변해주세요."""


def build_dev_guide_prompt(
    target: list[str],
    scale: str,
    extra_conditions: str,
    games: list[dict],
    price_data: list[dict],
    common_tags: list[tuple],
    user_question: str = "",
) -> str:
    """신규 게임 개발 전략 가이드 프롬프트."""
    from datetime import datetime

    target_str = ", ".join(target) if target else "전체"
    total = len(games)

    revenues = [g.get("revenue") or 0 for g in games]
    sales = [g.get("copiesSold") or 0 for g in games]
    scores = [g.get("reviewScore") or 0 for g in games if g.get("reviewScore")]
    playtimes = [g.get("avgPlaytime") or 0 for g in games if g.get("avgPlaytime")]

    avg_revenue = sum(revenues) / total if total else 0
    avg_sales = sum(sales) / total if total else 0
    avg_score = sum(scores) / len(scores) if scores else 0
    avg_playtime = sum(playtimes) / len(playtimes) if playtimes else 0

    # 상위 성공작
    top_games = sorted(games, key=lambda x: x.get("revenue") or 0, reverse=True)[:20]
    top_lines = []
    for i, g in enumerate(top_games, 1):
        ts = g.get("releaseDate") or g.get("firstReleaseDate")
        yr = datetime.fromtimestamp(int(ts) / 1000).year if ts else "?"
        price = g.get("price") or 0
        top_lines.append(
            f"  {i}. {g.get('name', '?')} ({yr}) | "
            f"가격 ${price} | "
            f"수익 ${(g.get('revenue') or 0):,.0f} | "
            f"판매 {(g.get('copiesSold') or 0):,}장 | "
            f"리뷰 {g.get('reviewScore', 0)}/100 | "
            f"플레이타임 {(g.get('avgPlaytime') or 0):.0f}시간"
        )

    # 공통 태그
    tag_lines = [f"  {tag}: {cnt}개 게임" for tag, cnt in common_tags[:15]]

    # 가격대별 분포
    from collections import defaultdict, Counter
    bucket_counter: Counter = Counter()
    bucket_revenue: dict = defaultdict(list)
    for item in price_data:
        bucket_counter[item["price_bucket"]] += 1
        bucket_revenue[item["price_bucket"]].append(item["revenue"])

    price_lines = []
    bucket_order = ["무료", "$0~5", "$5~10", "$10~20", "$20~30", "$30~60", "$60+"]
    for bucket in bucket_order:
        cnt = bucket_counter.get(bucket, 0)
        if cnt == 0:
            continue
        rev_list = bucket_revenue.get(bucket, [])
        avg_rev = sum(rev_list) / len(rev_list) if rev_list else 0
        price_lines.append(f"  {bucket}: {cnt}개, 평균 수익 ${avg_rev:,.0f}")

    question_section = f"\n## 추가 조건\n{extra_conditions}" if extra_conditions else ""
    user_q_section = f"\n## 질문\n{user_question}" if user_question else ""

    return f"""# {target_str} 게임 개발 전략 가이드 요청

## 개발 조건
- 목표 장르/태그: {target_str}
- 개발 규모: {scale}
- 분석 대상 성공작: {total}개
{question_section}

## 시장 통계
- 평균 수익: ${avg_revenue:,.0f}
- 평균 판매량: {avg_sales:,.0f}장
- 평균 리뷰 점수: {avg_score:.1f}/100
- 평균 플레이타임: {avg_playtime:.0f}시간

## 가격대별 분포
{chr(10).join(price_lines) if price_lines else "데이터 없음"}

## 성공작 공통 태그 Top 15
{chr(10).join(tag_lines) if tag_lines else "데이터 없음"}

## 벤치마크 성공작 목록
{chr(10).join(top_lines) if top_lines else "데이터 없음"}
{user_q_section}

## 분석 요청
위 데이터를 바탕으로 {scale} 규모 {target_str} 게임 개발을 위한 전략 가이드를 제공해주세요:

1. **시장 진입 전략**: 현재 시장 포화도와 차별화 방향
2. **최적 가격 전략**: 개발 규모별 권장 가격대와 수익 예측
3. **필수 게임 요소**: 성공작의 공통 태그/기능 기반 핵심 구현 요소
4. **경쟁사 분석**: 주요 경쟁작과 차별화 포인트
5. **리스크 평가**: 예상 리스크와 완화 방안
6. **성공 가능성**: 수익 시나리오 (보수적/중간/낙관적)
7. **실행 로드맵**: 개발 단계별 주요 마일스톤

한국어로 상세하게 답변해주세요."""


# ── 커스텀 HTML 리포트 ────────────────────────────────────────────────────────

SYSTEM_PROMPT_REPORT = """당신은 Steam 게임 시장 전문 애널리스트이자 데이터 시각화 전문가입니다.

사용자가 제공하는 실제 Steam 게임 데이터를 분석하여 완전한 HTML 보고서를 생성합니다.

중요한 규칙:
1. 반드시 완전한 HTML 문서를 반환하세요 (<!DOCTYPE html> 부터 </html> 까지)
2. 다른 설명이나 마크다운 없이 오직 HTML만 출력하세요
3. CSS는 <style> 태그에 인라인으로 포함하세요
4. Chart.js (CDN)를 활용한 인터랙티브 차트를 포함하세요
5. 모든 분석과 텍스트는 한국어로 작성하세요
6. 전문적인 비즈니스 리포트 수준의 디자인을 적용하세요
7. 데이터에 기반한 구체적인 수치를 반드시 포함하세요"""


def build_custom_report_prompt(
    user_prompt: str,
    filtered_games: list[dict],
    selected_fields: list[str],
    filter_summary: str,
    yearly_trends: dict | None = None,
) -> str:
    """커스텀 HTML 리포트 생성 프롬프트."""
    import json as _json
    from datetime import datetime
    from collections import Counter, defaultdict

    total = len(filtered_games)
    if total == 0:
        return "데이터가 없습니다."

    FIELD_MAP = {
        "판매량": "copiesSold",
        "수익": "revenue",
        "리뷰점수": "reviewScore",
        "리뷰수": "reviews",
        "평균플레이타임": "avgPlaytime",
        "가격": "price",
        "팔로워": "followers",
        "위시리스트": "wishlists",
        "현재플레이어CCU": "players",
        "오너수": "owners",
    }

    # 선택 필드 결정 (없으면 전체)
    active_fields = {k: v for k, v in FIELD_MAP.items()
                     if not selected_fields or k in selected_fields}

    import math

    def _clean(v):
        """None / NaN / Inf → 0으로 정규화."""
        if v is None:
            return 0
        try:
            f = float(v)
            return 0 if not math.isfinite(f) else f
        except (TypeError, ValueError):
            return 0

    def safe_avg(vals):
        vals = [x for x in vals if x and math.isfinite(float(x))]
        return sum(vals) / len(vals) if vals else 0

    # 집계 통계
    agg = {}
    for label, field in active_fields.items():
        vals = [_clean(g.get(field)) for g in filtered_games]
        agg[label] = {
            "total": round(sum(vals)),
            "average": round(safe_avg(vals)),
            "max": round(max(vals)) if vals else 0,
            "max_game": next(
                (g.get("name", "?") for g in filtered_games
                 if (g.get(field) or 0) == max(vals)), "?"
            ) if vals else "?",
        }

    # 장르 분포
    genre_count: Counter = Counter()
    genre_rev: dict = defaultdict(float)
    for g in filtered_games:
        for genre in (g.get("genres") or []):
            genre_count[genre] += 1
            genre_rev[genre] += g.get("revenue") or 0

    # 태그 분포
    tag_count: Counter = Counter()
    for g in filtered_games:
        for tag in (g.get("tags") or []):
            tag_count[tag] += 1

    # 국가별 집계
    country_agg: dict = defaultdict(float)
    for g in filtered_games:
        cd = _parse_field(g.get("countryData"), default={})
        if isinstance(cd, dict):
            for country, pct in cd.items():
                country_agg[country] += pct
    top_countries = dict(sorted(country_agg.items(), key=lambda x: x[1], reverse=True)[:10])

    # 플레이타임 분포 평균
    pt_buckets: dict = defaultdict(float)
    for g in filtered_games:
        pd_data = _parse_field(g.get("playtimeData"), default={})
        dist = pd_data.get("distribution") or {}
        for bucket, pct in dist.items():
            pt_buckets[bucket] += pct
    avg_pt_dist = {k: round(v / total, 1) for k, v in pt_buckets.items()}

    # 상위 30개 게임
    top_games = sorted(filtered_games, key=lambda x: x.get("revenue") or 0, reverse=True)[:30]
    game_rows = []
    for i, g in enumerate(top_games, 1):
        ts = g.get("releaseDate") or g.get("firstReleaseDate")
        yr = datetime.fromtimestamp(int(ts) / 1000).year if ts else "?"
        row = {"rank": i, "name": g.get("name", "?"), "year": yr,
               "genres": (g.get("genres") or [])[:3],
               "tags": (g.get("tags") or [])[:5]}
        for label, field in active_fields.items():
            row[label] = g.get(field) or 0
        game_rows.append(row)

    # 연도별 트렌드
    trend_data = {}
    if yearly_trends:
        for yr, data in sorted(yearly_trends.items()):
            if yr >= 2015:
                trend_data[str(yr)] = {
                    "revenue": round(data.get("revenue", 0)),
                    "sales": round(data.get("sales", 0)),
                    "game_count": data.get("game_count", 0),
                }

    data_package = {
        "filter_summary": filter_summary,
        "total_games": total,
        "aggregate_stats": agg,
        "genre_distribution": {
            g: {"count": genre_count[g], "total_revenue": round(genre_rev[g])}
            for g in list(genre_count.keys())[:12]
        },
        "top_tags": dict(tag_count.most_common(20)),
        "top_countries": top_countries,
        "playtime_distribution_avg_pct": avg_pt_dist,
        "yearly_trends": trend_data,
        "top_30_games": game_rows,
    }

    return f"""다음 Steam 게임 데이터를 분석하여 전문적인 HTML 보고서를 생성해주세요.

## 분석 요청
{user_prompt}

## 필터 조건
{filter_summary}

## 데이터
```json
{_json.dumps(data_package, ensure_ascii=False, indent=2)}
```

## HTML 보고서 요구사항
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
- 상위 30개 게임 상세 테이블 (선택된 데이터 항목 열)
- 주요 발견사항 및 전략적 시사점 섹션
- 모든 텍스트는 한국어
- 리포트 제목은 분석 내용을 반영해 자동 생성

오직 HTML 코드만 반환하세요. 앞뒤 설명 없이 <!DOCTYPE html>로 시작하세요."""
