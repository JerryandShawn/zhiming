export type CourseEvidence = {
  evidence_id: string;
  case_id: string;
  context_sha256: string;
  c_alias: string;
  r_aliases: string[];
  role: 'primary' | 'basis' | 'rule_input';
  summary: string;
};
export type CourseQuiz = {
  quiz_id: string;
  question: string;
  correct_option_id: string;
  explanation: string;
  options: { option_id: string; text: string }[];
  basis: { kind: 'concept' | 'chart_observation' | 'matched_rule' };
  evidence_ids: string[];
  source_ids: string[];
};
export type CourseLesson = {
  lesson_id: string;
  order: number;
  title: string;
  level: string;
  status: 'draft_for_review';
  prerequisite_ids: string[];
  objectives: string[];
  paragraphs: string[];
  source_ids: string[];
  pending_review: string[];
  worked_examples: { case_id: string; text: string; evidence_ids: string[]; learning_point_ids: string[] }[];
  quiz: CourseQuiz[];
  school_differences: { school: string; note: string; source_ids: string[] }[];
};
export type CourseData = {
  title: string;
  lessons: CourseLesson[];
  evidence: CourseEvidence[];
  sources: {
    source_id: string;
    title: string;
    kind: string;
    verification_status: string;
    edition_page_status: string;
  }[];
  limits: string[];
};
