import { createContext, useContext, useId, useMemo, type ReactNode } from 'react';
import DialogContent from '../components/ui/DialogContent';
import { Button } from '../components/ui/Controls';
import type { StudyPort } from './types';
import { TermDetail, studySystemLabels } from './TermDetail';
import { buildTermMatcher, type TermMatcher } from './termMatching';
import { useStudyTermsController } from './useStudyTermsController';
import './study-terms.css';

type Context = Pick<ReturnType<typeof useStudyTermsController>, 'terms' | 'indexStatus' | 'openTerm' | 'openLabel'> & {
  match: TermMatcher;
};
const Terms = createContext<Context | undefined>(undefined);
export const useStudyTerms = () => useContext(Terms);

/** Keep this provider mounted while the readonly catalog is loading/reloading. */
export function StudyTermProvider({ port, children }: { port?: StudyPort; children: ReactNode }) {
  const model = useStudyTermsController(port);
  const contentId = useId();
  const match = useMemo(() => buildTermMatcher(model.terms), [model.terms]);
  const view = model.view;
  return (
    <Terms.Provider
      value={{
        terms: model.terms,
        indexStatus: model.indexStatus,
        openTerm: model.openTerm,
        openLabel: model.openLabel,
        match,
      }}>
      {children}
      <DialogContent
        open={model.open}
        title={view?.phase === 'ready' ? `${view.detail.term.term} · 术语解释` : '术语解释'}
        description="只读研习词典。请同时核对体系、出处、流派差异和仍待验证的范围。"
        contentId={contentId}
        sheet
        onOpenChange={(next) => {
          if (!next) model.close();
        }}
        onReturnFocus={model.returnFocus}>
        {view?.phase === 'loading' ? (
          <p role="status">正在读取词条…</p>
        ) : view?.phase === 'choose' ? (
          <section className="stack" aria-label="选择术语体系">
            <h3>这个名字属于几个体系</h3>
            <p className="small-text">先选择你想查的词条；这里不会默认取第一项。</p>
            {view.candidates.map((term) => (
              <Button key={term.term_id} onClick={() => model.choose(term.term_id)}>
                {studySystemLabels[term.system]} · {term.term}
              </Button>
            ))}
          </section>
        ) : view?.phase === 'ready' ? (
          <TermDetail detail={view.detail} />
        ) : view?.phase === 'unavailable' ? (
          <p role="status">{view.message}</p>
        ) : null}
      </DialogContent>
    </Terms.Provider>
  );
}
