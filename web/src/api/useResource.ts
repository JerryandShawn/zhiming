import { useQuery } from '@tanstack/react-query';
import { api, operationNamespace, useAuth } from './client';
export function useResource<T>(path: string | null) {
  const token = useAuth((state) => state.token);
  const loginRequired = useAuth((state) => state.loginRequired);
  return useQuery<T>({
    queryKey: ['api', operationNamespace(), path],
    queryFn: ({ signal }) => api<T>(path!, { signal }),
    enabled: Boolean(path && token && !loginRequired),
    retry: false,
  });
}
