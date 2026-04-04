import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBookOpen,
  faCompress,
  faFileArrowUp,
  faMagnifyingGlass,
  faMinus,
  faPlay,
  faPause,
  faPlus,
  faShareNodes,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type {
  BibliographyGraph,
  BibliographyGraphNode,
  BibliographyReference,
} from "../types";
import {
  cssVar,
  rgbaFromHex,
  drawGraphLabel,
  buildInitialPositions,
  computeNodeSize,
  setupHoverTracking,
  setupNodeDrag,
  applyGraphReducers,
  zoomToNode,
  zoomIn,
  zoomOut,
  zoomFit,
} from "../lib/graphUtils";
import { CommandPalette } from "./CommandPalette";

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
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [includeAuthors, setIncludeAuthors] = useState(true);
  const [includeConcepts, setIncludeConcepts] = useState(true);
  const [includeTags, setIncludeTags] = useState(false);
  const [includeSemantic, setIncludeSemantic] = useState(true);
  const [includeBibliographyCollections, setIncludeBibliographyCollections] = useState(true);
  const [includeResearchLinks, setIncludeResearchLinks] = useState(true);
  const [includeTeachingLinks, setIncludeTeachingLinks] = useState(true);
  const [focusMode, setFocusMode] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [physicsRunning, setPhysicsRunning] = useState(true);
  const physicsRef = useRef<{ running: boolean; raf: number | null }>({ running: true, raf: null });

  const referenceMap = useMemo(
    () => new Map(references.map((item) => [item.id, item])),
    [references],
  );

  const selectedNode = useMemo(
    () => graphData.nodes.find((item) => item.id === selectedNodeId) ?? null,
    [graphData.nodes, selectedNodeId],
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

  // Search items for CommandPalette
  const searchItems = useMemo(
    () =>
      graphData.nodes.map((n) => ({
        id: n.id,
        label: n.label,
        icon: faShareNodes,
        section: n.node_type,
      })),
    [graphData.nodes],
  );

  // Ctrl+F to open search
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "f") {
        e.preventDefault();
        e.stopImmediatePropagation();
        setSearchOpen(true);
      }
    }
    window.addEventListener("keydown", handleKey, true);
    return () => window.removeEventListener("keydown", handleKey, true);
  }, []);

  // Load graph data
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
        setSelectedNodeId((current) =>
          current && response.nodes.some((item) => item.id === current)
            ? current
            : response.nodes[0]?.id ?? null,
        );
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to build graph.");
        }
      } finally {
        if (!cancelled) setLoading(false);
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

  // Build and render graph
  useEffect(() => {
    if (!containerRef.current) return;
    rendererRef.current?.kill();
    rendererRef.current = null;
    graphRef.current = null;
    if (physicsRef.current.raf) cancelAnimationFrame(physicsRef.current.raf);
    physicsRef.current.raf = null;

    if (graphData.nodes.length === 0) return;

    const graph = new Graph();
    const positions = buildInitialPositions(graphData.nodes.map((item) => item.id));
    const brand = cssVar("--brand", "#3AAFA8");
    const textBright = cssVar("--text-bright", "#ededf0");
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
                        : text;
      const baseSize =
        node.node_type === "paper"
          ? 10
          : node.node_type === "author"
            ? 5
            : node.node_type === "concept"
              ? 6
              : node.node_type === "research_project" || node.node_type === "teaching_project"
                ? 7
                : 5;
      graph.addNode(node.id, {
        label: node.label,
        x: pos.x,
        y: pos.y,
        size: baseSize,
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

    // Apply degree-based sizing after all edges are added
    graph.forEachNode((nodeId) => {
      const baseSize = graph.getNodeAttribute(nodeId, "size") as number;
      graph.setNodeAttribute(nodeId, "size", computeNodeSize(graph, nodeId, baseSize));
    });

    // Initial layout pass for starting positions
    if (graph.order > 1) {
      forceAtlas2.assign(graph, {
        iterations: 50,
        settings: {
          gravity: 1,
          scalingRatio: 9,
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
    renderer.on("clickStage", () => setSelectedNodeId(null));
    renderer.on("doubleClickNode", ({ node }) => {
      const nd = graphData.nodes.find((n) => n.id === node);
      if (nd?.ref_id) {
        const ref = referenceMap.get(nd.ref_id);
        if (ref) onOpenPaper(ref);
      }
    });

    // Setup interactions
    const cleanupHover = setupHoverTracking(renderer, setHoveredNodeId);
    const cleanupDrag = setupNodeDrag(renderer, graph, new Set());

    renderer.getCamera().animatedReset({ duration: 250 });

    // Live physics loop
    const fa2Settings = {
      gravity: 1,
      scalingRatio: 9,
      slowDown: 8,
    };
    physicsRef.current.running = true;
    setPhysicsRunning(true);

    function physicsStep() {
      if (!physicsRef.current.running || !graphRef.current) return;
      forceAtlas2.assign(graphRef.current, { iterations: 1, settings: fa2Settings });
      physicsRef.current.raf = requestAnimationFrame(physicsStep);
    }
    physicsRef.current.raf = requestAnimationFrame(physicsStep);

    // Auto-stop physics after a few seconds
    const autoStop = setTimeout(() => {
      physicsRef.current.running = false;
      setPhysicsRunning(false);
    }, 4000);

    return () => {
      clearTimeout(autoStop);
      if (physicsRef.current.raf) cancelAnimationFrame(physicsRef.current.raf);
      physicsRef.current.raf = null;
      cleanupHover();
      cleanupDrag();
      renderer.kill();
      rendererRef.current = null;
      graphRef.current = null;
    };
  }, [graphData]);

  // Apply reducers on hover/select/focus changes
  useEffect(() => {
    const renderer = rendererRef.current;
    const graph = graphRef.current;
    if (!renderer || !graph) return;
    applyGraphReducers(renderer, graph, {
      hoveredNode: hoveredNodeId,
      selectedNode: selectedNodeId,
      focusMode,
    });
  }, [hoveredNodeId, selectedNodeId, focusMode]);

  // Zoom to node on select (from sidebar clicks)
  const handleSelectNode = useCallback(
    (nodeId: string) => {
      setSelectedNodeId(nodeId);
      const renderer = rendererRef.current;
      const graph = graphRef.current;
      if (renderer && graph) zoomToNode(renderer, graph, nodeId);
    },
    [],
  );

  function togglePhysics() {
    const next = !physicsRef.current.running;
    physicsRef.current.running = next;
    setPhysicsRunning(next);
    if (next && graphRef.current) {
      function step() {
        if (!physicsRef.current.running || !graphRef.current) return;
        forceAtlas2.assign(graphRef.current, {
          iterations: 1,
          settings: { gravity: 1, scalingRatio: 9, slowDown: 8 },
        });
        physicsRef.current.raf = requestAnimationFrame(step);
      }
      physicsRef.current.raf = requestAnimationFrame(step);
    }
  }

  const selectedReference = selectedNode?.ref_id ? referenceMap.get(selectedNode.ref_id) ?? null : null;

  // Count nodes by type for toolbar labels
  const nodeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    graphData.nodes.forEach((n) => {
      counts[n.node_type] = (counts[n.node_type] || 0) + 1;
    });
    return counts;
  }, [graphData.nodes]);

  return (
    <>
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
          <button type="button" className={`bib-toggle-btn${includeAuthors ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeAuthors((v) => !v)}>
            Authors{nodeCounts.author ? ` (${nodeCounts.author})` : ""}
          </button>
          <button type="button" className={`bib-toggle-btn${includeConcepts ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeConcepts((v) => !v)}>
            Concepts{nodeCounts.concept ? ` (${nodeCounts.concept})` : ""}
          </button>
          <button type="button" className={`bib-toggle-btn${includeTags ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeTags((v) => !v)}>
            Tags{nodeCounts.tag ? ` (${nodeCounts.tag})` : ""}
          </button>
          <button type="button" className={`bib-toggle-btn${includeSemantic ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeSemantic((v) => !v)}>
            Semantic
          </button>
          <button type="button" className={`bib-toggle-btn${includeBibliographyCollections ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeBibliographyCollections((v) => !v)}>
            Collections
          </button>
          <button type="button" className={`bib-toggle-btn${includeResearchLinks ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeResearchLinks((v) => !v)}>
            Research
          </button>
          <button type="button" className={`bib-toggle-btn${includeTeachingLinks ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeTeachingLinks((v) => !v)}>
            Teaching
          </button>
          <span className="study-graph-toolbar-spacer" />
          <button type="button" className="ghost icon-only graph-toolbar-icon" onClick={() => setSearchOpen(true)} title="Search nodes (Ctrl+F)">
            <FontAwesomeIcon icon={faMagnifyingGlass} />
          </button>
          <button type="button" className={`bib-toggle-btn${!focusMode ? " bib-toggle-btn-active" : ""}`} onClick={() => setFocusMode(false)}>All</button>
          <button type="button" className={`bib-toggle-btn${focusMode ? " bib-toggle-btn-active" : ""}`} onClick={() => selectedNodeId && setFocusMode(true)} disabled={!selectedNodeId}>Focus</button>
        </div>

        <div className="bibliography-graph-shell">
          <div className="bibliography-graph-canvas-wrap">
            {loading ? <div className="bibliography-graph-state">Loading...</div> : null}
            {!loading && error ? <div className="bibliography-graph-state error">{error}</div> : null}
            {!loading && !error && graphData.nodes.length === 0 ? (
              <div className="bibliography-graph-state">No graph nodes.</div>
            ) : null}
            <div className={`bibliography-graph-canvas${loading || error || graphData.nodes.length === 0 ? " hidden" : ""}`} ref={containerRef} />

            {/* Zoom controls */}
            <div className="graph-zoom-controls">
              <button type="button" className="graph-zoom-btn" onClick={() => rendererRef.current && zoomIn(rendererRef.current)} title="Zoom in">
                <FontAwesomeIcon icon={faPlus} />
              </button>
              <button type="button" className="graph-zoom-btn" onClick={() => rendererRef.current && zoomOut(rendererRef.current)} title="Zoom out">
                <FontAwesomeIcon icon={faMinus} />
              </button>
              <button type="button" className="graph-zoom-btn" onClick={() => rendererRef.current && zoomFit(rendererRef.current)} title="Fit to view">
                <FontAwesomeIcon icon={faCompress} />
              </button>
              <button type="button" className={`graph-zoom-btn${physicsRunning ? " graph-zoom-btn-active" : ""}`} onClick={togglePhysics} title={physicsRunning ? "Pause physics" : "Resume physics"}>
                <FontAwesomeIcon icon={physicsRunning ? faPause : faPlay} />
              </button>
            </div>

            {/* Legend */}
            <div className="graph-legend">
              {nodeCounts.paper ? <span className="graph-legend-item"><span className="graph-legend-dot" style={{ background: cssVar("--brand", "#3AAFA8") }} />Papers</span> : null}
              {nodeCounts.author ? <span className="graph-legend-item"><span className="graph-legend-dot" style={{ background: cssVar("--text", "#b4b4bd") }} />Authors</span> : null}
              {nodeCounts.concept ? <span className="graph-legend-item"><span className="graph-legend-dot" style={{ background: "#59c7a7" }} />Concepts</span> : null}
              {nodeCounts.tag ? <span className="graph-legend-item"><span className="graph-legend-dot" style={{ background: cssVar("--warning", "#e5a913") }} />Tags</span> : null}
            </div>
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
                          onClick={() => handleSelectNode(node.id)}
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

      {searchOpen ? (
        <CommandPalette
          items={searchItems}
          onSelect={(id) => {
            setSearchOpen(false);
            setFocusMode(true);
            handleSelectNode(id);
          }}
          onClose={() => setSearchOpen(false)}
          aggressiveKeyboardCapture
        />
      ) : null}
    </>
  );
}
