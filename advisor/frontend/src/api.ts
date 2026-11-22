export class ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly payload: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function api<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, credentials: 'same-origin', signal: init?.signal ?? AbortSignal.timeout(65_000) });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const data = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {};
    const message = [data.message, data.detail].find(value => typeof value === 'string');
    throw new ApiError(response.status, typeof message === 'string' ? message :
      response.status === 401 ? 'Войдите в кошелёк.' : `Запрос не выполнен (${response.status}).`, payload);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}
