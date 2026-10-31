import { afterEach, describe, expect, it } from 'vitest';
import { publicAssetPath } from '../src/publicAsset';

afterEach(() => history.replaceState({}, '', '/'));

describe('public asset URLs under a shared static base', () => {
  it.each([
    ['/', '/data/study/course.json'],
    ['/v4/', '/v4/data/study/course.json'],
    ['/v4/index.html', '/v4/data/study/course.json'],
  ])('resolves %s without changing the API origin or path', (base, expected) => {
    history.replaceState({}, '', base);
    expect(publicAssetPath('/data/study/course.json')).toBe(expected);
  });

  it.each(['/api/state', '/data/../private', '/data//double', '/data\\escape', '/data/tools/a?x=1'])(
    'rejects %s',
    (path) => {
      expect(() => publicAssetPath(path)).toThrow('公开资源路径无效');
    },
  );
});
