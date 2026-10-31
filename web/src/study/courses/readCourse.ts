import { array, fields, hex, integer, plainText, stringList, studyNeed, unique } from '../validation';
import type { CourseData, CourseEvidence, CourseLesson, CourseQuiz } from './types';

export const COURSE_COMMIT = 'f8d9536a44db67a84db9315c208e2a66893214c9';
export const COURSE_MANIFEST_SHA = '1491b7ce765e2b4317c309fcceb05288b87222a40e40a284a375c22533781a6c';
const ids = (value: unknown) => {
  const list = stringList(value);
  studyNeed(unique(list));
  return list;
};
const subset = (values: string[], available: Set<string>) => studyNeed(values.every((name) => available.has(name)));
function evidence(value: unknown): CourseEvidence {
  const row = fields(value, ['evidence_id', 'case_id', 'context_sha256', 'c_alias', 'r_aliases', 'role', 'summary']);
  const role = row.role,
    c = plainText(row.c_alias),
    rules = ids(row.r_aliases);
  studyNeed(role === 'primary' || role === 'basis' || role === 'rule_input');
  studyNeed(/^c[1-9][0-9]*$/.test(c) && rules.every((name) => /^r[1-9][0-9]*$/.test(name)));
  studyNeed(role !== 'rule_input' || rules.length > 0);
  return {
    evidence_id: plainText(row.evidence_id),
    case_id: plainText(row.case_id),
    context_sha256: hex(row.context_sha256),
    c_alias: c,
    r_aliases: rules,
    role,
    summary: plainText(row.summary),
  };
}
function quiz(value: unknown): CourseQuiz {
  const row = fields(value, [
    'quiz_id',
    'question',
    'correct_option_id',
    'explanation',
    'options',
    'basis',
    'evidence_ids',
    'source_ids',
  ]);
  const options = array(row.options).map((value) => {
    const option = fields(value, ['option_id', 'text']);
    return { option_id: plainText(option.option_id), text: plainText(option.text) };
  });
  const answer = plainText(row.correct_option_id),
    kind = fields(row.basis, ['kind']).kind;
  studyNeed(kind === 'concept' || kind === 'chart_observation' || kind === 'matched_rule');
  studyNeed(
    options.length === 3 &&
      unique(options.map((item) => item.option_id)) &&
      options.some((item) => item.option_id === answer),
  );
  const evidence_ids = ids(row.evidence_ids),
    source_ids = ids(row.source_ids);
  studyNeed(
    kind === 'concept'
      ? evidence_ids.length === 0 && source_ids.length > 0
      : evidence_ids.length === 1 && source_ids.length === 0,
  );
  return {
    quiz_id: plainText(row.quiz_id),
    question: plainText(row.question),
    correct_option_id: answer,
    explanation: plainText(row.explanation),
    options,
    basis: { kind },
    evidence_ids,
    source_ids,
  };
}
function lesson(value: unknown): CourseLesson {
  const row = fields(value, [
    'lesson_id',
    'order',
    'title',
    'level',
    'status',
    'prerequisite_ids',
    'objectives',
    'paragraphs',
    'source_ids',
    'pending_review',
    'worked_examples',
    'quiz',
    'school_differences',
  ]);
  studyNeed(row.status === 'draft_for_review');
  return {
    lesson_id: plainText(row.lesson_id),
    order: integer(row.order, 1, 20),
    title: plainText(row.title),
    level: plainText(row.level),
    status: 'draft_for_review',
    prerequisite_ids: ids(row.prerequisite_ids),
    objectives: stringList(row.objectives),
    paragraphs: stringList(row.paragraphs),
    source_ids: ids(row.source_ids),
    pending_review: stringList(row.pending_review),
    quiz: array(row.quiz).map(quiz),
    worked_examples: array(row.worked_examples).map((value) => {
      const item = fields(value, ['case_id', 'text', 'evidence_ids', 'learning_point_ids']);
      return {
        case_id: plainText(item.case_id),
        text: plainText(item.text),
        evidence_ids: ids(item.evidence_ids),
        learning_point_ids: ids(item.learning_point_ids),
      };
    }),
    school_differences: array(row.school_differences).map((value) => {
      const item = fields(value, ['school', 'note', 'source_ids']);
      return { school: plainText(item.school), note: plainText(item.note), source_ids: ids(item.source_ids) };
    }),
  };
}
function relationships(data: CourseData, contexts: Map<string, string>) {
  const evidence = new Map(data.evidence.map((row) => [row.evidence_id, row]));
  const sources = new Set(data.sources.map((row) => row.source_id));
  studyNeed(evidence.size === 20 && sources.size === 39 && data.sources.length === 39);
  studyNeed(data.evidence.every((row) => row.context_sha256 === contexts.get(row.case_id)));
  const earlier = new Set<string>(),
    quizzes = new Set<string>();
  for (const [index, item] of data.lessons.entries()) {
    studyNeed(item.lesson_id === `lesson-${String(index + 1).padStart(2, '0')}` && item.order === index + 1);
    subset(item.prerequisite_ids, earlier);
    subset(item.source_ids, sources);
    const declared = new Set(item.source_ids),
      worked = new Set<string>();
    for (const example of item.worked_examples) {
      studyNeed(contexts.has(example.case_id));
      worked.add(example.case_id);
      studyNeed(example.evidence_ids.every((id) => evidence.get(id)?.case_id === example.case_id));
    }
    item.school_differences.forEach((row) => subset(row.source_ids, declared));
    studyNeed(item.quiz.length === 2);
    for (const [position, question] of item.quiz.entries()) {
      studyNeed(question.quiz_id === `${item.lesson_id}-q${position + 1}` && !quizzes.has(question.quiz_id));
      quizzes.add(question.quiz_id);
      subset(question.source_ids, declared);
      for (const id of question.evidence_ids) {
        const row = evidence.get(id);
        studyNeed(row && worked.has(row.case_id));
        studyNeed(question.basis.kind !== 'matched_rule' || row.role === 'rule_input');
      }
    }
    earlier.add(item.lesson_id);
  }
  studyNeed(earlier.size === 20 && quizzes.size === 40);
}
export function readCourse(value: unknown): CourseData {
  const row = fields(value, [
    'format',
    'title',
    'status',
    'synthetic_only',
    'lessons',
    'cases',
    'evidence',
    'sources',
    'provenance',
    'effects',
    'limits',
  ]);
  studyNeed(row.format === 'frontend-course-v1' && row.status === 'draft_for_review' && row.synthetic_only === true);
  const origins = fields(row.provenance, ['source_commit', 'manifest_sha256_lf_utf8', 'input_sha256_lf_utf8']);
  studyNeed(origins.source_commit === COURSE_COMMIT && origins.manifest_sha256_lf_utf8 === COURSE_MANIFEST_SHA);
  const effects = fields(row.effects, ['model_calls', 'user_writes', 'network_calls']);
  studyNeed(Object.values(effects).every((value) => value === 0));
  const contexts = new Map(
    array(row.cases).map((value) => {
      const item = fields(value, ['case_id', 'context_sha256', 'learning']);
      // Companion cards belong to this independent snapshot; this view does not render or merge them into the old StudyPort.
      return [plainText(item.case_id), hex(item.context_sha256)] as const;
    }),
  );
  studyNeed(contexts.size === 3 && ['ayuan-bazi', 'ayuan-ziwei', 'ayuan-astro'].every((id) => contexts.has(id)));
  const result: CourseData = {
    title: plainText(row.title),
    lessons: array(row.lessons).map(lesson),
    evidence: array(row.evidence).map(evidence),
    limits: stringList(row.limits),
    sources: array(row.sources).map((value) => {
      const item = fields(value, ['source_id', 'title', 'kind', 'verification_status', 'edition_page_status']);
      return {
        source_id: plainText(item.source_id),
        title: plainText(item.title),
        kind: plainText(item.kind),
        verification_status: plainText(item.verification_status),
        edition_page_status: plainText(item.edition_page_status),
      };
    }),
  };
  relationships(result, contexts);
  return result;
}
