import { publicChatText } from '../../chat/publicProjection';
import { Button, Tag } from '../../components/ui/Controls';
import { ConfirmAction } from './ConfirmAction';
import { DeleteMemory } from './DeleteMemory';
import { ItemEditor } from './ItemEditor';
import { Sources } from './Sources';
import type { AboutMePort, AboutMeSnapshot } from './types';
import type { MeView } from './views';

export const viewTitles: Record<MeView['kind'], string> = {
  'profile-view': '画像条目详情',
  'profile-edit': '修改画像条目',
  'profile-delete': '删除画像条目',
  'memory-edit': '修改记忆',
  'memory-stop': '停用记忆',
  'memory-delete': '删除记忆',
  person: '相关记忆',
  'symbol-delete': '删除这个联想',
};
export function MeDialogBody({
  view,
  snapshot,
  port,
  close,
  confirmed,
  edit,
}: {
  view: MeView;
  snapshot: AboutMeSnapshot;
  port: AboutMePort;
  close: () => void;
  confirmed: (message: string) => void;
  edit: (view: MeView) => void;
}) {
  switch (view.kind) {
    case 'profile-view': {
      const item = snapshot.profileItems.find((entry) => entry.id === view.item.id) || view.item;
      return (
        <div className="stack">
          <p>{publicChatText(item.text)}</p>
          {item.userEdited && <Tag>你改过</Tag>}
          {item.section === 'chart_summary' && <p className="meta">这里只是画像摘要，盘面与计算口径请到命盘页核对。</p>}
          <Sources port={port} refs={item.sourceRefs} />
          <Button onClick={() => edit({ kind: 'profile-edit', item })}>编辑这条画像</Button>
        </div>
      );
    }
    case 'profile-edit':
      return (
        <ItemEditor
          item={snapshot.profileItems.find((entry) => entry.id === view.item.id) || view.item}
          kind="profile"
          port={port}
          close={close}
          confirmed={confirmed}
        />
      );
    case 'memory-edit':
      return (
        <ItemEditor
          item={snapshot.memories.find((entry) => entry.id === view.item.id) || view.item}
          kind="memory"
          port={port}
          close={close}
          confirmed={confirmed}
        />
      );
    case 'profile-delete':
      return (
        <ConfirmAction
          port={port}
          close={close}
          confirmed={confirmed}
          label="确认删除画像条目"
          text="这会移除这一条画像，保留原始来源和其他记忆。确认前不会删除。"
          command={{
            type: 'profile-delete',
            id: view.item.id,
            expectedRevision: view.item.revision,
            requestId: crypto.randomUUID(),
          }}
        />
      );
    case 'memory-stop':
      return (
        <ConfirmAction
          port={port}
          close={close}
          confirmed={confirmed}
          label="确认停用记忆"
          text="停用后，这条记忆不会再被主动提起；来源仍可核对。"
          command={{
            type: 'memory-stop',
            id: view.item.id,
            expectedRevision: view.item.revision,
            requestId: crypto.randomUUID(),
          }}
        />
      );
    case 'memory-delete':
      return (
        <DeleteMemory
          item={snapshot.memories.find((entry) => entry.id === view.item.id) || view.item}
          port={port}
          close={close}
          confirmed={confirmed}
        />
      );
    case 'symbol-delete':
      return (
        <ConfirmAction
          port={port}
          close={close}
          confirmed={confirmed}
          label="确认删除这个联想"
          text="这会删除你记录的这一条个人联想，保留原始来源。"
          command={{
            type: 'symbol-delete',
            id: view.item.id,
            expectedRevision: view.item.revision,
            requestId: crypto.randomUUID(),
          }}
        />
      );
    case 'person': {
      const current = snapshot.people.find((item) => item.id === view.item.id) || view.item;
      const memories = snapshot.memories.filter(
        (item) => item.status === 'active' && current.memoryIds.includes(item.id),
      );
      return (
        <div className="stack">
          <h3>{publicChatText(current.name)}</h3>
          <p className="meta">{publicChatText(current.relation)}</p>
          {memories.map((item) => (
            <article key={item.id}>
              <p>{publicChatText(item.text)}</p>
              <Sources port={port} refs={item.sourceRefs} />
            </article>
          ))}
          {!memories.length && <p>目前没有可核对的相关记忆。</p>}
        </div>
      );
    }
  }
}
