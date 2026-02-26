"""
Claude API 스트리밍 호출 래퍼.
"""
import os
from typing import Generator

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def _get_api_key() -> str:
    """Streamlit Secrets → .env 순으로 API 키 탐색."""
    # Streamlit Cloud 환경
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    # 로컬 .env 환경
    return os.getenv("ANTHROPIC_API_KEY", "")


def _get_client():
    """anthropic 클라이언트 생성 (API 키 검증 포함)."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic 패키지가 설치되지 않았습니다. pip install anthropic")

    api_key = _get_api_key()
    if not api_key or api_key == "여기에_키_입력":
        raise ValueError(
            "ANTHROPIC_API_KEY가 설정되지 않았습니다.\n"
            ".env 파일 또는 Streamlit Secrets에 ANTHROPIC_API_KEY를 입력하세요."
        )
    return anthropic.Anthropic(api_key=api_key)


def stream_analysis(prompt: str, system: str, max_tokens: int = 4096) -> Generator[str, None, None]:
    """Claude 스트리밍 분석 제너레이터."""
    client = _get_client()
    import anthropic

    try:
        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text
    except anthropic.AuthenticationError:
        yield "❌ API 키 인증 실패: ANTHROPIC_API_KEY를 확인하세요."
    except anthropic.RateLimitError:
        yield "⚠️ API 요청 한도 초과: 잠시 후 다시 시도하세요."
    except anthropic.APIError as e:
        yield f"❌ API 오류: {e}"


def stream_report(prompt: str, system: str) -> Generator[str, None, None]:
    """HTML 리포트 전용 스트리밍 (max_tokens=8192)."""
    yield from stream_analysis(prompt, system, max_tokens=8192)


def check_api_key() -> tuple[bool, str]:
    """API 키 유효성 확인. (bool, message) 반환."""
    api_key = _get_api_key()
    if not api_key or api_key == "여기에_키_입력":
        return False, "ANTHROPIC_API_KEY 미설정"
    return True, "API 키 설정됨"
