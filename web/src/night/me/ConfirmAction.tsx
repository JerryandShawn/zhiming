import { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '../../components/ui/Controls';
import type { AboutMeCommand, AboutMePort } from './types';
import { CancelButton, CommandFeedback, useMeCommand } from './useMeCommand';

export function ConfirmAction({
  command,
  text,
  label,
  port,
  close,
  confirmed,
}: {
  command: AboutMeCommand;
  text: string;
  label: string;
  port: AboutMePort;
  close: () => void;
  confirmed: (text: string) => void;
}) {
  const operation = useMeCommand(port);
  const [review, setReview] = useState(false);
  return (
    <div className="stack">
      <p className="row small-text">
        <AlertTriangle className="icon" aria-hidden="true" />
        {text}
      </p>
      <CommandFeedback operation={operation} success="操作已确认。" />
      {operation.conflict && (
        <div className="stack small">
          <Button onClick={() => setReview(true)}>核对当前版本</Button>
          {review && <p>请关闭此页，核对列表中的当前内容，再重新选择操作。旧操作不会继续提交。</p>}
        </div>
      )}
      <div className="row wrap">
        <Button
          disabled={operation.conflict || Boolean(operation.receipt)}
          loading={operation.busy}
          onClick={() =>
            void operation.run(command).then((receipt) => {
              if (receipt) {
                confirmed('操作已确认。');
                close();
              }
            })
          }>
          {operation.hasPending && !operation.conflict ? '用原操作重试' : label}
        </Button>
        <CancelButton close={close} disabled={operation.busy} />
      </div>
    </div>
  );
}
