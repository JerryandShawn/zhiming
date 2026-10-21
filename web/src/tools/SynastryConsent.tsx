import { Checkbox } from '../components/ui/Controls';
import { sampleNames } from './port';
import type { SynastryDraft } from './SynastryForm';

export function SynastryConsent({
  draft,
  checked,
  onChange,
}: {
  draft: SynastryDraft;
  checked: { a: boolean; b: boolean };
  onChange: (side: 'a' | 'b', checked: boolean) => void;
}) {
  return (
    <fieldset className="stack tool-consent">
      <legend>分别确认本次展示</legend>
      <p className="meta">
        样例中的历史确认不能替代本次选择。任一条件改变后需重新确认；只在本页内有效，不涵盖保存、分享或发送。
      </p>
      {(['a', 'b'] as const).map((side) => (
        <label className="row" key={side}>
          <Checkbox
            label={`允许本次展示${side.toUpperCase()}方合成盘面`}
            checked={checked[side]}
            onChange={(event) => onChange(side, event.target.checked)}
          />
          允许本次展示 {side.toUpperCase()} 方 {sampleNames[draft[side]]} 的合成盘面
        </label>
      ))}
    </fieldset>
  );
}
