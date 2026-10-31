import { Input } from '../components/ui/Controls';
import { kindLabels, sampleNames } from './port';
import { inputAria, ToolFieldIssues, type InputTargets } from './ToolInputFeedback';
import { ToolSelect } from './ToolSelect';
import type { FieldIssue, SynastryField } from './inputValidationTypes';
import type { RelationKind, SynastryQuery } from './types';

export type SynastryDraft = Omit<SynastryQuery, 'orbDegrees'> & { orbDegrees: string };
/** UI conversion only. Empty and unfinished values reach the pure validator as NaN, never 0. */
export function synastryCandidate(draft: SynastryDraft) {
  const raw = draft.orbDegrees;
  const decimal = /^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/.test(raw);
  return { ...draft, orbDegrees: decimal ? Number(raw) : Number.NaN };
}
export const synastryDraftKey = (draft: SynastryDraft) =>
  JSON.stringify([draft.a, draft.b, draft.kind, draft.asOfDate, draft.orbDegrees]);

export function SynastryForm({
  draft,
  issues,
  prefix,
  targets,
  change,
}: {
  draft: SynastryDraft;
  issues: readonly FieldIssue<SynastryField>[];
  prefix: string;
  targets: InputTargets<SynastryField>;
  change: (draft: SynastryDraft) => void;
}) {
  return (
    <>
      {(['a', 'b'] as const).map((side) => (
        <div className="field" key={side}>
          {side.toUpperCase()} 方合成对象
          <ToolSelect
            id={targets[side]}
            label={`${side.toUpperCase()} 方合成对象`}
            value={draft[side]}
            options={Object.entries(sampleNames).map(([value, label]) => ({ value, label }))}
            {...inputAria(side, issues, prefix)}
            onChange={(value) => change({ ...draft, [side]: value as SynastryQuery[typeof side] })}
          />
          <ToolFieldIssues field={side} issues={issues} prefix={prefix} />
        </div>
      ))}
      <div className="field">
        本次比较用途
        <ToolSelect
          id={targets.kind}
          label="本次比较用途"
          value={draft.kind}
          options={Object.entries(kindLabels).map(([value, label]) => ({ value, label }))}
          {...inputAria('kind', issues, prefix)}
          onChange={(kind) => change({ ...draft, kind: kind as RelationKind })}
        />
        <ToolFieldIssues field="kind" issues={issues} prefix={prefix} />
      </div>
      <div className="field">
        <label htmlFor={targets.asOfDate}>核对日期（北京时间）</label>
        <Input
          id={targets.asOfDate}
          type="date"
          value={draft.asOfDate}
          required
          {...inputAria('asOfDate', issues, prefix)}
          onChange={(event) => change({ ...draft, asOfDate: event.target.value })}
        />
        <ToolFieldIssues field="asOfDate" issues={issues} prefix={prefix} />
      </div>
      <div className="field">
        <label htmlFor={targets.orbDegrees}>统一相位容许度（度）</label>
        <Input
          id={targets.orbDegrees}
          type="text"
          inputMode="decimal"
          value={draft.orbDegrees}
          required
          {...inputAria('orbDegrees', issues, prefix)}
          onChange={(event) => change({ ...draft, orbDegrees: event.target.value })}
        />
        <span className="meta">0至10度；空白不会自动补成0或6。</span>
        <ToolFieldIssues field="orbDegrees" issues={issues} prefix={prefix} />
      </div>
    </>
  );
}
