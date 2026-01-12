"""
core/retriever_factory.py

- 환경변수 RETRIEVER_VERSION에 따라 v1/v2 retriever 선택
- v2 인덱스 경로는 환경변수 INDEX_V2_DIR로 바꿀 수 있게 지원(배포 편의)
- v1 인덱스 경로는 INDEX_PATH(기존)로 바꿀 수 있게 유지

주의:
- v1은 LangChain 기반일 수 있으니, import는 필요한 분기에서만 수행
  (v2만 쓰는 환경에서 v1 의존성 때문에 부팅 실패하는 것 방지)
"""

import os


def get_retriever():
    version = os.getenv("RETRIEVER_VERSION", "v1").lower().strip()
    device = os.getenv("EMBED_DEVICE", "cpu")

    if version == "v2":
        # ✅ v2 인덱스 폴더 경로는 환경변수로 오버라이드 가능
        # 기본은 backend/models/faiss_index_v2
        index_dir = os.getenv("INDEX_V2_DIR", "models/faiss_index_v2")

        print(f"🚀 Using BookRetrieverV2 | index_dir={index_dir} | device={device}")
        from core.retriever_v2 import BookRetrieverV2

        return BookRetrieverV2(
            index_dir=index_dir,
            device=device,
            model_name=os.getenv("EMBED_MODEL_NAME", "intfloat/multilingual-e5-base"),
        )

    # default: v1
    index_path = os.getenv("INDEX_PATH", "models/faiss_index")

    print(f"⚠️ Using BookRetriever(v1) | index_path={index_path}")
    from core.retriever import BookRetriever

    return BookRetriever(index_path)
