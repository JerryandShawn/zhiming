import { Select } from '../components/ui/Selection';
import type { Card } from './public';

export type ManualCard = { card_id: string; orientation: string };
export function ManualCards({
  positions,
  cards,
  reversals,
  value,
  onChange,
}: {
  positions: string[];
  cards: Card[];
  reversals: boolean;
  value: ManualCard[];
  onChange: (cards: ManualCard[]) => void;
}) {
  function update(index: number, next: Partial<ManualCard>) {
    onChange(
      positions.map((_, i) => ({
        card_id: value[i]?.card_id ?? '',
        orientation: value[i]?.orientation ?? 'upright',
        ...(i === index ? next : {}),
      })),
    );
  }
  return (
    <div className="stack">
      {positions.map((label, index) => (
        <div className="row wrap" key={label}>
          <div className="field">
            <span>{label}的牌</span>
            <Select
              label={`${label}的牌`}
              value={value[index]?.card_id ?? ''}
              options={[
                { value: '', label: '选择实际抽到的牌' },
                ...cards.map((c) => ({ value: c.card_id, label: c.name })),
              ]}
              onChange={(card_id) => update(index, { card_id })}
            />
          </div>
          <div className="field">
            <span>{label}的方向</span>
            <Select
              label={`${label}的方向`}
              value={reversals ? (value[index]?.orientation ?? 'upright') : 'upright'}
              options={[
                { value: 'upright', label: '正位' },
                ...(reversals ? [{ value: 'reversed', label: '逆位' }] : []),
              ]}
              onChange={(orientation) => update(index, { orientation })}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
export function manualValid(value: ManualCard[], count: number): boolean {
  return (
    value.length === count &&
    value.every((c) => Boolean(c.card_id)) &&
    new Set(value.map((c) => c.card_id)).size === count
  );
}
