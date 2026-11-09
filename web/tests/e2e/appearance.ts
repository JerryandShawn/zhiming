// Count actual painted content in the viewport, including clipping by the chat scroller.
// Brand/navigation/chart semantic colors are the exclusions explicitly approved in 14 I.6.
export function cinnabarUsages() {
  const probe = document.createElement('span');
  document.body.append(probe);
  const colors = ['--cinnabar', '--cinnabar-hover', '--cinnabar-wash'].map((token) => {
    probe.style.color = `var(${token})`;
    return getComputedStyle(probe).color;
  });
  probe.remove();
  const painted: Element[] = [];
  const modal = document.querySelector('[aria-modal="true"]');
  const root = modal ?? document.querySelector('main');
  for (const element of Array.from(root?.querySelectorAll('*') ?? [])) {
    if (element.closest('.seal, .tabbar, .rail, .day-master, .element-bar, .fire, .fire-bg, .astro-wheel')) continue;
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    if (!rect.width || !rect.height || style.visibility === 'hidden' || Number(style.opacity) === 0) continue;
    let top = Math.max(0, rect.top),
      bottom = Math.min(innerHeight, rect.bottom);
    let left = Math.max(0, rect.left),
      right = Math.min(innerWidth, rect.right);
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
      const parentStyle = getComputedStyle(parent);
      if (parentStyle.display === 'none' || parentStyle.visibility === 'hidden' || Number(parentStyle.opacity) === 0) {
        bottom = top;
        break;
      }
      const bounds = parent.getBoundingClientRect();
      if (/(auto|scroll|hidden|clip)/.test(parentStyle.overflowY)) {
        top = Math.max(top, bounds.top);
        bottom = Math.min(bottom, bounds.bottom);
      }
      if (/(auto|scroll|hidden|clip)/.test(parentStyle.overflowX)) {
        left = Math.max(left, bounds.left);
        right = Math.min(right, bounds.right);
      }
    }
    if (bottom <= top || right <= left) continue;
    const ownText = Array.from(element.childNodes).some((node) => node.nodeType === 3 && node.textContent?.trim());
    const ink = ownText && colors.includes(style.color);
    const fill = colors.includes(style.backgroundColor);
    const border = ['borderTop', 'borderRight', 'borderBottom', 'borderLeft', 'outline'].some(
      (side) =>
        colors.includes(
          style.getPropertyValue(side.replace(/[A-Z]/g, (value) => `-${value.toLowerCase()}`) + '-color'),
        ) &&
        parseFloat(style.getPropertyValue(side.replace(/[A-Z]/g, (value) => `-${value.toLowerCase()}`) + '-width')) > 0,
    );
    if ((ink || fill || border) && !painted.some((parent) => parent.contains(element))) painted.push(element);
  }
  return painted.map((element) => ({
    className: element.getAttribute('class') ?? '',
    text: element.textContent?.trim().slice(0, 45),
  }));
}
