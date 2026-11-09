import './components-demo.css';

export default function ComponentNotice({ page }: { page: string }) {
  return (
    <section className="component-demo-notice stack small" aria-label="组件模拟说明">
      <p className="small-text">
        组件演示使用合成资料，仅用于查看界面与交互。操作只在本页生效，不会读取或修改你的记录，也不会调用模型。
      </p>
      <nav className="row wrap" aria-label="组件预览页面">
        {[
          ['chart', '命盘'],
          ['tarot', '塔罗'],
          ['today', '今日'],
        ].map(([value, label]) => (
          <a
            className="text-link quiet-link"
            href={`#/${value}`}
            key={value}
            aria-current={page === value ? 'page' : undefined}>
            {label}
          </a>
        ))}
        <a className="text-link quiet-link" href={`/#/${page}`}>
          返回真实页面
        </a>
      </nav>
    </section>
  );
}
