import {
  DraftApiError,
  draftRequest,
  exactKeys,
  isId,
  isInstant,
  isRevision,
  isText,
  record,
  sourceRef,
  writeResult,
  type Receipt,
  type SourceRef,
  type WriteIdentity,
} from '../modules/draftApi';
import type { RequestOwner } from '../threads/request';

// mod api_spaces_topics_draft 0.1.0 @ daccd26c. Space ids are open-ended (users create spaces).
export type ApiSpace = Readonly<{
  id: string;
  revision: number;
  name: string;
  description: string;
  order: number;
  hidden: boolean;
  sensitive: boolean;
}>;
export type ApiTopic = Readonly<{
  id: string;
  space_id: string;
  revision: number;
  title: string;
  status: 'open' | 'archived' | 'case';
  summary: string;
  source_refs: readonly SourceRef[];
  case_id: string | null;
  updated_at: string;
  summary_until_message_id: string | null;
  created_at: string;
  last_at: string;
}>;
export type Page<T> = Readonly<{ items: readonly T[]; next_cursor: string | null }>;
export type ListQuery = { limit?: number; cursor?: string; subject_id?: string; include_hidden?: boolean };
export type SpacePatch = Partial<Pick<ApiSpace, 'name' | 'description' | 'order' | 'hidden'>>;
export type TopicPatch = Partial<{ title: string; space_id: string; status: ApiTopic['status']; case_id: string }>;

const bad = () => new DraftApiError('BAD_RESPONSE');
function space(value: unknown): ApiSpace {
  const item = record(value);
  if (
    !exactKeys(item, ['id', 'revision', 'name', 'description', 'order', 'hidden', 'sensitive']) ||
    !isId(item.id) ||
    !isRevision(item.revision) ||
    !isText(item.name, 1, 60) ||
    !isText(item.description, 0, 500) ||
    !Number.isSafeInteger(item.order) ||
    (item.order as number) < 0 ||
    (item.order as number) > 10000 ||
    typeof item.hidden !== 'boolean' ||
    typeof item.sensitive !== 'boolean'
  )
    throw bad();
  return Object.freeze(item as ApiSpace);
}
const topicKeys = [
  'id',
  'space_id',
  'revision',
  'title',
  'status',
  'summary',
  'source_refs',
  'case_id',
  'updated_at',
  'summary_until_message_id',
  'created_at',
  'last_at',
] as const;
function topic(value: unknown, spaceId: string): ApiTopic {
  const item = record(value);
  if (
    !exactKeys(item, topicKeys) ||
    !isId(item.id) ||
    item.space_id !== spaceId ||
    !isRevision(item.revision) ||
    !isText(item.title, 1, 80) ||
    !['open', 'archived', 'case'].includes(item.status as string) ||
    !isText(item.summary, 0, 1000) ||
    !Array.isArray(item.source_refs) ||
    item.source_refs.length > 50 ||
    (item.status === 'case' ? !isId(item.case_id) : item.case_id !== null) ||
    (item.summary_until_message_id !== null && !isId(item.summary_until_message_id)) ||
    !isInstant(item.updated_at) ||
    !isInstant(item.created_at) ||
    !isInstant(item.last_at) ||
    Date.parse(item.created_at) > Date.parse(item.last_at)
  )
    throw bad();
  return Object.freeze({ ...(item as ApiTopic), source_refs: Object.freeze(item.source_refs.map(sourceRef)) });
}
function page<T>(value: unknown, parse: (item: unknown) => T): Page<T> {
  const body = record(value);
  if (
    !exactKeys(body, ['items', 'next_cursor']) ||
    !Array.isArray(body.items) ||
    (body.next_cursor !== null && !isText(body.next_cursor, 1, 512))
  )
    throw bad();
  const items = body.items.map(parse);
  if (new Set(items.map((item) => (item as { id: string }).id)).size !== items.length) throw bad();
  return Object.freeze({ items: Object.freeze(items), next_cursor: body.next_cursor as string | null });
}
function query(value: ListQuery) {
  if (
    (value.limit !== undefined && (!Number.isSafeInteger(value.limit) || value.limit < 1 || value.limit > 100)) ||
    (value.cursor !== undefined && !isText(value.cursor, 1, 512)) ||
    (value.subject_id !== undefined && !isId(value.subject_id))
  )
    throw new DraftApiError('VALIDATION_ERROR');
  return { ...value };
}
function patch<T extends object>(value: T, check: (key: string, item: unknown) => boolean) {
  const entries = Object.entries(value).filter(([, item]) => item !== undefined);
  if (!entries.length || !entries.every(([key, item]) => check(key, item))) throw new DraftApiError('VALIDATION_ERROR');
  return Object.fromEntries(entries) as T;
}
const segment = (id: string) => {
  if (!isId(id)) throw new DraftApiError('VALIDATION_ERROR');
  return encodeURIComponent(id);
};

export type SpacesTopicsPort = ReturnType<typeof spacesTopicsHttpPort>;
/** Callers build each write once with writeIntent() and resend that exact object after unknown outcomes. */
export function spacesTopicsHttpPort(fetcher: typeof fetch = fetch) {
  const write = async (
    method: 'POST' | 'PATCH',
    path: string,
    body: WriteIdentity,
    owner: RequestOwner,
  ): Promise<Receipt> => writeResult(await draftRequest(fetcher, { method, path, body }, owner), body.request_id);
  return {
    async listSpaces(list: ListQuery, owner: RequestOwner) {
      return page(
        await draftRequest(fetcher, { method: 'GET', path: '/api/spaces', query: query(list) }, owner),
        space,
      );
    },
    async listTopics(spaceId: string, list: ListQuery, owner: RequestOwner) {
      const path = `/api/spaces/${segment(spaceId)}/topics`;
      return page(await draftRequest(fetcher, { method: 'GET', path, query: query(list) }, owner), (item) =>
        topic(item, spaceId),
      );
    },
    createSpace(body: WriteIdentity & { name: string; description: string; sensitive: boolean }, owner: RequestOwner) {
      if (
        body.expected_revision !== 0 ||
        !isText(body.name.trim(), 1, 60) ||
        !isText(body.description, 0, 500) ||
        typeof body.sensitive !== 'boolean'
      )
        throw new DraftApiError('VALIDATION_ERROR');
      return write('POST', '/api/spaces', body, owner);
    },
    patchSpace(spaceId: string, body: WriteIdentity & { patch: SpacePatch }, owner: RequestOwner) {
      patch(body.patch, (key, item) =>
        key === 'name'
          ? isText(item, 1, 60)
          : key === 'description'
            ? isText(item, 0, 500)
            : key === 'order'
              ? Number.isSafeInteger(item) && (item as number) >= 0 && (item as number) <= 10000
              : key === 'hidden' && typeof item === 'boolean',
      );
      if (!isRevision(body.expected_revision)) throw new DraftApiError('VALIDATION_ERROR');
      return write('PATCH', `/api/spaces/${segment(spaceId)}`, body, owner);
    },
    createTopic(spaceId: string, body: WriteIdentity & { title: string }, owner: RequestOwner) {
      if (body.expected_revision !== 0 || !isText(body.title.trim(), 1, 80))
        throw new DraftApiError('VALIDATION_ERROR');
      return write('POST', `/api/spaces/${segment(spaceId)}/topics`, body, owner);
    },
    patchTopic(topicId: string, body: WriteIdentity & { patch: TopicPatch }, owner: RequestOwner) {
      const value = patch(body.patch, (key, item) =>
        key === 'title'
          ? isText(item, 1, 80)
          : key === 'space_id' || key === 'case_id'
            ? isId(item)
            : key === 'status' && ['open', 'archived', 'case'].includes(item as string),
      );
      if (!isRevision(body.expected_revision) || (value.status === 'case' && !value.case_id))
        throw new DraftApiError('VALIDATION_ERROR');
      return write('PATCH', `/api/topics/${segment(topicId)}`, body, owner);
    },
    routeMessage(
      messageId: string,
      body: WriteIdentity & { space_id: string; topic_id: string | null; space_secondary: string | null },
      owner: RequestOwner,
    ) {
      if (
        !isRevision(body.expected_revision) ||
        !isId(body.space_id) ||
        (body.topic_id !== null && !isId(body.topic_id)) ||
        (body.space_secondary !== null && (!isId(body.space_secondary) || body.space_secondary === body.space_id))
      )
        throw new DraftApiError('VALIDATION_ERROR');
      return write('POST', `/api/messages/${segment(messageId)}/route`, body, owner);
    },
  };
}
