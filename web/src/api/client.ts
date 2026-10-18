import { create } from 'zustand';

const tokenKey = 'mingjing-auth-token';
const epochKey = 'mingjing-auth-epoch';
function read(key: string): string {
  try {
    return sessionStorage.getItem(key) ?? '';
  } catch {
    return '';
  }
}
function persist(key: string, value: string) {
  try {
    if (value) sessionStorage.setItem(key, value);
    else sessionStorage.removeItem(key);
  } catch {
    /* Session storage is optional. */
  }
}
let epoch = read(epochKey) || crypto.randomUUID();
persist(epochKey, epoch);
export const useAuth = create<{ token: string; loginRequired: boolean; setToken: (token: string) => void }>((set) => ({
  token: read(tokenKey),
  loginRequired: !read(tokenKey),
  setToken: (token) => {
    const previous = useAuth.getState().token;
    if (previous && previous !== token) {
      epoch = crypto.randomUUID();
      persist(epochKey, epoch);
    }
    persist(tokenKey, token);
    set({ token, loginRequired: !token });
  },
}));
export function operationNamespace() {
  return epoch;
}
export function authHeaders(): Record<string, string> {
  const token = useAuth.getState().token;
  return token ? { 'X-Token': token } : {};
}
export function requireLogin() {
  useAuth.setState({ loginRequired: true });
}
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const namespace = operationNamespace();
  const headers = new Headers(options.headers);
  for (const [key, value] of Object.entries(authHeaders())) headers.set(key, value);
  let response: Response;
  try {
    // Foreground data should not wait behind the CJK font slices requested during layout.
    response = await fetch(path, { priority: 'high', ...options, headers, credentials: 'same-origin' });
  } catch {
    if (options.signal?.aborted) throw options.signal.reason;
    throw new ApiError(0, '网络没有连上。你的修改还在，请用原内容再试一次。');
  }
  if (namespace !== operationNamespace()) throw new ApiError(0, '登录已经切换，本次结果不会显示。');
  if (!response.ok) {
    if (response.status === 401) requireLogin();
    const messages: Record<number, string> = {
      401: '请重新登录，你的草稿还在。',
      403: '这次操作没有权限，请核对登录。',
      404: '没有找到这条内容，请刷新核对。',
      409: '内容已在别处更新，刷新后核对。你的修改还在。',
      422: '内容没有通过核对，请检查填写的信息。',
    };
    throw new ApiError(response.status, messages[response.status] ?? '这次没有收到确认。你的修改还在，请稍后重试。');
  }
  try {
    const value = (await response.json()) as T;
    if (namespace !== operationNamespace()) throw new ApiError(0, '登录已经切换，本次结果不会显示。');
    return value;
  } catch {
    if (namespace !== operationNamespace()) throw new ApiError(0, '登录已经切换，本次结果不会显示。');
    throw new ApiError(502, '没有收到完整回执。请保留原内容再试一次。');
  }
}
export function json<T>(method: string, path: string, payload: unknown): Promise<T> {
  return api<T>(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
}
