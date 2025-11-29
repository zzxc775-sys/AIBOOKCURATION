# core/llm_integration.py

import os
import requests
import json
from typing import List, Dict
from datetime import datetime
import logging

from requests.exceptions import RequestException
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DeepSeekRecommender:
    """
    RAG 검색 결과(책 3~5권)를 기반으로
    LLM이 '추천 도서 정리 → 추천 이유 종합 → 사용자 확인 질문'을 생성하도록 설계한 클래스
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DeepSeek API 키가 제공되지 않았습니다. 환경변수 DEEPSEEK_API_KEY를 설정하세요.")
        
        self.base_url = "https://api.deepseek.com/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    # ---------------------------------------------------------------------
    # 1) LLM 호출
    # ---------------------------------------------------------------------
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(RequestException)
    )
    def generate_recommendation(self, user_query: str, books: List[Dict], model: str = "deepseek-chat") -> Dict:
        """
        LLM에 user_query + 책 후보 리스트를 보내 요약된 추천 결과를 생성.
        books: [{title, author, description/content, score, ...}, ...]
        """
        try:
            # 1. 프롬프트 생성
            prompt = self._build_prompt(user_query, books)

            # 2. API 페이로드 구성
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": self._get_system_message()},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 1200,
                "top_p": 0.9,
                "frequency_penalty": 0.4
            }

            # 3. DeepSeek 요청
            logger.info("Sending DeepSeek payload: %s", json.dumps(payload, ensure_ascii=False, indent=2))
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            # 4. 응답 처리
            result = response.json()
            content = result["choices"][0]["message"]["content"]

            return {
                "content": content,
                "usage": result.get("usage", {}),
                "timestamp": datetime.now().isoformat()
            }

        except requests.exceptions.Timeout:
            logger.error("DeepSeek API 요청 시간 초과")
            raise

        except requests.exceptions.RequestException as e:
            logger.error(f"DeepSeek API 호출 실패: {str(e)}")
            raise

    # ---------------------------------------------------------------------
    # 2) SYSTEM 메시지 (역할 정의)
    # ---------------------------------------------------------------------
    def _get_system_message(self) -> str:
        """
        LLM이 따라야 하는 역할 정의.
        """
        return """
당신은 한국어로 답변하는 '전문 도서 큐레이션 AI'입니다.

[목표]
- 사용자의 상황·감정·목표에 맞는 최적의 책을 추천하고,
  그 이유를 명확하고 친절하게 설명합니다.

[스타일]
- 친절한 상담형 톤.
- 한국어 존댓말 사용.
- 너무 긴 문장은 피하고 핵심만 요약.
- 리스트/굵은 글씨 등을 적절히 사용해 가독성 높이기.

[출력 형식 — 반드시 아래 순서로 작성]
## 1. 추천 도서
- 총 3~5권
- 각 책마다:
  - 제목
  - 저자
  - 1~2줄 요약 (책의 핵심)
  - 이 책이 사용자의 요청에 적합한 이유

## 2. 추천 이유 종합
- 사용자의 질문 의도를 먼저 1문장으로 정리.
- 왜 이런 책들을 묶어서 추천했는지 3~5개의 핵심 근거로 설명.

## 3. 다음 선택을 위한 안내
- 추천이 맞았는지 사용자에게 확인하는 질문 1개.
- 사용자가 더 말해주면 좋은 추가 정보 2~4개 제안.
"""

    # ---------------------------------------------------------------------
    # 3) USER 프롬프트 생성 (RAG 후보 + 사용자 질문 조합)
    # ---------------------------------------------------------------------
    def _build_prompt(self, user_query: str, books: List[Dict]) -> str:
        """
        RAG 검색으로 얻은 책 후보들을 LLM에 넘기기 위한 프롬프트 생성.
        """

        def _render_book(idx: int, b: Dict) -> str:
            title = b.get("title") or "제목 없음"
            author = b.get("author") or "저자 정보 없음"
            desc = b.get("content") or b.get("description") or ""
            desc = (desc[:160] + "...") if len(desc) > 160 else desc

            score = b.get("score")
            score_text = f"{score:.3f}" if isinstance(score, (float, int)) else "N/A"

            return (
                f"{idx}. 제목: {title}\n"
                f"   - 저자: {author}\n"
                f"   - 내용 요약: {desc if desc else '요약 정보 없음'}\n"
                f"   - 유사도 점수(참고): {score_text}\n"
            )

        books_block = "\n".join(
            _render_book(i + 1, b) for i, b in enumerate(books)
        )

        # USER 메시지 (LLM에게 실제 작업 지시)
        return f"""
[사용자 요청]
{user_query}

[후보 도서 목록]
아래는 검색 시스템이 사용자의 요청과 가장 유사한 책 순서로 전달한 후보 리스트입니다.
각 책의 유사도 점수는 참고용입니다.

{books_block}

[당신의 작업]
위 정보를 바탕으로 아래 3가지 섹션을 정확한 순서로 작성하세요:

1) 추천 도서 3~5권 (각각 제목/저자/한줄요약/추천 이유 포함)
2) 추천 이유 종합
3) 사용자에게 확인 질문 + 추가로 알려주면 좋은 정보 제안

중복된 설명을 하지 말고, 사용자의 상황에 맞춘 이유 중심으로 정리해주세요.
"""

