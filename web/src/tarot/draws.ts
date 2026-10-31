import { api } from '../api/client';
import { write } from '../api/operations';
import { draw, object, type Draw } from './public';

export const path = (id: string) => `/api/tarot/draws/${encodeURIComponent(id)}`;
export async function createDraw(payload: Record<string, unknown>): Promise<{ draw: Draw; reused: boolean }> {
  const response = object(
    await write<unknown>('tarot:create', 'POST', '/api/tarot/draws', payload, {
      idKey: 'idempotency_key',
      receipt: (value) => Boolean(draw(object(value).draw).id),
    }),
  );
  return { draw: draw(response.draw), reused: response.reused === true };
}
export async function mutateDraw(
  current: Draw,
  action: 'select' | 'reveal' | 'cancel' | 'manual',
  payload: Record<string, unknown>,
): Promise<Draw> {
  return draw(
    await write<unknown>(
      `tarot:${current.id}:${action}`,
      action === 'manual' ? 'PATCH' : 'POST',
      `${path(current.id)}/${action}`,
      payload,
      {
        idKey: action === 'select' || action === 'manual' ? 'idempotency_key' : 'request_id',
        receipt: (value) => Boolean(draw(value).id),
      },
    ),
  );
}
export async function loadDraw(id: string): Promise<Draw> {
  return draw(await api<unknown>(path(id)));
}
