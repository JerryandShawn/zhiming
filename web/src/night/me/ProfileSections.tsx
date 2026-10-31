import { publicChatText } from '../../chat/publicProjection';
import { Button, Tag } from '../../components/ui/Controls';
import { PROFILE_SECTIONS, type AboutMePort, type ProfileItem } from './types';
import { Sources } from './Sources';
import type { OpenMeView } from './views';

export function ProfileSections({ items, port, open }: { items: ProfileItem[]; port: AboutMePort; open: OpenMeView }) {
  return (
    <div>
      {PROFILE_SECTIONS.map((section) => {
        const active = items.filter((item) => item.section === section.id && item.status === 'active');
        return (
          <section className="section night-me-section" key={section.id} aria-label={section.label}>
            <h2>{section.label}</h2>
            {!active.length && <p className="meta">这一节还没有已确认的画像条目。</p>}
            {active.map((item) => (
              <article
                className="night-me-item"
                key={item.id}
                data-profile-id={item.id}
                data-revision={item.revision}
                data-status={item.status}>
                <p>{publicChatText(item.text)}</p>
                {item.userEdited && <Tag>你改过</Tag>}
                <Sources port={port} refs={item.sourceRefs} />
                <div className="row wrap night-me-item-actions">
                  <Button
                    variant="ghost"
                    aria-label={`查看画像条目：${section.label}`}
                    onClick={(event) => open({ kind: 'profile-view', item }, event.currentTarget)}>
                    查看
                  </Button>
                  <Button
                    variant="ghost"
                    aria-label={`编辑画像条目：${section.label}`}
                    onClick={(event) => open({ kind: 'profile-edit', item }, event.currentTarget)}>
                    编辑
                  </Button>
                  <Button
                    variant="ghost"
                    aria-label={`删除画像条目：${section.label}`}
                    onClick={(event) => open({ kind: 'profile-delete', item }, event.currentTarget)}>
                    删除
                  </Button>
                </div>
              </article>
            ))}
          </section>
        );
      })}
    </div>
  );
}
