import { ChevronRight } from 'lucide-react';
import { publicChatText } from '../../chat/publicProjection';
import { Button } from '../../components/ui/Controls';
import { Panel } from '../../components/ui/Overlays';
import type { AboutMePort, SourceProjection, SourceRef } from './types';

export function sourceChannel(channel: string) {
  return (
    ({ feishu: '飞书', web: '网页', 'web-action': '网页确认' } as Record<string, string>)[channel] ||
    publicChatText(channel)
  );
}

function projection(port: AboutMePort, ref: SourceRef): SourceProjection {
  try {
    return port.readSource(ref);
  } catch {
    return { ref, available: false, reason: '暂时无法核对这条来源。' };
  }
}
export function SourceQuote({ port, source }: { port: AboutMePort; source?: SourceRef }) {
  if (!source) return <p className="meta">目前没有可核对的原话。</p>;
  const result = projection(port, source);
  return result.available && result.quote ? (
    <>
      <blockquote className="memory-quote">{publicChatText(result.quote)}</blockquote>
      <p className="meta">
        {publicChatText(result.label || `${source.at.slice(0, 10)} · ${sourceChannel(source.channel)}`)}
      </p>
    </>
  ) : (
    <p className="meta">这条来源目前不可查看，不显示未经核对的原话。</p>
  );
}
export function Sources({ port, refs }: { port: AboutMePort; refs: SourceRef[] }) {
  if (!refs.length) return <p className="meta">目前没有可核对的来源。</p>;
  return (
    <div className="night-me-sources row wrap">
      {refs.map((ref, index) => {
        const label = refs.length === 1 ? '查看来源' : `查看来源${index + 1}`;
        return (
          <div className="row wrap" key={`${ref.messageId}-${ref.version}-${ref.start}-${ref.end}`}>
            <span className="meta">
              来自 {ref.at.slice(5, 10).replace('-', '/')} {sourceChannel(ref.channel)}
            </span>
            <Panel
              title="来源原话"
              description="只显示你授权核对的引用片段，不展开整段对话。"
              trigger={
                <Button variant="ghost" aria-label={label}>
                  {label}
                  <ChevronRight className="icon small" aria-hidden="true" />
                </Button>
              }>
              <SourceQuote port={port} source={ref} />
            </Panel>
          </div>
        );
      })}
    </div>
  );
}
