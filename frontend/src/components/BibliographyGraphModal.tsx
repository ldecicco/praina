import React, { useEffect, useMemo, useRef, useState } from "react";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBookOpen,
  faFileArrowUp,
  faShareNodes,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type {
  BibliographyGraph,
  BibliographyGraphNode,
  BibliographyReference,
} from "../types";

function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function buildInitialPositions(ids: string[]) {
  const total = Math.max(ids.length, 1);
  return new Map(
    ids.map((id, index) => {
      const angle = (Math.PI * 2 * index) / total;
      return [id, { x: Math.cos(angle) * 12, y: Math.sin(angle) * 12 }];
    })
  );
}

function rgbaFromHex(value: string, alpha: number): string {
  const normalized = value.trim();
  if (!normalized.startsWith("#")) {
    return `rgba(17, 17, 19, ${alpha})`;
  }
  const hex = normalized.slice(1);
  const full = hex.length === 3
    ? hex.split("").map((char) => `${char}${char}`).join("")
    : hex;
  const red = Number.parseInt(full.slice(0, 2), 16);
  const green = Number.parseInt(full.slice(2, 4), 16);
  const blue = Number.parseInt(full.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function drawRoundedRect(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number
) {
  const r = Math.min(radius, width / 2, height / 2);
  context.beginPath();
  context.moveTo(x + r, y);
  context.arcTo(x + width, y, x + width, y + height, r);
  context.arcTo(x + width, y + height, x, y + height, r);
  context.arcTo(x, y + height, x, y, r);
  context.arcTo(x, y, x + width, y, r);
  context.closePath();
}

function drawGraphLabel(
  context: CanvasRenderingContext2D,
  data: {
    label?: string | null;
    size?: number;
    color?: string;
    x?: number;
    y?: number;
  }
) {
  if (!data.label || typeof data.x !== "number" || typeof data.y !== "number") return;

  const bg = cssVar("--bg", "#111113");
  const lineStrong = cssVar("--line-strong", "rgba(255,255,255,0.12)");
  const textBright = cssVar("--text-bright", "#ededf0");
  const textSecondary = cssVar("--text-secondary", "#8e8e9a");
  const size = typeof data.size === "number" ? data.size : 10;
  const accent = data.color || cssVar("--brand", "#7c5cfc");
  const fontSize = Math.max(11, Math.round(size * 0.92));
  const padX = 8;
  const padY = 5;
  const radius = 7;

  context.font = `600 ${fontSize}px var(--font), sans-serif`;
  const metrics = context.measureText(data.label);
  const textWidth = metrics.width;
  const boxWidth = textWidth + padX * 2;
  const boxHeight = fontSize + padY * 2;
  const x = data.x + size + 8;
  const y = data.y - boxHeight / 2;

  context.save();
  context.shadowColor = rgbaFromHex(bg, 0.46);
  context.shadowBlur = 22;
  context.fillStyle = rgbaFromHex(bg, 0.84);
  drawRoundedRect(context, x, y, boxWidth, boxHeight, radius);
  context.fill();
  context.shadowBlur = 0;
  context.strokeStyle = rgbaFromHex(accent, 0.34);
  context.lineWidth = 1;
  drawRoundedRect(context, x, y, boxWidth, boxHeight, radius);
  context.stroke();

  context.fillStyle = textBright;
  context.textBaseline = "middle";
  context.fillText(data.label, x + padX, y + boxHeight / 2);

  context.fillStyle = textSecondary;
  context.beginPath();
  context.arc(x + 5, y + boxHeight / 2, 1.6, 0, Math.PI * 2);
  context.fill();
  context.restore();
}

export function BibliographyGraphModal({
  references,
  onClose,
  onOpenPaper,
  onOpenAttachment,
  openingAttachmentId,
}: {
  references: BibliographyReference[];
  onClose: () => void;
  onOpenPaper: (reference: BibliographyReference) => void;
  onOpenAttachment: (reference: BibliographyReference) => void;
  openingAttachmentId: string | null;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const [graphData, setGraphData] = useState<BibliographyGraph>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [includeAuthors, setIncludeAuthors] = useState(true);
  const [includeConcepts, setIncludeConcepts] = useState(true);
  const [includeTags, setIncludeTags] = useState(false);
  const [includeSemantic, setIncludeSemantic] = useState(true);
  const [includeBibliographyCollections, setIncludeBibliographyCollections] = useState(true);
  const [includeResearchLinks, setIncludeResearchLinks] = useState(true);
  const [includeTeachingLinks, setIncludeTeachingLinks] = useState(true);

  const referenceMap = useMemo(
    () => new Map(references.map((item) => [item.id, item])),
    [references]
  );

  const selectedNode = useMemo(
    () => graphData.nodes.find((item) => item.id === selectedNodeId) ?? null,
    [graphData.nodes, selectedNodeId]
  );

  const relatedNodes = useMemo(() => {
    if (!selectedNode) return [];
    const neighbors = new Map<string, { node: BibliographyGraphNode; edgeType: string; weight: number | null }>();
    for (const edge of graphData.edges) {
      if (edge.source !== selectedNode.id && edge.target !== selectedNode.id) continue;
      const neighborId = edge.source === selectedNode.id ? edge.target : edge.source;
      const neighbor = graphData.nodes.find((item) => item.id === neighborId);
      if (!neighbor) continue;
      const previous = neighbors.get(neighborId);
      if (!previous || (edge.weight ?? 0) > (previous.weight ?? 0)) {
        neighbors.set(neighborId, { node: neighbor, edgeType: edge.edge_type, weight: edge.weight });
      }
    }
    return Array.from(neighbors.values()).sort((a, b) => {
      if (a.node.node_type === "paper" && b.node.node_type !== "paper") return -1;
      if (a.node.node_type !== "paper" && b.node.node_type === "paper") return 1;
      return a.node.label.localeCompare(b.node.label);
    });
  }, [graphData.edges, graphData.nodes, selectedNode]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (references.length === 0) {
        setGraphData({ nodes: [], edges: [] });
        setSelectedNodeId(null);
        return;
      }
      setLoading(true);
      setError("");
      try {
        const response = await api.buildBibliographyGraph({
          reference_ids: references.map((item) => item.id),
          include_authors: includeAuthors,
          include_concepts: includeConcepts,
          include_tags: includeTags,
          include_semantic: includeSemantic,
          include_bibliography_collections: includeBibliographyCollections,
          include_research_links: includeResearchLinks,
          include_teaching_links: includeTeachingLinks,
        });
        if (cancelled) return;
        setGraphData(response);
        setSelectedNodeId((current) => current && response.nodes.some((item) => item.id === current)
          ? current
          : response.nodes[0]?.id ?? null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to build graph.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [
    references,
    includeAuthors,
    includeConcepts,
    includeTags,
    includeSemantic,
    includeBibliographyCollections,
    includeResearchLinks,
    includeTeachingLinks,
  ]);

  useEffect(() => {
    if (!containerRef.current) return;
    rendererRef.current?.kill();
    rendererRef.current = null;
    graphRef.current = null;

    if (graphData.nodes.length === 0) return;

    const graph = new Graph();
    const positions = buildInitialPositions(graphData.nodes.map((item) => item.id));
    const brand = cssVar("--brand", "#7c5cfc");
    const textBright = cssVar("--text-bright", "#ededf0");
    const textSecondary = cssVar("--text-secondary", "#8e8e9a");
    const text = cssVar("--text", "#b4b4bd");
    const warning = cssVar("--warning", "#e5a913");
    const success = cssVar("--success", "#2ec97a");
    const surface = cssVar("--surface-3", "#323236");
    const paperColor = rgbaFromHex(brand, 0.82);
    const authorColor = rgbaFromHex(text, 0.74);
    const conceptColor = rgbaFromHex("#59c7a7", 0.78);
    const tagColor = rgbaFromHex(warning, 0.8);
    const bibliographyCollectionColor = rgbaFromHex(brand, 0.66);
    const researchCollectionColor = rgbaFromHex(success, 0.78);
    const researchProjectColor = rgbaFromHex(success, 0.42);
    const teachingProjectColor = rgbaFromHex(warning, 0.62);

    for (const node of graphData.nodes) {
      const pos = positions.get(node.id) ?? { x: 0, y: 0 };
      const color =
        node.node_type === "paper"
          ? paperColor
          : node.node_type === "author"
            ? authorColor
            : node.node_type === "concept"
              ? conceptColor
            : node.node_type === "tag"
              ? tagColor
              : node.node_type === "bibliography_collection"
                ? bibliographyCollectionColor
                : node.node_type === "research_collection"
                  ? researchCollectionColor
                  : node.node_type === "research_project"
                    ? researchProjectColor
                    : node.node_type === "teaching_project"
                      ? teachingProjectColor
                      : textSecondary;
      const size =
        node.node_type === "paper"
          ? 14
          : node.node_type === "author"
            ? 8
            : node.node_type === "concept"
              ? 9
            : node.node_type === "research_project" || node.node_type === "teaching_project"
              ? 10
              : 7;
      graph.addNode(node.id, {
        label: node.label,
        x: pos.x,
        y: pos.y,
        size,
        color,
        type: "circle",
        nodeType: node.node_type,
      });
    }

    for (const edge of graphData.edges) {
      if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue;
      graph.addEdgeWithKey(edge.id, edge.source, edge.target, {
        size: edge.edge_type === "semantic" ? 1.4 : 1.8,
        color:
          edge.edge_type === "semantic"
            ? rgbaFromHex(brand, 0.2)
            : edge.edge_type === "written_by"
              ? rgbaFromHex(textBright, 0.12)
              : edge.edge_type === "mentions_concept"
                ? rgbaFromHex("#59c7a7", 0.22)
              : edge.edge_type === "linked_to_research_collection" || edge.edge_type === "contains_collection"
                ? rgbaFromHex(success, 0.18)
                : edge.edge_type === "used_in_teaching_project"
                  ? rgbaFromHex(warning, 0.2)
                  : rgbaFromHex(brand, 0.16),
        edgeType: edge.edge_type,
      });
    }

    if (graph.order > 1) {
      forceAtlas2.assign(graph, {
        iterations: 120,
        settings: {
          gravity: 1,
          scalingRatio: 9,
          strongGravityMode: false,
          slowDown: 1.8,
        },
      });
    }

    const renderer = new Sigma(graph, containerRef.current, {
      renderEdgeLabels: false,
      labelDensity: 0.08,
      labelGridCellSize: 80,
      labelRenderedSizeThreshold: 8,
      labelColor: { color: textBright },
      defaultDrawNodeLabel: drawGraphLabel,
      defaultDrawNodeHover: drawGraphLabel,
      defaultEdgeColor: "rgba(255,255,255,0.12)",
      defaultNodeColor: surface,
    });
    graphRef.current = graph;
    rendererRef.current = renderer;

    renderer.on("clickNode", ({ node }) => {
      setSelectedNodeId(node);
    });
    renderer.on("clickStage", () => {
      setSelectedNodeId(null);
    });
    renderer.getCamera().animatedReset({ duration: 250 });

    return () => {
      renderer.kill();
      rendererRef.current = null;
      graphRef.current = null;
    };
  }, [graphData]);

  useEffect(() => {
    const renderer = rendererRef.current;
    const graph = graphRef.current;
    if (!renderer || !graph) return;

    const muted = cssVar("--muted", "#6e6e7a");
    const neighborIds = new Set(
      selectedNodeId && graph.hasNode(selectedNodeId) ? graph.neighbors(selectedNodeId) : []
    );

    renderer.setSetting("nodeReducer", (node, data) => {
      if (!selectedNodeId) return data;
      if (node === selectedNodeId) {
        return {
          ...data,
          size: (typeof data.size === "number" ? data.size : 10) + 3,
          color: data.color,
          zIndex: 1,
        };
      }
      if (neighborIds.has(node)) {
        return {
          ...data,
          zIndex: 1,
        };
      }
      return {
        ...data,
        color: muted,
        label: "",
      };
    });

    renderer.setSetting("edgeReducer", (edge, data) => {
      if (!selectedNodeId) return data;
      const extremities = graph.extremities(edge);
      if (extremities.includes(selectedNodeId)) {
        return {
          ...data,
          hidden: false,
          size: (typeof data.size === "number" ? data.size : 1.2) + 0.5,
        };
      }
      return {
        ...data,
        hidden: true,
      };
    });

    renderer.refresh();
  }, [selectedNodeId]);

  const selectedReference = selectedNode?.ref_id ? referenceMap.get(selectedNode.ref_id) ?? null : null;

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="modal-card bibliography-graph-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <h3>Graph</h3>
          <div className="modal-head-actions">
            <span className="chip small">{references.length} papers</span>
            <button type="button" className="ghost docs-action-btn" onClick={onClose} title="Close">
              <FontAwesomeIcon icon={faXmark} />
            </button>
          </div>
        </div>

        <div className="bibliography-graph-toolbar">
          <button
            type="button"
            className={`bib-toggle-btn${includeAuthors ? " bib-toggle-btn-active" : ""}`}
            onClick={() => setIncludeAuthors((value) => !value)}
          >
            Authors
          </button>
          <button
            type="button"
            className={`bib-toggle-btn${includeConcepts ? " bib-toggle-btn-active" : ""}`}
            onClick={() => setIncludeConcepts((value) => !value)}
          >
            Concepts
          </button>
          <button
            type="button"
            className={`bib-toggle-btn${includeTags ? " bib-toggle-btn-active" : ""}`}
            onClick={() => setIncludeTags((value) => !value)}
          >
            Tags
          </button>
          <button
            type="button"
            className={`bib-toggle-btn${includeSemantic ? " bib-toggle-btn-active" : ""}`}
            onClick={() => setIncludeSemantic((value) => !value)}
          >
            Semantic
          </button>
          <button
            type="button"
            className={`bib-toggle-btn${includeBibliographyCollections ? " bib-toggle-btn-active" : ""}`}
            onClick={() => setIncludeBibliographyCollections((value) => !value)}
          >
            Collections
          </button>
          <button
            type="button"
            className={`bib-toggle-btn${includeResearchLinks ? " bib-toggle-btn-active" : ""}`}
            onClick={() => setIncludeResearchLinks((value) => !value)}
          >
            Research
          </button>
          <button
            type="button"
            className={`bib-toggle-btn${includeTeachingLinks ? " bib-toggle-btn-active" : ""}`}
            onClick={() => setIncludeTeachingLinks((value) => !value)}
          >
            Teaching
          </button>
        </div>

        <div className="bibliography-graph-shell">
          <div className="bibliography-graph-canvas-wrap">
            {loading ? <div className="bibliography-graph-state">Loading...</div> : null}
            {!loading && error ? <div className="bibliography-graph-state error">{error}</div> : null}
            {!loading && !error && graphData.nodes.length === 0 ? (
              <div className="bibliography-graph-state">No graph nodes.</div>
            ) : null}
            <div className={`bibliography-graph-canvas${loading || error || graphData.nodes.length === 0 ? " hidden" : ""}`} ref={containerRef} />
          </div>

          <aside className="bibliography-graph-detail">
            {selectedNode ? (
              <>
                <div className="bibliography-graph-node-head">
                  <span className={`chip small bibliography-graph-node-kind bibliography-graph-node-kind-${selectedNode.node_type}`}>
                    {selectedNode.node_type}
                  </span>
                  <strong>{selectedNode.label}</strong>
                </div>

                {selectedReference ? (
                  <>
                    <div className="bibliography-graph-node-meta">
                      <span>{selectedReference.authors.join(", ") || "No authors"}</span>
                      <span>{selectedReference.year || "No year"}</span>
                      {selectedReference.venue ? <span>{selectedReference.venue}</span> : null}
                    </div>
                    <div className="bibliography-graph-actions">
                      <button type="button" className="meetings-new-btn" onClick={() => onOpenPaper(selectedReference)}>
                        <FontAwesomeIcon icon={faBookOpen} /> Open Paper
                      </button>
                      {selectedReference.attachment_url ? (
                        <button
                          type="button"
                          className="ghost icon-text-button small"
                          disabled={openingAttachmentId === selectedReference.id}
                          onClick={() => onOpenAttachment(selectedReference)}
                        >
                          <FontAwesomeIcon icon={faFileArrowUp} spin={openingAttachmentId === selectedReference.id} /> PDF
                        </button>
                      ) : null}
                    </div>
                    {selectedReference.tags.length > 0 ? (
                      <div className="research-chip-group">
                        {selectedReference.tags.map((tag) => (
                          <span key={`${selectedReference.id}-${tag}`} className="chip small">{tag}</span>
                        ))}
                      </div>
                    ) : null}
                    {selectedReference.concepts.length > 0 ? (
                      <div className="research-chip-group">
                        {selectedReference.concepts.map((concept) => (
                          <span key={`${selectedReference.id}-${concept}`} className="chip small">{concept}</span>
                        ))}
                      </div>
                    ) : null}
                  </>
                ) : null}

                <div className="bibliography-graph-links">
                  <strong>Connections</strong>
                  {relatedNodes.length === 0 ? (
                    <p className="muted-small">No visible connections.</p>
                  ) : (
                    <div className="bibliography-graph-link-list">
                      {relatedNodes.map(({ node, edgeType, weight }) => (
                        <button
                          key={`${selectedNode.id}-${node.id}`}
                          type="button"
                          className="bibliography-graph-link-item"
                          onClick={() => setSelectedNodeId(node.id)}
                        >
                          <span className="bibliography-graph-link-title">{node.label}</span>
                          <span className="bibliography-graph-link-meta">
                            <span className="chip small">{edgeType.replace(/_/g, " ")}</span>
                            {weight !== null ? <small>{Math.round(weight * 100)}%</small> : null}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="bibliography-graph-empty">
                <FontAwesomeIcon icon={faShareNodes} />
                <span>Select a node.</span>
              </div>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
