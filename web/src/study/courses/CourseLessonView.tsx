import { useId } from 'react';
import { Button, Disclosure } from '../../components/ui/Controls';
import type { CourseData, CourseLesson, CourseQuiz } from './types';

const caseLabels: Record<string, string> = {
  'ayuan-bazi': '阿远 · 八字',
  'ayuan-ziwei': '阿远 · 紫微斗数',
  'ayuan-astro': '阿远 · 西方占星',
};
const sourceStatus: Record<string, string> = {
  implementation_locator_checked: '已核对项目程序定位；不等于原典或现实效度核验。',
  official_document_read: '来源登记记录了官方说明的阅读；本页未重新访问外网。',
  original_editorial_read: '项目原创研习说明；不冒称古籍原文或统一流派结论。',
};

function Quiz({
  quiz,
  selected,
  checked,
  choose,
  check,
}: {
  quiz: CourseQuiz;
  selected?: string;
  checked?: string;
  choose: (id: string) => void;
  check: () => void;
}) {
  const id = useId();
  return (
    <fieldset className="course-question stack small" data-course-quiz={quiz.quiz_id}>
      <legend>{quiz.question}</legend>
      {quiz.options.map((option) => (
        <label className="course-option" key={option.option_id}>
          <input
            type="radio"
            name={id}
            value={option.option_id}
            checked={selected === option.option_id}
            onChange={() => choose(option.option_id)}
          />
          <span>{option.text}</span>
        </label>
      ))}
      <Button onClick={check} disabled={!selected}>
        核对这题
      </Button>
      {checked && (
        <div role="status" className="course-answer stack small">
          <p>{checked === quiz.correct_option_id ? '这题已核对。' : '再读一下依据，可以重新选择。'}</p>
          <p>{quiz.explanation}</p>
          <p className="meta">
            {quiz.basis.kind === 'concept'
              ? '概念练习，依据为登记出处，不生成计算别名。'
              : '只按这份固定合成样例核对，不代表现实预测。'}
          </p>
        </div>
      )}
    </fieldset>
  );
}

export function CourseLessonView({
  data,
  lesson,
  choices,
  checked,
  choose,
  check,
}: {
  data: CourseData;
  lesson: CourseLesson;
  choices: Record<string, string>;
  checked: Record<string, string>;
  choose: (quiz: string, option: string) => void;
  check: (quiz: string) => void;
}) {
  const evidenceIds = new Set([
    ...lesson.worked_examples.flatMap((item) => item.evidence_ids),
    ...lesson.quiz.flatMap((item) => item.evidence_ids),
  ]);
  const evidence = data.evidence.filter((row) => evidenceIds.has(row.evidence_id));
  return (
    <article
      className="course-lesson stack"
      aria-label={`第${lesson.order}课 ${lesson.title}`}
      data-course-lesson={lesson.lesson_id}>
      <header className="stack small">
        <p className="meta">
          第{lesson.order}课 · {lesson.level} · 教材草稿待复核
        </p>
        <h3 tabIndex={-1} id="course-current-heading">
          {lesson.title}
        </h3>
      </header>
      <div className="stack small">
        <h4>这一课读什么</h4>
        <ul className="study-limit-list">
          {lesson.objectives.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      </div>
      {lesson.paragraphs.map((text) => (
        <p key={text}>{text}</p>
      ))}
      <section className="stack small" aria-label="本课合成样例">
        <h4>在合成样例里看</h4>
        {lesson.worked_examples.map((example, index) => (
          <div key={`${example.case_id}-${index}`} className="stack small">
            <p className="meta">{caseLabels[example.case_id]} · 本课程独立合成样例</p>
            <p>{example.text}</p>
          </div>
        ))}
      </section>
      <Disclosure title="本课依据与口径">
        <ul className="study-source-list">
          {evidence.map((row) => (
            <li key={row.evidence_id} className="stack small">
              <p>
                {caseLabels[row.case_id]} · 〔{row.c_alias}〕{row.r_aliases.map((name) => `〔${name}〕`).join('')}
              </p>
              <p>{row.summary}</p>
              <p className="meta">仅在本课程这一份合成样例中有效。</p>
            </li>
          ))}
        </ul>
        <p className="meta">保留原别名，不与旧版学习卡按短号合并；不展开原始时刻或完整盘面。</p>
      </Disclosure>
      <section className="stack" aria-label="本课练习">
        <h4>读完试两题</h4>
        {lesson.quiz.map((quiz) => (
          <Quiz
            key={quiz.quiz_id}
            quiz={quiz}
            selected={choices[quiz.quiz_id]}
            checked={checked[quiz.quiz_id]}
            choose={(option) => choose(quiz.quiz_id, option)}
            check={() => check(quiz.quiz_id)}
          />
        ))}
      </section>
      <Disclosure title="出处、流派差异与待核项">
        <div className="stack small">
          <h4>登记出处</h4>
          <ul className="study-source-list">
            {data.sources
              .filter((row) => lesson.source_ids.includes(row.source_id))
              .map((row) => (
                <li key={row.source_id}>
                  <p>{row.title}</p>
                  <p className="meta">
                    {sourceStatus[row.verification_status] ?? '来源登记仍待核对。'} {row.edition_page_status}
                  </p>
                </li>
              ))}
          </ul>
          {lesson.school_differences.map((row) => (
            <div key={row.school}>
              <h4>{row.school}</h4>
              <p>{row.note}</p>
            </div>
          ))}
          <h4>仍待核对</h4>
          <ul className="study-limit-list">
            {lesson.pending_review.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </div>
      </Disclosure>
    </article>
  );
}
