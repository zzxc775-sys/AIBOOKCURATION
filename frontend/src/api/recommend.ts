import client from './client';

export type RecommendRequest = { query: string };
export type BookItem = {
  id?: string;
  title: string;
  author?: string;
  content?: string; // description 요약
  description?: string; // 원본 설명
  score?: number;   // 유사도
  image?: string;   // 확장 시 썸네일
  thumbnail?: string; // 썸네일 이미지 URL

  rank?: number;           // 1,2,3...
  score_pct?: number;      // 0~100
  rel_pct?: number;        // 10~100 (세트 내 상대)
  stars?: number;          // 0.5~5.0
  distance?: number | null;// 원시 거리(디버깅용)
  publisher?: string | null;
  isbn?: string | null;
};
export type RecommendResponse = {
  results: BookItem[];
  content?: string; // AI 추천 요약
};

export async function fetchRecommend(body: RecommendRequest) {
  const { data } = await client.post<RecommendResponse>('/recommend', body);
  return data;
}
