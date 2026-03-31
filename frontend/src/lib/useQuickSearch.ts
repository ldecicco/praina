import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Ctrl+F / Cmd+F quick search hook.
 * Opens a floating search bar that pipes into a list filter.
 */
export function useQuickSearch(onQueryChange: (query: string) => void) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "f") {
        e.preventDefault();
        setOpen(true);
        setQuery("");
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (open) onQueryChange(query);
  }, [query, open]);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    onQueryChange("");
  }, [onQueryChange]);

  return { open, query, setQuery, inputRef, close };
}
