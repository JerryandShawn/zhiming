/** Deliberate viewer projection: response snapshots and private deck order never enter component state. */
export type Card = {
  card_id: string;
  name: string;
  upright: string;
  reversed: string;
  misreading: string;
  question: string;
};
export type Spread = { id: string; name: string; positions: string[] };
export type Deck = { cards: Card[]; spreads: Spread[]; reversals: boolean };
export type Position = {
  position: number;
  label: string;
  back_id: string;
  revealed: boolean;
  card?: Card;
  orientation?: string;
};
export type Draw = {
  id: string;
  question: string;
  case_id: string;
  spread_id: string;
  spread: Spread;
  draw_source: string;
  reversals: boolean;
  status: string;
  cards: Position[];
  backs: { back_id: string; selected: boolean }[];
  options: { A: string; B: string };
  created_at: string;
  revision: number;
  previous_draw_id: string;
};
export type Reading = { id: string; version: number; status: string; answer: string; appendix: string };
export function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
export function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}
export function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}
function number(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}
export function card(value: unknown): Card {
  const raw = object(value);
  return {
    card_id: text(raw.card_id),
    name: text(raw.name),
    upright: text(raw.upright),
    reversed: text(raw.reversed),
    misreading: text(raw.misreading),
    question: text(raw.question),
  };
}
export function spread(value: unknown): Spread {
  const raw = object(value);
  return {
    id: text(raw.id),
    name: text(raw.name),
    positions: list(raw.positions).filter((v): v is string => typeof v === 'string'),
  };
}
export function deck(value: unknown): Deck {
  const raw = object(value);
  return {
    cards: list(raw.cards).map(card),
    spreads: list(raw.spreads).map(spread),
    reversals: object(raw.preferences).reversals !== false,
  };
}
export function draw(value: unknown): Draw {
  const raw = object(value),
    options = object(raw.options);
  return {
    id: text(raw.id),
    question: text(raw.question),
    case_id: text(raw.case_id),
    spread_id: text(raw.spread_id),
    spread: spread(raw.spread),
    draw_source: text(raw.draw_source),
    reversals: raw.reversals === true,
    status: text(raw.status),
    cards: list(raw.cards).map((value) => {
      const position = object(value),
        revealed = position.revealed === true;
      return {
        position: number(position.position),
        label: text(position.label),
        back_id: text(position.back_id),
        revealed,
        ...(revealed ? { card: card(position.card), orientation: text(position.orientation) } : {}),
      };
    }),
    backs: list(raw.backs).map((value) => ({
      back_id: text(object(value).back_id),
      selected: object(value).selected === true,
    })),
    options: { A: text(options.A), B: text(options.B) },
    created_at: text(raw.created_at),
    revision: number(raw.revision),
    previous_draw_id: text(raw.previous_draw_id),
  };
}
export function reading(value: unknown): Reading {
  const raw = object(value),
    result = object(raw.result);
  return {
    id: text(raw.id),
    version: number(raw.version),
    status: text(raw.status),
    answer: text(result.answer),
    appendix: text(result.professional_appendix),
  };
}
export function image(id?: string): string {
  return id && /^[a-zA-Z0-9_-]+$/.test(id) ? `/static/tarot/${id}.svg` : '/static/tarot/back.svg';
}
