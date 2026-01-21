# backend/core/llm_integration.py

import os
import requests
import json
from typing import List, Dict, Optional
from datetime import datetime
import logging

from requests.exceptions import RequestException, Timeout, ConnectionError
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DeepSeekRecommender:
    """
    RAG 검색 결과(책 3~5권)를 기반으로
    LLM이 '추천 도서 정리 → 추천 이유 종합 → 사용자 확인 질문'을 생성하도록 설계한 클래스

    [성능/UX 정책]
    - "타임박스"를 걸어서 LLM이 느리면 빨리 실패하고(=요약 없이) 검색 결과는 즉시 반환.
    - 운영 UX를 위해 긴 재시도/무제한 대기 금지.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DeepSeek API 키가 제공되지 않았습니다. 환경변수 DEEPSEEK_API_KEY를 설정하세요.")

        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1/chat/completions")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # --- 타임박스(초) ---
        # connect: TCP 연결에 걸리는 최대 시간
        # read: 서버가 응답 바디를 "받기 시작해서 끝날 때까지" 기다리는 최대 시간
        self.timeout_connect = float(os.getenv("DEEPSEEK_TIMEOUT_CONNECT", "5"))
        self.timeout_read = float(os.getenv("DEEPSEEK_TIMEOUT_READ", "8"))

        # --- 토큰 제한 ---
        self.max_tokens = int(os.getenv("DEEPSEEK_MAX_TOKENS", "600"))

        # --- 로깅(운영에서 payload 전문 출력은 비추) ---
        self.log_payload = os.getenv("DEEPSEEK_LOG_PAYLOAD", "0") == "1"

    # ---------------------------------------------------------------------
    # 1) LLM 호출 (타임박스 + 최소 재시도)
    # ---------------------------------------------------------------------
    @retry(
        # 2회까지만 시도: 1차 실패(일시적 네트워크)면 1번만 더.
        stop=stop_after_attempt(2),
        # 재시도 대기시간 고정 0.5초 (길게 끌지 않음)
        wait=wait_fixed(0.5),
        # Timeout/ConnectionError 같은 네트워크 계열만 재시도
        retry=retry_if_exception_type((Timeout, ConnectionError, RequestException)),
        reraise=True,
    )
    def generate_recommendation(self, user_query: str, books: List[Dict], model: str = "deepseek-chat") -> Dict:
        """
        LLM에 user_query + 책 후보 리스트를 보내 요약된 추천 결과를 생성.
        books: [{title, author, description/content, score, ...}, ...]
        """
        # 1) 짧은 프롬프트 생성
        prompt = self._build_prompt(user_query, books)

        # 2) API 페이로드 구성 (토큰/길이 제한 강화)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self._get_system_message()},
                {"role": "user", "content": prompt},
            ],
            # 안정성/속도 위해 살짝 낮춤(선택)
            "temperature": 0.6,
            "max_tokens": self.max_tokens,   # ✅ 1200 -> 600
            "top_p": 0.9,
            "frequency_penalty": 0.2,
        }

        if self.log_payload:
            logger.info("Sending DeepSeek payload: %s", json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            logger.info(
                "Sending DeepSeek request (model=%s, max_tokens=%s, timeout=(%ss,%ss))",
                model, self.max_tokens, self.timeout_connect, self.timeout_read
            )

        # 3) DeepSeek 요청 (✅ 타임박스: (connect, read))
        response = requests.post(
            self.base_url,
            headers=self.headers,
            json=payload,
            timeout=(self.timeout_connect, self.timeout_read),
        )
        response.raise_for_status()

        # 4) 응답 처리
        result = response.json()
        content = result["choices"][0]["message"]["content"]

        return {
            "content": content,
            "usage": result.get("usage", {}),
            "timestamp": datetime.now().isoformat(),
        }

    # ---------------------------------------------------------------------
    # 2) SYSTEM 메시지 (역할 정의) - "짧고 완성형" 강제
    # ---------------------------------------------------------------------
    def _get_system_message(self) -> str:
        """
        LLM이 따라야 하는 역할 정의.
        핵심: 600토큰 내에서 '완성형' 답을 하게 길이 제한을 명시.
        """
        return """
당신은 한국어로 답변하는 '전문 도서 큐레이션 AI'입니다.

[목표]
- 사용자의 요청에 맞는 책 3~5권을 추천하고, 이유를 짧고 명확하게 설명합니다.

[매우 중요: 길이 제한]
- 전체 답변은 "간결하게" 작성합니다.
- 각 책은 '요약 1문장 + 추천이유 1문장'만 작성합니다.
- "추천 이유 종합"은 불릿 3개만 작성합니다.
- 마지막 섹션은 질문 1개 + 추가정보 2개만 작성합니다.
- 아래 형식을 반드시 지키고, 불필요한 서론/중복 설명을 금지합니다.

[출력 형식 — 반드시 아래 순서]
## 1. 추천 도서
- (3~5권)
- 각 책: 제목 / 저자 / 1문장 요약 / 1문장 추천 이유

## 2. 추천 이유 종합
- 사용자 의도 1문장
- 핵심 근거 3개 (불릿)

## 3. 다음 선택을 위한 안내
- 확인 질문 1개
- 추가로 알려주면 좋은 정보 2개
""".strip()

    # ---------------------------------------------------------------------
    # 3) USER 프롬프트 생성 (RAG 후보 + 사용자 질문 조합) - 입력도 짧게
    # ---------------------------------------------------------------------
    def _build_prompt(self, user_query: str, books: List[Dict]) -> str:
        """
        RAG 검색으로 얻은 책 후보들을 LLM에 넘기기 위한 프롬프트 생성.
        - 후보 설명을 짧게 잘라 입력 토큰을 줄임
        - 점수는 참고용으로만 3자리로 표기
        """

        def _clip(text: str, max_len: int = 140) -> str:
            text = (text or "").strip()
            if not text:
                return ""
            return (text[:max_len] + "...") if len(text) > max_len else text

        def _render_book(idx: int, b: Dict) -> str:
            title = b.get("title") or "제목 없음"
            author = b.get("author") or "저자 정보 없음"

            # description/content는 길게 넣지 않기(입력 토큰 절약)
            desc = b.get("snippet") or b.get("content") or b.get("description") or ""
            desc = _clip(desc, 140)

            score = b.get("score")
            score_text = f"{score:.3f}" if isinstance(score, (float, int)) else "N/A"

            # 입력 최소화
            return (
                f"{idx}. {title} / {author}\n"
                f"   - 요약: {desc if desc else '요약 없음'}\n"
                f"   - 유사도(참고): {score_text}\n"
            )

        # 상위 5개까지만 사용(너 fastapi_app에서 이미 5개만 주지만 안전장치)
        books = (books or [])[:5]
        books_block = "\n".join(_render_book(i + 1, b) for i, b in enumerate(books))

        return f"""
[사용자 요청]
{user_query}

[후보 도서(유사도 순)]
{books_block}

[작성 지시]
- system 메시지의 "길이 제한"과 "형식"을 반드시 지키세요.
""".strip()
