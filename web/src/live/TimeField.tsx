import { Select } from '../components/ui/Selection';

export default function TimeField({
  label,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const [hour = '00', minute = '00'] = value.split(':');
  const options = (count: number) =>
    Array.from({ length: count }, (_, index) => ({
      value: String(index).padStart(2, '0'),
      label: String(index).padStart(2, '0'),
    }));
  return (
    <fieldset disabled={disabled} className="field">
      <legend>{label}</legend>
      <div className="row wrap">
        <Select
          label={`${label}小时`}
          value={hour}
          onChange={(next) => onChange(`${next}:${minute}`)}
          options={options(24)}
        />
        <span>时</span>
        <Select
          label={`${label}分钟`}
          value={minute}
          onChange={(next) => onChange(`${hour}:${next}`)}
          options={options(60)}
        />
        <span>分</span>
      </div>
    </fieldset>
  );
}
