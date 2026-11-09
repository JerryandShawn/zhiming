export function publicAssetPath(path: string): string {
  if (!/^\/data\/[A-Za-z0-9._/-]+$/.test(path) || path.includes('..') || path.includes('//') || path.includes('\\'))
    throw new Error('公开资源路径无效');
  return new URL(path.slice(1), document.baseURI).pathname;
}
