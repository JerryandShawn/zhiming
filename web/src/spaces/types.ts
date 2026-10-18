export interface Space {
  id: string;
  name: string;
  description: string;
  sensitive: boolean;
  order: number;
  hidden: boolean;
  revision: number;
  lastAt: string;
  unread: number;
}

export interface Topic {
  id: string;
  spaceId: string;
  title: string;
  status: 'open' | 'archived' | 'case';
  summary: string;
  messageIds: string[];
  createdAt: string;
  lastAt: string;
  needsReview?: boolean;
}

export interface SpaceMessage {
  id: string;
  spaceId: string;
  topicId: string;
  role: 'user' | 'assistant';
  text: string;
  at: string;
  secondarySpaceId?: string;
}

export interface SpaceMemory {
  id: string;
  spaceId: string;
  topicId?: string;
  text: string;
}

export interface SpacePerson {
  id: string;
  spaceId: string;
  name: string;
  relation: string;
}

export interface SpaceCase {
  id: string;
  spaceId: string;
  topicId?: string;
  title: string;
  status: string;
}

export interface Dataset {
  spaces: Space[];
  topics: Topic[];
  messages: SpaceMessage[];
  memories: SpaceMemory[];
  people: SpacePerson[];
  cases: SpaceCase[];
}

export interface Proposal {
  spaces: Space[];
  topics: Topic[];
  ignoredTopicIds: string[];
}

export interface AppliedBatch {
  batchId: string;
  before: Dataset;
  after: Dataset;
}
