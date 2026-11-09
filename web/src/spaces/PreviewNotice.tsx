import { Button, Tag } from '../components/ui/Controls';
import { useSpacesDemo } from './store';
import './common.css';

export default function PreviewNotice() {
  const reset = useSpacesDemo((state) => state.reset);
  const current = location.hash.split('?')[0];
  return (
    <section className="spaces-preview-note" aria-label="功能区模拟说明">
      <div className="row between wrap">
        <Tag>功能区预览 · 合成资料</Tag>
        <a className="text-link quiet-link" href={`${location.pathname}#/chat`}>
          返回真实对话
        </a>
      </div>
      <p className="small-text secondary-text">归区、应用和撤销只修改本地演示，刷新后重置。真实旧对话尚未整理。</p>
      <nav className="row wrap" aria-label="功能区预览页面">
        {[
          ['chat', '区与话题'],
          ['me', '分区记忆'],
          ['organize', '整理建议'],
          ['organize-review', '旧对话审阅'],
        ].map(([route, label]) => (
          <a
            key={route}
            className="button ghost"
            href={`#/${route}`}
            aria-current={current === `#/${route}` ? 'page' : undefined}>
            {label}
          </a>
        ))}
        <Button variant="ghost" onClick={reset}>
          重置演示
        </Button>
      </nav>
    </section>
  );
}
