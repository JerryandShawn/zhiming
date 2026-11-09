import type { GlossarySource, TermDetail as Detail } from './types';

export const studySystemLabels = { bazi: '八字', ziwei: '紫微斗数', astro: '西方占星', tarot: '塔罗' } as const;
const kinds: Record<string, string> = {
  astronomical_time_coordinate: '天文时间坐标',
  editorial_method: '项目整理方法',
  editorial_symbol: '项目象征说明',
  geometric_parameter: '几何参数',
  symbolic_timing_technique: '象征性时序方法',
  traditional_concept: '传统概念',
};
const verification: Record<string, string> = {
  implementation_locator_checked: '来源登记已核对程序定位；不等于原典或现实效度核验。',
  official_document_read: '来源登记记录了官方说明的阅读；本页未重新访问或加载外网。',
  original_editorial_read: '项目原创研习说明；不冒称古籍原文或统一流派结论。',
};

function externalUrl(value: string | null) {
  if (!value) return;
  try {
    const url = new URL(value);
    if (url.protocol === 'https:' && !url.username && !url.password) return url.href;
  } catch {
    /* Render source descriptions as text when no safe link exists. */
  }
}

function Source({ source, detail }: { source: GlossarySource; detail: Detail }) {
  const support = detail.term.sources.filter((ref) => ref.source_id === source.source_id);
  const href = externalUrl(source.url);
  return (
    <li className="stack small">
      <h4>{source.title}</h4>
      {support.length ? (
        support.map((ref) => (
          <div key={ref.locator} className="stack small">
            <p className="small-text">支持范围：{ref.support_scope}</p>
            <p className="meta study-source-locator">词条定位：{ref.locator}</p>
          </div>
        ))
      ) : (
        <p className="small-text">用于此词条的流派差异说明。</p>
      )}
      <p className="meta">{verification[source.verification_status] ?? '来源登记仍需进一步核对。'}</p>
      <p className="meta">版页说明：{source.edition_page_status}</p>
      <details className="disclosure">
        <summary>查看来源定位</summary>
        <div className="stack small">
          <p className="meta study-source-locator">{source.locator}</p>
          {source.path && <p className="meta study-source-locator">项目文件：{source.path}</p>}
          {href && (
            <a
              className="text-link quiet-link"
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`自行打开登记来源：${source.title}`}>
              自行打开登记来源
            </a>
          )}
        </div>
      </details>
    </li>
  );
}

export function TermDetail({ detail }: { detail: Detail }) {
  const { term } = detail;
  const sourceName = (id: string) => detail.sources.find((source) => source.source_id === id)?.title ?? '出处待核';
  return (
    <article
      className="stack study-term-detail"
      data-term-id={term.term_id}
      data-study-stage={detail.metadata.stage}
      data-definition-kind={term.definition_kind}>
      <p className="meta">
        {studySystemLabels[term.system]} · {kinds[term.definition_kind] ?? '研习概念'} · 编辑核对稿
      </p>
      {term.aliases.length > 0 && <p className="small-text">也称：{term.aliases.join('、')}</p>}
      <section className="stack small">
        <h3>白话解释</h3>
        <p>{term.plain_explanation}</p>
      </section>
      <section className="stack small">
        <h3>一个例句</h3>
        <p>{term.example}</p>
      </section>
      <section className="stack small">
        <h3>流派与适用范围</h3>
        {term.school_differences.length ? (
          term.school_differences.map((item, index) => (
            <div key={`${index}:${item.school}`} className="stack small">
              <h4>{item.school}</h4>
              <p className="small-text">{item.note}</p>
              <p className="meta">出处：{item.source_ids.map(sourceName).join('、')}</p>
            </div>
          ))
        ) : (
          <p className="small-text">本条没有补充流派差异，不代表所有流派已经达成一致。</p>
        )}
      </section>
      {term.pending_review.length > 0 && (
        <section className="stack small">
          <h3>仍待核对</h3>
          <ul>
            {term.pending_review.map((text, index) => (
              <li key={index}>{text}</li>
            ))}
          </ul>
        </section>
      )}
      <section className="stack small">
        <h3>出处与支持范围</h3>
        <ul className="study-source-list stack">
          {detail.sources.map((source) => (
            <Source key={source.source_id} source={source} detail={detail} />
          ))}
        </ul>
      </section>
      <details className="disclosure">
        <summary>词典版本与限制</summary>
        <div className="stack small">
          <p className="meta">
            {detail.metadata.version} · 共{detail.metadata.entry_count}条、{detail.metadata.source_count}份来源登记。
          </p>
          <p className="meta">资料阶段：研习草稿；编辑复核已完成，来源仍须逐条核对。</p>
          <p className="meta study-source-locator">
            登记阶段：{detail.metadata.stage}；来源登记：{detail.metadata.source_stage}；编辑标记：
            {detail.metadata.review_tag}。
          </p>
          <p className="small-text">知识草稿已做编辑核对，具体原典版页仍以每条来源说明为准。</p>
          <ul>
            {detail.metadata.limits.map((text, index) => (
              <li key={index}>{text}</li>
            ))}
          </ul>
        </div>
      </details>
    </article>
  );
}
