import { Tag } from '../../components/ui/Controls';
import type { Decision } from '../types';

export function DecisionCards({ options }: { options: Decision[] }) {
  if (!options.length) return null;
  return (
    <section
      className={`decision-options live-decision-options count-${Math.min(options.length, 3)}`}
      role="region"
      tabIndex={0}
      aria-label="可比较的选择">
      <h2 className="sr-only">可比较的选择</h2>
      {options.map((option, index) => (
        <section className="decision-card" key={`${index}-${option.option}`}>
          <h3>{option.option}</h3>
          <dl>
            {(['benefit', 'cost', 'risk', 'reversibility', 'first_step'] as const).map((key, item) => (
              <div key={key}>
                <dt>{['收益', '代价', '风险', '可逆性', '第一步'][item]}</dt>
                <dd>{option[key] || '仍需核对'}</dd>
              </div>
            ))}
          </dl>
          <Tag tone="work">待确认</Tag>
        </section>
      ))}
    </section>
  );
}
