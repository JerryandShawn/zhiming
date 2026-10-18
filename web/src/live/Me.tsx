import { useState } from 'react';
import { useResource } from '../api/useResource';
import { Button, Segmented, Seal } from '../components/ui/Controls';
import { ResourceState } from './common';
import MemoryCard from './MemoryCard';
import ProfileForm from './ProfileForm';
import LegacyPreview from './LegacyPreview';
import type { Fact, Profile } from './types';

const sections = [
  { value: 'profile', label: '资料与画像' },
  { value: 'memory', label: '记忆' },
  { value: 'pending', label: '待确认' },
  { value: 'people', label: '重要的人' },
  { value: 'timeline', label: '时间线' },
  { value: 'dictionary', label: '符号词典' },
];
export default function Me() {
  const initial = new URLSearchParams(location.hash.split('?')[1]).get('section') ?? 'profile';
  const [tab, setTab] = useState(sections.some((item) => item.value === initial) ? initial : 'profile');
  const facts = useResource<Fact[]>('/api/memories?subject_id=self');
  const profile = useResource<Profile>(tab === 'profile' ? '/api/subjects/self/profile' : null);
  const active = facts.data?.filter((fact) => fact.status === 'active').length;
  const refresh = () => {
    void facts.refetch();
  };
  return (
    <div className="page" data-page="me">
      <header className="me-heading row">
        <Seal size="large" />
        <div>
          <h1>关于我</h1>
          <p className="meta">{active === undefined ? '正在核对有效记忆' : `目前有 ${active} 条有效记忆`}</p>
        </div>
      </header>
      <div className="route-tabs">
        <Segmented label="关于我的分区" options={sections} value={tab} onChange={setTab} />
      </div>
      {tab === 'profile' ? (
        <>
          <ResourceState
            loading={profile.isPending}
            error={profile.error}
            retry={() => {
              void profile.refetch();
            }}
          />
          {profile.data && (
            <ProfileForm
              profile={profile.data}
              onSaved={() => {
                void profile.refetch();
                refresh();
              }}
            />
          )}
          <section className="section">
            <h2>画像</h2>
            <p className="secondary-text">新版画像整理服务尚未接入。已确认的原话记忆可在“记忆”中查看和更正。</p>
            <Button disabled>编辑新版画像</Button>
          </section>
        </>
      ) : tab === 'memory' ? (
        <section className="section stack">
          <h2>记忆与来源</h2>
          <ResourceState loading={facts.isPending} error={facts.error} retry={refresh} />
          {facts.data
            ?.filter((fact) => fact.status !== 'deleted')
            .map((fact) => (
              <MemoryCard key={fact.id} fact={fact} onSaved={refresh} />
            ))}
          {facts.data?.filter((fact) => fact.status !== 'deleted').length === 0 && <p>还没有长期记忆。</p>}
        </section>
      ) : (
        <section className="section">
          <h2>{sections.find((item) => item.value === tab)?.label}</h2>
          {tab === 'pending' ? (
            <>
              <p className="secondary-text">暂时无法在这里确认或拒绝待记忆内容。出生资料请到“资料与画像”明确核对。</p>
              <Button disabled>确认记忆提案</Button>
            </>
          ) : (
            <LegacyPreview section={tab} />
          )}
          <p>
            <a className="text-link quiet-link" href="#/chat">
              查看对话历史
            </a>
          </p>
        </section>
      )}
    </div>
  );
}
