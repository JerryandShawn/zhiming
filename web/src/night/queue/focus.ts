/** Do not steal focus if the user moved on while a receipt was pending. */
export function restoreComposerFocus(previous: Element | null) {
  requestAnimationFrame(() => {
    if (previous && !previous.isConnected && document.activeElement === document.body)
      document.querySelector<HTMLTextAreaElement>('#composer-input')?.focus({ preventScroll: true });
  });
}
