import { lazy, Suspense, useState, type ReactNode } from 'react';
import { Button, Disclosure, Segmented, Tag } from '../components/ui/Controls';
import { GlossaryPanel } from './GlossaryPanel';
import { LearningPanel } from './LearningPanel';
import { StudyTermProvider } from './StudyTerms';
import { StudyText } from './StudyText';
import { useStudyCatalog } from './useStudyCatalog';
import type { StudyLoadSession } from './staticLoader';
import './study.css';

const CoursePanel = lazy(() => import('./courses/CoursePanel'));
type View = 'chat' | 'dictionary' | 'cards' | 'courses';

export default function StudyWorkspace({
  children,
  createSession,
}: {
  children: ReactNode;
  createSession?: () => StudyLoadSession;
}) {
  const [tab, setTab] = useState<View>(() =>
    new URLSearchParams(window.location.hash.split('?')[1]).get('view') === 'courses' ? 'courses' : 'chat',
  );
  const [coursesOpened, setCoursesOpened] = useState(tab === 'courses');
  const catalog = useStudyCatalog(createSession);
  const ready = catalog.view.status === 'ready' ? catalog.view : undefined;
  return (
    <StudyTermProvider port={ready?.port}>
      <section
        className="study-workspace stack"
        aria-label="命理研习工具"
        data-runtime="study-workspace"
        data-study-state={catalog.view.status}>
        <header className="study-workspace-heading stack small">
          <div className="row wrap between">
            <h2>命理研习</h2>
            <Tag>只读研习资料</Tag>
          </div>
          <p className="small-text secondary-text">
            查词、读卡，再把疑问留在对话里。这里不读取你的档案、不修改个人符号词典，也不会生成新结论。
          </p>
          {ready && (
            <p className="meta">
              {ready.metadata.glossary.entry_count}条术语 · {ready.metadata.glossary.source_count}处登记出处 ·{' '}
              {ready.metadata.learning.reduce((count, item) => count + item.card_count, 0)}张合成学习卡
            </p>
          )}
        </header>
        <Segmented<View>
          label="命理研习视图"
          options={[
            { value: 'chat', label: '对话' },
            { value: 'dictionary', label: '术语词典' },
            { value: 'cards', label: '学习卡' },
            { value: 'courses', label: '研习课程' },
          ]}
          value={tab}
          onChange={(next) => {
            if (next === 'courses') setCoursesOpened(true);
            setTab(next);
          }}
        />
        {catalog.view.status === 'loading' && (
          <p role="status" className="meta">
            正在载入只读研习资料，对话草稿仍可继续写。
          </p>
        )}
        {catalog.view.status === 'error' && (
          <div className="study-read-error stack small" role="alert">
            <h3>研习资料没有载入</h3>
            <p>可以重试，原对话和你写的草稿仍保留。</p>
            <Button onClick={catalog.reload}>重新载入研习资料</Button>
          </div>
        )}
        <div className="study-tab-content" hidden={tab !== 'chat'}>
          <aside className="study-conversation-example stack small" aria-label="研习提示合成示例">
            <p className="meta">研习提示 · 合成示例</p>
            <p>
              <StudyText text="可以从日主、命宫和上升点逐条查起。" />
            </p>
          </aside>
          {children}
        </div>
        <div className="study-tab-content" hidden={tab !== 'dictionary'}>
          <GlossaryPanel port={ready?.port} metadata={ready?.metadata} />
        </div>
        <div className="study-tab-content" hidden={tab !== 'cards'}>
          <LearningPanel port={ready?.port} metadata={ready?.metadata} />
        </div>
        <div className="study-tab-content" hidden={tab !== 'courses'}>
          {coursesOpened && (
            <Suspense fallback={<p role="status">正在展开课程…</p>}>
              <CoursePanel active={tab === 'courses'} />
            </Suspense>
          )}
        </div>
        {ready && (
          <Disclosure title="研习资料的口径与限制">
            <div className="stack small">
              <p>术语为已整理的研习草稿；保留具体来源、流派差异与待核项，不把编辑复核当作原典重新核验或预测效度。</p>
              <ul className="study-limit-list small-text secondary-text">
                {ready.metadata.glossary.limits.map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
              <Button variant="ghost" onClick={catalog.reload}>
                重新载入研习资料
              </Button>
            </div>
          </Disclosure>
        )}
      </section>
    </StudyTermProvider>
  );
}
