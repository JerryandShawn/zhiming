import { Fragment } from 'react';
import type { StudySystem } from './types';
import { useStudyTerms } from './StudyTerms';

/** Inline plain text only: callers keep Markdown links/code out of this component. */
export function StudyText({ text, system }: { text: string; system?: StudySystem }) {
  const terms = useStudyTerms();
  if (!terms || terms.indexStatus !== 'ready') return <>{text}</>;
  return (
    <>
      {terms.match(text, system).map((part, index) =>
        part.kind === 'text' ? (
          <Fragment key={index}>{part.text}</Fragment>
        ) : (
          <button
            key={index}
            type="button"
            className="study-term-link"
            aria-haspopup="dialog"
            aria-label={`查看术语：${part.text}`}
            onClick={(event) => terms.openLabel(part.label, event.currentTarget, system)}>
            {part.text}
          </button>
        ),
      )}
    </>
  );
}
