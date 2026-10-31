import type { JsonObject } from './types';
export const record = (value: unknown): value is JsonObject =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
export const text = (value: unknown): value is string => typeof value === 'string';
export const bounded = (value: unknown, max: number, min = 0): value is string =>
  text(value) && Array.from(value).length >= min && Array.from(value).length <= max;
export const identifier = (value: unknown): value is string =>
  text(value) && value.length <= 200 && /^[A-Za-z0-9][A-Za-z0-9_.:-]*$/.test(value);
export const oneOf = (value: unknown, allowed: readonly string[]) => text(value) && allowed.includes(value);
export const integer = (value: unknown, min: number): value is number =>
  Number.isSafeInteger(value) && Number(value) >= min;
export function keys(data: JsonObject, required: string[], optional: string[] = []) {
  return (
    required.every((key) => Object.hasOwn(data, key)) &&
    Object.keys(data).every((key) => required.includes(key) || optional.includes(key))
  );
}
export const optional = (data: JsonObject, key: string, valid: (value: unknown) => boolean) =>
  !Object.hasOwn(data, key) || data[key] === null || valid(data[key]);
export const optionalId = (data: JsonObject, key: string) => optional(data, key, identifier);
export const ids = (value: unknown, max = Infinity): value is string[] =>
  Array.isArray(value) && value.length <= max && value.every(identifier);
