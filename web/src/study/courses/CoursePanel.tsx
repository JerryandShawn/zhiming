import { useEffect, useRef, useState } from 'react';
import { Button, Disclosure } from '../../components/ui/Controls';
import { CourseLessonView } from './CourseLessonView';
import { loadCourse, type CourseLoader } from './loader';
import type { CourseData } from './types';
import './courses.css';

function CourseContent({ data }: { data: CourseData }) {
  const [index, setIndex] = useState(0);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [checked, setChecked] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState('');
  const focusLesson = useRef(false);
  const lesson = data.lessons[index];
  const completed = (item: typeof lesson) =>
    item.quiz.every((quiz) => checked[quiz.quiz_id] === quiz.correct_option_id);
  const chooseLesson = (next: number) => {
    focusLesson.current = true;
    setIndex(next);
    setNotice('');
  };
  useEffect(() => {
    if (!focusLesson.current) return;
    document.getElementById('course-current-heading')?.focus({ preventScroll: true });
    focusLesson.current = false;
  }, [index]);
  return (
    <>
      <p role="status" className="meta">
        本页练习：{data.lessons.filter(completed).length}/20课已核对 · 仅当前页面内存
      </p>
      <div className="course-layout">
        <nav aria-label="课程目录" className="course-directory">
          <ol>
            {data.lessons.map((item, position) => (
              <li key={item.lesson_id}>
                <Button
                  variant="ghost"
                  aria-current={position === index ? 'step' : undefined}
                  onClick={() => chooseLesson(position)}>
                  <span>
                    第{item.order}课 {item.title}
                  </span>
                  <span className="meta">{completed(item) ? '本页已核对' : item.level}</span>
                </Button>
              </li>
            ))}
          </ol>
        </nav>
        <div className="stack course-reading">
          <CourseLessonView
            data={data}
            lesson={lesson}
            choices={choices}
            checked={checked}
            choose={(quiz, option) => {
              setChoices((value) => ({ ...value, [quiz]: option }));
              setChecked((value) => {
                const next = { ...value };
                delete next[quiz];
                return next;
              });
            }}
            check={(quiz) => {
              if (choices[quiz]) setChecked((value) => ({ ...value, [quiz]: choices[quiz] }));
            }}
          />
          <nav aria-label="课程翻页" className="row wrap between">
            <Button disabled={index === 0} onClick={() => chooseLesson(index - 1)}>
              上一课
            </Button>
            <Button disabled={index === data.lessons.length - 1} onClick={() => chooseLesson(index + 1)}>
              下一课
            </Button>
          </nav>
          <Button
            variant="ghost"
            onClick={() => {
              setChoices({});
              setChecked({});
              setNotice('本页练习已清空；没有修改档案或记忆。');
            }}>
            清空本页练习
          </Button>
          {notice && <p role="status">{notice}</p>}
        </div>
      </div>
      <Disclosure title="课程使用范围">
        <ul className="study-limit-list">
          {data.limits.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      </Disclosure>
    </>
  );
}

export default function CoursePanel({ active, loader = loadCourse }: { active: boolean; loader?: CourseLoader }) {
  const [data, setData] = useState<CourseData>();
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!active || data) return;
    const controller = new AbortController();
    let current = true;
    setPhase('loading');
    void loader(controller.signal).then(
      (value) => {
        if (current && !controller.signal.aborted) {
          setData(value);
          setPhase('ready');
        }
      },
      () => {
        if (current && !controller.signal.aborted) setPhase('error');
      },
    );
    return () => {
      current = false;
      controller.abort();
    };
  }, [active, data, loader, attempt]);
  return (
    <section className="study-panel stack" aria-label="研习课程" data-course-state={phase}>
      <header className="stack small">
        <h3>从读盘位置开始，慢慢学</h3>
        <p>20课 · 40道练习 · 固定合成样例，教材草稿待复核。</p>
        <p className="meta">
          可以随时停下，切换研习视图再回来继续；刷新或离开研习区后清空，不写入记忆、档案或设备存储。
        </p>
      </header>
      {phase === 'loading' && <p role="status">正在核对课程资料…</p>}
      {phase === 'error' && (
        <div role="alert" className="study-read-error stack small">
          <p>课程资料暂未通过核对。对话草稿与旧版词典、学习卡仍可使用。</p>
          <Button onClick={() => setAttempt((value) => value + 1)}>重新读取课程</Button>
        </div>
      )}
      {data && <CourseContent data={data} />}
    </section>
  );
}
