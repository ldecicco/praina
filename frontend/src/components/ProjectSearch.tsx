import { useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBook,
  faCalendarDay,
  faFlask,
  faSearch,
  faBolt,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type { SearchResultItem } from "../types";

const SCOPE_OPTIONS = [
  { value: "", label: "All sources" },
  { value: "documents", label: "Documents" },
  { value: "meetings", label: "Meetings" },
  { value: "research", label: "Research" },
];

function compactText(value: string, maxLength: number): string {
  const cleaned = value.replace(/\s+/g, " ").trim();
  if (cleaned.length <= maxLength) return cleaned;
  return `${cleaned.slice(0, maxLength)}...`;
}

function sourceLabel(sourceType: string): string {
  if (sourceType === "document") return "Document";
  if (sourceType === "meeting") return "Meeting";
  if (sourceType === "research_note") return "Research Note";
  if (sourceType === "research_reference") return "Research Reference";
  if (sourceType === "research_discussion") return "Discussion";
  if (sourceType === "research_finding") return "Finding";
  if (sourceType === "research_decision") return "Decision";
  if (sourceType === "research_action_item") return "Action Item";
  if (sourceType === "research_hypothesis") return "Hypothesis";
  if (sourceType === "research_method") return "Method";
  if (sourceType === "research_literature_review") return "Lit Review";
  if (sourceType === "research_conclusion") return "Conclusion";
  if (sourceType === "research_observation") return "Observation";
  return sourceType;
}

function sourceIcon(sourceType: string) {
  if (sourceType === "document") return faBook;
  if (sourceType === "meeting") return faCalendarDay;
  return faFlask;
}

export function ProjectSearch({ selectedProjectId, onNavigate }: { selectedProjectId: string; onNavigate?: (view: string, entityId?: string) => void }) {
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState("");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [total, setTotal] = useState(0);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState("");
  const [backfilling, setBackfilling] = useState(false);
  const [backfillResult, setBackfillResult] = useState<{ documents: number; meetings: number; research?: number } | null>(null);

  async function handleSearch() {
    const q = query.trim();
    if (!q || !selectedProjectId) return;
    setSearching(true);
    setError("");
    setBackfillResult(null);
    try {
      const res = await api.searchProject(selectedProjectId, q, {
        scope: scope || undefined,
        top_k: 20,
      });
      setResults(res.results);
      setTotal(res.total);
      setSearched(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setSearching(false);
    }
  }

  async function handleBackfill() {
    if (!selectedProjectId) return;
    setBackfilling(true);
    setError("");
    try {
      const res = await api.embedBackfill(selectedProjectId);
      setBackfillResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backfill failed.");
    } finally {
      setBackfilling(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") void handleSearch();
  }

  function handleResultOpen(result: SearchResultItem) {
    if (!onNavigate) return;
    if (result.source_type === "document") {
      onNavigate("documents", result.source_key);
      return;
    }
    if (result.source_type === "meeting") {
      onNavigate("meetings", result.source_id);
      return;
    }
    if (result.source_key.startsWith("research:meeting_discussion:")) {
      onNavigate("meetings", result.source_id);
      return;
    }
    onNavigate("research", result.source_id);
  }

  if (!selectedProjectId) {
    return <p className="empty-message">Select a project to search.</p>;
  }

  return (
    <>
      {error ? <p className="error">{error}</p> : null}

      {/* Summary bar */}
      <div className="setup-summary-bar">
        <div className="setup-summary-stats">
          {searched ? (
            <>
              <span>{total} result{total !== 1 ? "s" : ""}</span>
              <span className="setup-summary-sep" />
              <span className="muted-small">Hybrid TF-IDF + vector search</span>
            </>
          ) : (
            <span>Search documents, meetings, and research</span>
          )}
        </div>
        <button
          type="button"
          className="ghost meetings-new-btn"
          onClick={() => void handleBackfill()}
          disabled={backfilling}
          title="Generate embeddings for all un-embedded chunks"
        >
          <FontAwesomeIcon icon={faBolt} /> {backfilling ? "Embedding..." : "Build Index"}
        </button>
      </div>

      {backfillResult ? (
        <p className="muted-small">
          Embedded {backfillResult.documents} document chunks + {backfillResult.meetings} meeting chunks
          {(backfillResult.research || 0) > 0 ? ` + ${backfillResult.research} research chunks.` : "."}
        </p>
      ) : null}

      {/* Search toolbar */}
      <div className="meetings-toolbar">
        <div className="meetings-filter-group search-input-group">
          <div className="search-bar">
            <FontAwesomeIcon icon={faSearch} className="search-bar-icon" />
            <input
              className="search-bar-input"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search across documents, meetings, and research..."
              autoFocus
            />
          </div>
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            {SCOPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <button
            type="button"
            className="meetings-new-btn"
            onClick={() => void handleSearch()}
            disabled={searching || !query.trim()}
          >
            {searching ? "Searching..." : "Search"}
          </button>
        </div>
      </div>

      {/* Results */}
      {searching ? <p className="muted-small">Searching...</p> : null}

      {!searching && searched && results.length === 0 ? (
        <p className="muted-small empty-message">No results found.</p>
      ) : null}

      {!searching && results.length > 0 ? (
        <div className="simple-table-wrap">
          <table className="simple-table compact-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Title</th>
                <th>Excerpt</th>
                <th className="col-70">Score</th>
              </tr>
            </thead>
            <tbody>
              {results.map((result) => (
                <tr key={`${result.source_id}-${result.chunk_index}`}>
                  <td>
                    <div className="search-source-cell">
                      <span className="meetings-source-icon">
                        <FontAwesomeIcon icon={sourceIcon(result.source_type)} />
                      </span>
                      <div className="search-source-meta">
                        <span className="chip small">{sourceLabel(result.source_type)}</span>
                        <span className="muted-small">Chunk {result.chunk_index + 1}</span>
                      </div>
                    </div>
                  </td>
                  <td>
                    <button type="button" className="search-result-link" onClick={() => handleResultOpen(result)}>
                      <strong>{compactText(result.title, 140)}</strong>
                    </button>
                    {result.version > 1 ? <span className="muted-small search-inline-meta">Version {result.version}</span> : null}
                  </td>
                  <td>
                    <p className="search-result-snippet">{compactText(result.content, 320)}</p>
                  </td>
                  <td>
                    <span className="search-result-score">{(result.score * 100).toFixed(0)}%</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}
