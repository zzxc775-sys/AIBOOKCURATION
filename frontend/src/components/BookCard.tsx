// src/components/BookCard.tsx
import type { BookItem } from '../api/recommend'

const SCORE_MODE = import.meta.env.VITE_SCORE_MODE ?? 'stars';

function ScoreView({book}:{book: BookItem}) {
  if (SCORE_MODE === 'none') return null;

  if (SCORE_MODE === 'score_pct' && typeof book.score_pct === 'number') {
    return <p className="mt-1 text-xs text-gray-500">유사도 {book.score_pct}%</p>;
  }
  if (SCORE_MODE === 'rel_pct' && typeof book.rel_pct === 'number') {
    return <p className="mt-1 text-xs text-gray-500">이 검색에서 {book.rel_pct}%</p>;
  }
  if (SCORE_MODE === 'stars' && typeof book.stars === 'number') {
    return <p className="mt-1 text-xs text-gray-500">★ {book.stars.toFixed(1)} / 5.0 (유사도)</p>;
  }
  // fallback: nothing
  return null;
}

export default function BookCard({ book }: { book: BookItem }) {
  return (
    <div className="bg-white rounded-2xl shadow p-4 border border-gray-100">
      <h3 className="text-lg font-semibold">{book.title}</h3>
      {book.author && <p className="text-sm text-gray-600 mt-0.5">👤 {book.author}</p>}
      {book.content && <p className="mt-2 text-gray-800 line-clamp-3">{book.content}</p>}
      <ScoreView book={book} />
    </div>
  )
}
