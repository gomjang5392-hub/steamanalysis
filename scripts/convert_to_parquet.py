"""
JSON 게임 데이터 → Parquet 변환 스크립트.

641MB JSON 파일들을 단일 Parquet 파일(~30~50MB)로 압축합니다.
Streamlit Community Cloud 배포 전 1회 실행하세요.

실행:
    python scripts/convert_to_parquet.py
"""
import json
import glob
import os
import sys

import pandas as pd

GAMES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "raw_data", "games")
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "raw_data", "games_data.parquet")


def main():
    print(f"JSON 파일 로드 중: {GAMES_DIR}")
    paths = [p for p in glob.glob(os.path.join(GAMES_DIR, "*.json"))
             if "_progress" not in os.path.basename(p)]
    print(f"발견된 파일: {len(paths)}개")

    # 서비스에서 사용하지 않는 필드 (용량만 차지)
    DROP_FIELDS = {"alsoPlayed", "similarGames"}

    rows = []
    errors = 0
    for i, path in enumerate(paths, 1):
        if i % 200 == 0:
            print(f"  {i}/{len(paths)} 처리 중...")
        try:
            with open(path, encoding="utf-8") as f:
                game = json.load(f)

            # 불필요 필드 제거
            for f_ in DROP_FIELDS:
                game.pop(f_, None)

            # audienceOverlap: link 높은 순으로 상위 30개만 유지
            ao = game.get("audienceOverlap")
            if isinstance(ao, list) and len(ao) > 30:
                game["audienceOverlap"] = sorted(
                    ao, key=lambda x: x.get("link", 0), reverse=True
                )[:30]

            row = {}
            for key, value in game.items():
                # dict / list → JSON 문자열로 직렬화
                if isinstance(value, (dict, list)):
                    row[key] = json.dumps(value, ensure_ascii=False)
                else:
                    row[key] = value
            rows.append(row)
        except Exception as e:
            errors += 1
            print(f"  오류 ({os.path.basename(path)}): {e}")

    if not rows:
        print("변환할 데이터가 없습니다.")
        sys.exit(1)

    df = pd.DataFrame(rows)
    df.to_parquet(OUTPUT_PATH, index=False, compression="gzip")

    size_mb = os.path.getsize(OUTPUT_PATH) / 1024 / 1024
    print(f"\n완료!")
    print(f"  게임 수: {len(df):,}개 (오류: {errors}개)")
    print(f"  저장 경로: {OUTPUT_PATH}")
    print(f"  파일 크기: {size_mb:.1f} MB")
    print(f"\n다음 단계: GitHub에 raw_data/games_data.parquet 파일을 포함해서 업로드하세요.")


if __name__ == "__main__":
    main()
