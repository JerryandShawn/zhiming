import { Tag } from '../../components/ui/Controls';
import { publicChatText } from '../publicProjection';
import type { Decision } from '../types';

const dimensions = ['benefit', 'cost', 'risk', 'reversibility', 'first_step'] as const;
const labels = ['收益', '代价', '风险', '可逆性', '第一步'];
const reversibility: Record<string, string> = {
  easy: '容易调整',
  partial: '部分可调整',
  hard: '较难撤回',
  unknown: '待确认',
};

function dimension(option: Decision, key: (typeof dimensions)[number], index: number) {
  if (option.unknowns?.some((unknown) => unknown === key || unknown === labels[index])) return '待确认';
  const value = option[key];
  return publicChatText(
    (key === 'reversibility' && Object.hasOwn(reversibility, value) ? reversibility[value] : value) || '待确认',
  );
}

export function DecisionCards({ options }: { options: Decision[] }) {
  if (!options.length) return null;
  return (
    <section
      className={`decision-options live-decision-options count-${Math.min(options.length, 3)}`}
      role="region"
      tabIndex={0}
      aria-label="可比较的选择">
      <h2 className="sr-only">可比较的选择</h2>
      {options.map((option, index) => {
        const uncertain =
          option.unknowns === undefined ||
          Boolean(option.unknowns.length) ||
          dimensions.some((key, item) => dimension(option, key, item) === '待确认');
        return (
          <section className="decision-card" key={option.id || `${index}-${option.option}`} data-option-id={option.id}>
            <h3>{publicChatText(option.option)}</h3>
            <dl>
              {dimensions.map((key, item) => (
                <div key={key}>
                  <dt>{labels[item]}</dt>
                  <dd>{dimension(option, key, item)}</dd>
                </div>
              ))}
            </dl>
            {uncertain && <Tag tone="work">待确认</Tag>}
            {Boolean(option.unknowns?.length) && (
              <ul className="meta" aria-label="待确认事项">
                {option.unknowns?.map((unknown, item) => (
                  <li key={item}>
                    {publicChatText(labels[dimensions.findIndex((key) => key === unknown)] || unknown)}
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </section>
  );
}
