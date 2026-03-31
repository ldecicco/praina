import { useEffect, useRef, useState } from "react";
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
}

export function CommandPalette({ items, onSelect, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = query
    ? items.filter(
        (item) =>
          item.label.toLowerCase().includes(query.toLowerCase()) ||
          (item.section?.toLowerCase().includes(query.toLowerCase()) ?? false)
      )
    : items;

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

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
      <div className="cmd-palette" onKeyDown={handleKeyDown}>
        <div className="cmd-palette-input-row">
          <FontAwesomeIcon icon={faSearch} className="cmd-palette-search-icon" />
          <input
            ref={inputRef}
            type="text"
            className="cmd-palette-input"
            placeholder="Go to..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <kbd className="cmd-palette-kbd">esc</kbd>
        </div>
        <div className="cmd-palette-list">
          {filtered.length === 0 ? (
            <div className="cmd-palette-empty">No matches</div>
          ) : (
            filtered.map((item, index) => (
              <button
                key={item.id}
                type="button"
                className={`cmd-palette-item ${index === activeIndex ? "active" : ""}`}
                onMouseEnter={() => setActiveIndex(index)}
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
