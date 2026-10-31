import { useRef, useState } from 'react';

/** Composer versions remain independent of stream and queue lifetimes. */
export function useConversationDraft() {
  const [draft, setDraftState] = useState('');
  const [images, setImagesState] = useState<string[]>([]);
  const current = useRef({ text: '', images: [] as string[], textRevision: 0, imagesRevision: 0 });
  function setDraft(text: string) {
    current.current = { ...current.current, text, textRevision: current.current.textRevision + 1 };
    setDraftState(text);
  }
  function setImages(next: string[]) {
    current.current = { ...current.current, images: [...next], imagesRevision: current.current.imagesRevision + 1 };
    setImagesState([...next]);
  }
  function capture() {
    return { ...current.current, images: [...current.current.images] };
  }
  function clearSubmitted(input: ReturnType<typeof capture>, includeImages = true) {
    if (input.textRevision === current.current.textRevision) setDraft('');
    if (includeImages && input.imagesRevision === current.current.imagesRevision) setImages([]);
  }
  return { draft, images, setDraft, setImages, capture, clearSubmitted };
}
