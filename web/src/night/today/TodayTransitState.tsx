import { Button } from '../../components/ui/Controls';
import { Skeleton } from '../../components/ui/Feedback';
import TodayTransit from './TodayTransit';
import type { TodayPort, TodayReadResult } from './types';

export type TodayLoad = TodayReadResult | { status: 'loading' | 'error' | 'invalid'; date: string };
export default function TodayTransitState({
  view,
  port,
  retry,
}: {
  view: TodayLoad;
  port: TodayPort;
  retry: () => void;
}) {
  if (view.status === 'invalid')
    return (
      <p id="today-date-hint" role="status" className="small-text">
        请先选择日期，再查看这一天的流日。
      </p>
    );
  if (view.status === 'loading') return <Skeleton label="正在载入流日要点" />;
  if (view.status === 'error')
    return (
      <div className="stack small" role="alert">
        <p>这一天的流日暂时没载入，原有安排还在。你可以重试。</p>
        <div>
          <Button onClick={retry}>重试流日</Button>
        </div>
      </div>
    );
  if (view.status === 'empty')
    return (
      <p className="small-text" role="status">
        {view.message}
      </p>
    );
  if (view.status === 'ready') return <TodayTransit key={view.transit.documentId} transit={view.transit} port={port} />;
  return null;
}
