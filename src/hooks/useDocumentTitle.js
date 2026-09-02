import { useEffect } from 'react';

/** Set the browser tab title per page. */
export function useDocumentTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · NEXUS` : 'NEXUS · Investigation Intelligence';
  }, [title]);
}
