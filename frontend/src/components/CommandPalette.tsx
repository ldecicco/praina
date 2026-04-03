import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import type { IconDefinition } from "@fortawesome/fontawesome-svg-core";
import { faSearch } from "@fortawesome/free-solid-svg-icons";

export interface CommandItem {
  id: string;
  label: string;
  icon: IconDefinition;
  section?: string;
}

interface Props {
  items: CommandItem[];
  onSelect: (id: string) => void;
  onClose: () => void;
  aggressiveKeyboardCapture?: boolean;
}

export function CommandPalette({ items, onSelect, onClose, aggressiveKeyboardCapture = false }: Props) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [pointerHoverEnabled, setPointerHoverEnabled] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const filtered = query
    ? items.filter(
        (item) =>
          item.label.toLowerCase().includes(query.toLowerCase()) ||
          (item.section?.toLowerCase().includes(query.toLowerCase()) ?? false)
      )
    : items;

  useLayoutEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useEffect(() => {
    setPointerHoverEnabled(false);
  }, []);

  useEffect(() => {
    const activeItem = itemRefs.current[activeIndex];
    activeItem?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, filtered.length]);

  function focusInput() {
    inputRef.current?.focus();
  }

  function appendToQuery(text: string) {
    setQuery((current) => current + text);
  }

  function handleKeyDownCapture(e: React.KeyboardEvent) {
    const target = e.target as HTMLElement | null;
    const targetTag = target?.tagName?.toLowerCase();
    const isTypingIntoInput =
      targetTag === "input" ||
      targetTag === "textarea" ||
      target?.isContentEditable;

    if (e.key === "Escape") return;

    if (!isTypingIntoInput) {
      if (e.key === "Backspace") {
        e.preventDefault();
        focusInput();
        setQuery((current) => current.slice(0, -1));
        return;
      }
      if (e.key === "Delete") {
        e.preventDefault();
        focusInput();
        setQuery("");
        return;
      }
      if (e.key === " " || (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey)) {
        e.preventDefault();
        focusInput();
        appendToQuery(e.key);
      }
    }
  }

  useEffect(() => {
    if (!aggressiveKeyboardCapture) return;

    function ensureInputFocus(select = false) {
      const input = inputRef.current;
      if (!input) return;
      input.focus();
      if (select) {
        input.select();
      } else {
        const end = input.value.length;
        try {
          input.setSelectionRange(end, end);
        } catch {
          /* noop */
        }
      }
    }

    const raf = requestAnimationFrame(() => ensureInputFocus(true));
    const timeout = window.setTimeout(() => ensureInputFocus(true), 40);

    function handleDocumentKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const targetTag = target?.tagName?.toLowerCase();
      const isTypingIntoInput =
        target === inputRef.current ||
        targetTag === "input" ||
        targetTag === "textarea" ||
        target?.isContentEditable;

      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }

      if (event.key === "ArrowDown") {
        event.preventDefault();
        event.stopPropagation();
        setActiveIndex((i) => (filtered.length > 0 ? (i + 1) % filtered.length : 0));
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        event.stopPropagation();
        setActiveIndex((i) => (filtered.length > 0 ? (i - 1 + filtered.length) % filtered.length : 0));
        return;
      }

      if (event.key === "Enter") {
        if (filtered.length === 0) return;
        if (target === inputRef.current || !isTypingIntoInput) {
          event.preventDefault();
          event.stopPropagation();
          onSelect(filtered[activeIndex].id);
        }
        return;
      }

      if (isTypingIntoInput && target === inputRef.current) {
        return;
      }

      if (event.key === "Backspace") {
        event.preventDefault();
        event.stopPropagation();
        ensureInputFocus(false);
        setQuery((current) => current.slice(0, -1));
        return;
      }

      if (event.key === "Delete") {
        event.preventDefault();
        event.stopPropagation();
        ensureInputFocus(false);
        setQuery("");
        return;
      }

      if (event.key === " " || (event.key.length === 1 && !event.metaKey && !event.ctrlKey && !event.altKey)) {
        event.preventDefault();
        event.stopPropagation();
        ensureInputFocus(false);
        setQuery((current) => current + event.key);
      }
    }

    document.addEventListener("keydown", handleDocumentKeyDown, true);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(timeout);
      document.removeEventListener("keydown", handleDocumentKeyDown, true);
    };
  }, [activeIndex, aggressiveKeyboardCapture, filtered, onClose, onSelect]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % filtered.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => (i - 1 + filtered.length) % filtered.length);
    } else if (e.key === "Enter" && filtered.length > 0) {
      e.preventDefault();
      onSelect(filtered[activeIndex].id);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  }

  return (
    <div className="cmd-palette-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="cmd-palette" onKeyDownCapture={handleKeyDownCapture} onKeyDown={handleKeyDown}>
        <div className="cmd-palette-input-row">
          <FontAwesomeIcon icon={faSearch} className="cmd-palette-search-icon" />
          <input
            ref={inputRef}
            type="text"
            className="cmd-palette-input"
            placeholder="Go to..."
            value={query}
            autoFocus
            onChange={(e) => setQuery(e.target.value)}
          />
          <kbd className="cmd-palette-kbd">esc</kbd>
        </div>
        <div
          className="cmd-palette-list"
          onMouseMove={() => {
            if (!pointerHoverEnabled) setPointerHoverEnabled(true);
          }}
        >
          {filtered.length === 0 ? (
            <div className="cmd-palette-empty">No matches</div>
          ) : (
            filtered.map((item, index) => (
              <button
                key={item.id}
                ref={(node) => {
                  itemRefs.current[index] = node;
                }}
                type="button"
                className={`cmd-palette-item ${index === activeIndex ? "active" : ""}`}
                onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => {
                  if (pointerHoverEnabled) setActiveIndex(index);
                }}
                onClick={() => onSelect(item.id)}
              >
                <FontAwesomeIcon icon={item.icon} className="cmd-palette-item-icon" />
                <span>{item.label}</span>
                {item.section ? <span className="cmd-palette-item-section">{item.section}</span> : null}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
