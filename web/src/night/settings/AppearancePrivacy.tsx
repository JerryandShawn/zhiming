import { EyeOff, ShieldCheck } from 'lucide-react';
import { Segmented } from '../../components/ui/Controls';
import { useUi, type Theme } from '../../state';

export function AppearancePrivacy() {
  const theme = useUi((state) => state.theme),
    setTheme = useUi((state) => state.setTheme);
  return (
    <>
      <section className="setting-group" aria-label="外观">
        <h2>外观</h2>
        <Segmented<Theme>
          label="外观主题"
          value={theme}
          onChange={setTheme}
          options={[
            { value: 'system', label: '跟随系统' },
            { value: 'light', label: '宣纸' },
            { value: 'dark', label: '夜墨' },
          ]}
        />
      </section>
      <section className="setting-group" aria-label="隐私">
        <h2>隐私</h2>
        <p className="row">
          <EyeOff className="icon" aria-hidden="true" />
          无痕对话
        </p>
        <p className="meta">无痕对话不会进入长期记忆。请从对话页开启，退出后清空这一段。</p>
        <a className="row-link" href="#/chat">
          前往对话页
        </a>
        <a className="row-link" href="#/me?section=memory">
          让明镜忘掉某段时间
        </a>
        <p className="meta">
          进入记忆列表后，选择要删除的条目或整段原话。只删条目会保留原话；删除整段来源会连带清除由它整理出的内容。已经发到飞书的消息无法撤回。
        </p>
        <p className="meta row">
          <ShieldCheck className="icon small" aria-hidden="true" />
          你的资料，由你决定。
        </p>
      </section>
    </>
  );
}
