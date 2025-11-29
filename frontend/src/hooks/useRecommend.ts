import { useMutation } from '@tanstack/react-query';
import { fetchRecommend } from '../api/recommend';

export function useRecommend() {
  return useMutation({ mutationFn: fetchRecommend });
}
