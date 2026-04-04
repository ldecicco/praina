import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBookOpen,
  faCalendarDay,
  faCompress,
  faFileArrowUp,
  faFileLines,
  faHashtag,
  faMagnifyingGlass,
  faMinus,
  faPause,
  faPlay,
  faPlus,
  faShareNodes,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import type {
  ResearchNote,
  ResearchReference,
  ResearchStudyFile,
  ResearchStudyIteration,
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

type StudyGraphNodeType = "log" | "tag" | "reference" | "file" | "iteration";

type StudyGraphNode = {
  id: string;
  label: string;
  nodeType: StudyGraphNodeType;
  refId: string | null;
  meta: string | null;
};

type StudyGraphEdge = {
  id: string;
  source: string;
  target: string;
  edgeType: "tagged" | "cites" | "attaches" | "links_to" | "in_iteration";
};

function formatReferenceLabel(reference: ResearchReference): string {
  const author = reference.authors[0]?.split(" ").slice(-1)[0] || "Ref";
  return reference.year ? `${author} ${reference.year}` : author;
}

function uniqueById<T extends { id: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

function buildStudyGraphData({
  notes,
  references,
  files,
  iterations,
  includeTags,
  includeReferences,
  includeFiles,
  includeIterations,
}: {
  notes: ResearchNote[];
  references: ResearchReference[];
  files: ResearchStudyFile[];
  iterations: ResearchStudyIteration[];
  includeTags: boolean;
  includeReferences: boolean;
  includeFiles: boolean;
  includeIterations: boolean;
}) {
  const nodes: StudyGraphNode[] = [];
  const edges: StudyGraphEdge[] = [];
  const nodeIds = new Set<string>();
  const edgeIds = new Set<string>();

  const referenceMap = new Map(references.map((item) => [item.id, item]));
  const fileMap = new Map(files.map((item) => [item.id, item]));
  const iterationByNoteId = new Map<string, ResearchStudyIteration[]>();

  iterations.forEach((iteration) => {
    iteration.note_ids.forEach((noteId) => {
      const bucket = iterationByNoteId.get(noteId) || [];
      bucket.push(iteration);
      iterationByNoteId.set(noteId, bucket);
    });
  });

  function addNode(node: StudyGraphNode) {
    if (nodeIds.has(node.id)) return;
    nodeIds.add(node.id);
    nodes.push(node);
  }

  function addEdge(edge: StudyGraphEdge) {
    if (edge.source === edge.target || edgeIds.has(edge.id)) return;
    edgeIds.add(edge.id);
    edges.push(edge);
  }

  notes.forEach((note) => {
    addNode({
      id: `log:${note.id}`,
      label: note.title || "Untitled Log",
      nodeType: "log",
      refId: note.id,
      meta: note.created_at,
    });

    if (includeTags) {
      note.tags.forEach((tag) => {
        addNode({ id: `tag:${tag.toLowerCase()}`, label: `#${tag}`, nodeType: "tag", refId: tag, meta: null });
        addEdge({ id: `edge:tag:${note.id}:${tag.toLowerCase()}`, source: `log:${note.id}`, target: `tag:${tag.toLowerCase()}`, edgeType: "tagged" });
      });
    }

    if (includeReferences) {
      note.linked_reference_ids.forEach((referenceId) => {
        const reference = referenceMap.get(referenceId);
        if (!reference) return;
        addNode({ id: `reference:${reference.id}`, label: reference.title || formatReferenceLabel(reference), nodeType: "reference", refId: reference.id, meta: reference.year ? String(reference.year) : null });
        addEdge({ id: `edge:ref:${note.id}:${reference.id}`, source: `log:${note.id}`, target: `reference:${reference.id}`, edgeType: "cites" });
      });
    }

    if (includeFiles) {
      note.linked_file_ids.forEach((fileId) => {
        const file = fileMap.get(fileId);
        if (!file) return;
        addNode({ id: `file:${file.id}`, label: file.original_filename, nodeType: "file", refId: file.id, meta: file.mime_type || null });
        addEdge({ id: `edge:file:${note.id}:${file.id}`, source: `log:${note.id}`, target: `file:${file.id}`, edgeType: "attaches" });
      });
    }

    uniqueById(note.linked_note_ids.map((id) => ({ id }))).forEach(({ id: linkedNoteId }) => {
      addEdge({ id: `edge:note:${note.id}:${linkedNoteId}`, source: `log:${note.id}`, target: `log:${linkedNoteId}`, edgeType: "links_to" });
    });

    if (includeIterations) {
      (iterationByNoteId.get(note.id) || []).forEach((iteration) => {
        addNode({ id: `iteration:${iteration.id}`, label: iteration.title || "Iteration", nodeType: "iteration", refId: iteration.id, meta: iteration.end_date || iteration.start_date || null });
        addEdge({ id: `edge:iteration:${note.id}:${iteration.id}`, source: `log:${note.id}`, target: `iteration:${iteration.id}`, edgeType: "in_iteration" });
      });
    }
  });

  return { nodes, edges };
}

export function StudyGraphModal({
  notes,
  references,
  files,
  iterations,
  initialNodeId,
  onClose,
  onOpenNote,
  onOpenReference,
  onOpenFile,
  onOpenIteration,
}: {
  notes: ResearchNote[];
  references: ResearchReference[];
  files: ResearchStudyFile[];
  iterations: ResearchStudyIteration[];
  initialNodeId?: string | null;
  onClose: () => void;
  onOpenNote: (noteId: string) => void;
  onOpenReference: (referenceId: string) => void;
  onOpenFile: (fileId: string) => void;
  onOpenIteration: (iterationId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [includeTags, setIncludeTags] = useState(true);
  const [includeReferences, setIncludeReferences] = useState(true);
  const [includeFiles, setIncludeFiles] = useState(true);
  const [includeIterations, setIncludeIterations] = useState(true);
  const [focusMode, setFocusMode] = useState(Boolean(initialNodeId));
  const [searchOpen, setSearchOpen] = useState(false);
  const [physicsRunning, setPhysicsRunning] = useState(true);
  const physicsRef = useRef<{ running: boolean; raf: number | null }>({ running: true, raf: null });

  const graphData = useMemo(
    () =>
      buildStudyGraphData({
        notes,
        references,
        files,
        iterations,
        includeTags,
        includeReferences,
        includeFiles,
        includeIterations,
      }),
    [notes, references, files, iterations, includeTags, includeReferences, includeFiles, includeIterations],
  );

  const selectedNode = useMemo(
    () => graphData.nodes.find((item) => item.id === selectedNodeId) ?? null,
    [graphData.nodes, selectedNodeId],
  );

  const relatedNodes = useMemo(() => {
    if (!selectedNode) return [];
    const neighbors = new Map<string, { node: StudyGraphNode; edgeType: string }>();
    graphData.edges.forEach((edge) => {
      if (edge.source !== selectedNode.id && edge.target !== selectedNode.id) return;
      const neighborId = edge.source === selectedNode.id ? edge.target : edge.source;
      const neighbor = graphData.nodes.find((item) => item.id === neighborId);
      if (!neighbor || neighbors.has(neighborId)) return;
      neighbors.set(neighborId, { node: neighbor, edgeType: edge.edgeType });
    });
    return Array.from(neighbors.values()).sort((a, b) => a.node.label.localeCompare(b.node.label));
  }, [graphData.edges, graphData.nodes, selectedNode]);

  const searchItems = useMemo(
    () => graphData.nodes.map((n) => ({ id: n.id, label: n.label, icon: faShareNodes, section: n.nodeType })),
    [graphData.nodes],
  );

  const nodeCounts = useMemo(() => {
    const c: Record<string, number> = {};
    graphData.nodes.forEach((n) => { c[n.nodeType] = (c[n.nodeType] || 0) + 1; });
    return c;
  }, [graphData.nodes]);

  useEffect(() => {
    const preferredId = initialNodeId && graphData.nodes.some((item) => item.id === initialNodeId)
      ? initialNodeId
      : graphData.nodes[0]?.id ?? null;
    setSelectedNodeId(preferredId);
    setFocusMode(Boolean(preferredId));
  }, [graphData.nodes, initialNodeId]);

  // Ctrl+F search
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

  // Build graph
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
    const success = cssVar("--success", "#2ec97a");
    const warning = cssVar("--warning", "#e5a913");
    const textBright = cssVar("--text-bright", "#ededf0");
    const surface = cssVar("--surface-3", "#323236");

    graphData.nodes.forEach((node) => {
      const pos = positions.get(node.id) ?? { x: 0, y: 0 };
      const color =
        node.nodeType === "log"
          ? rgbaFromHex(brand, 0.84)
          : node.nodeType === "tag"
            ? rgbaFromHex(warning, 0.8)
            : node.nodeType === "reference"
              ? rgbaFromHex("#5da2ff", 0.78)
              : node.nodeType === "file"
                ? rgbaFromHex("#ce82ff", 0.76)
                : rgbaFromHex(success, 0.82);
      const baseSize =
        node.nodeType === "log" ? 9 : node.nodeType === "iteration" ? 7 : node.nodeType === "reference" ? 7 : 5;
      graph.addNode(node.id, {
        label: node.label,
        x: pos.x,
        y: pos.y,
        size: baseSize,
        color,
        type: "circle",
        nodeType: node.nodeType,
      });
    });

    graphData.edges.forEach((edge) => {
      if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) return;
      const color =
        edge.edgeType === "tagged"
          ? rgbaFromHex(warning, 0.22)
          : edge.edgeType === "cites"
            ? "rgba(93,162,255,0.18)"
            : edge.edgeType === "attaches"
              ? "rgba(206,130,255,0.18)"
              : edge.edgeType === "in_iteration"
                ? rgbaFromHex(success, 0.18)
                : rgbaFromHex(textBright, 0.12);
      graph.addEdgeWithKey(edge.id, edge.source, edge.target, {
        size: edge.edgeType === "links_to" ? 1.4 : 1.9,
        color,
        edgeType: edge.edgeType,
      });
    });

    // Degree-based sizing
    graph.forEachNode((nodeId) => {
      const baseSize = graph.getNodeAttribute(nodeId, "size") as number;
      graph.setNodeAttribute(nodeId, "size", computeNodeSize(graph, nodeId, baseSize));
    });

    if (graph.order > 1) {
      forceAtlas2.assign(graph, {
        iterations: 50,
        settings: { gravity: 1, scalingRatio: 9, slowDown: 1.8 },
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

    renderer.on("clickNode", ({ node }) => setSelectedNodeId(node));
    renderer.on("clickStage", () => setSelectedNodeId(null));
    renderer.on("doubleClickNode", ({ node }) => {
      const nd = graphData.nodes.find((n) => n.id === node);
      if (nd?.refId) {
        if (nd.nodeType === "log") onOpenNote(nd.refId);
        if (nd.nodeType === "reference") onOpenReference(nd.refId);
        if (nd.nodeType === "file") onOpenFile(nd.refId);
        if (nd.nodeType === "iteration") onOpenIteration(nd.refId);
      }
    });

    const cleanupHover = setupHoverTracking(renderer, setHoveredNodeId);
    const cleanupDrag = setupNodeDrag(renderer, graph, new Set());
    renderer.getCamera().animatedReset({ duration: 250 });

    // Live physics
    const fa2Settings = { gravity: 1, scalingRatio: 9, slowDown: 8 };
    physicsRef.current.running = true;
    setPhysicsRunning(true);

    function physicsStep() {
      if (!physicsRef.current.running || !graphRef.current) return;
      forceAtlas2.assign(graphRef.current, { iterations: 1, settings: fa2Settings });
      physicsRef.current.raf = requestAnimationFrame(physicsStep);
    }
    physicsRef.current.raf = requestAnimationFrame(physicsStep);

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

  // Apply reducers
  useEffect(() => {
    const renderer = rendererRef.current;
    const graph = graphRef.current;
    if (!renderer || !graph) return;
    applyGraphReducers(renderer, graph, { hoveredNode: hoveredNodeId, selectedNode: selectedNodeId, focusMode });
  }, [hoveredNodeId, selectedNodeId, focusMode]);

  const handleSelectNode = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId);
    const renderer = rendererRef.current;
    const graph = graphRef.current;
    if (renderer && graph) zoomToNode(renderer, graph, nodeId);
  }, []);

  function togglePhysics() {
    const next = !physicsRef.current.running;
    physicsRef.current.running = next;
    setPhysicsRunning(next);
    if (next && graphRef.current) {
      function step() {
        if (!physicsRef.current.running || !graphRef.current) return;
        forceAtlas2.assign(graphRef.current, { iterations: 1, settings: { gravity: 1, scalingRatio: 9, slowDown: 8 } });
        physicsRef.current.raf = requestAnimationFrame(step);
      }
      physicsRef.current.raf = requestAnimationFrame(step);
    }
  }

  function openSelectedNode() {
    if (!selectedNode?.refId) return;
    if (selectedNode.nodeType === "log") onOpenNote(selectedNode.refId);
    if (selectedNode.nodeType === "reference") onOpenReference(selectedNode.refId);
    if (selectedNode.nodeType === "file") onOpenFile(selectedNode.refId);
    if (selectedNode.nodeType === "iteration") onOpenIteration(selectedNode.refId);
  }

  return (
    <>
    <div className="modal-overlay" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="modal-card bibliography-graph-modal study-graph-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <h3>Graph</h3>
          <div className="modal-head-actions">
            <span className="chip small">{nodeCounts.log || 0} logs</span>
            <button type="button" className="ghost docs-action-btn" onClick={onClose} title="Close">
              <FontAwesomeIcon icon={faXmark} />
            </button>
          </div>
        </div>

        <div className="bibliography-graph-toolbar">
          <button type="button" className={`bib-toggle-btn${includeTags ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeTags((v) => !v)}>
            Tags{nodeCounts.tag ? ` (${nodeCounts.tag})` : ""}
          </button>
          <button type="button" className={`bib-toggle-btn${includeReferences ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeReferences((v) => !v)}>
            References{nodeCounts.reference ? ` (${nodeCounts.reference})` : ""}
          </button>
          <button type="button" className={`bib-toggle-btn${includeFiles ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeFiles((v) => !v)}>
            Files{nodeCounts.file ? ` (${nodeCounts.file})` : ""}
          </button>
          <button type="button" className={`bib-toggle-btn${includeIterations ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeIterations((v) => !v)}>
            Iterations{nodeCounts.iteration ? ` (${nodeCounts.iteration})` : ""}
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
            {graphData.nodes.length === 0 ? <div className="bibliography-graph-state">No graph nodes.</div> : null}
            <div className={`bibliography-graph-canvas${graphData.nodes.length === 0 ? " hidden" : ""}`} ref={containerRef} />

            <div className="graph-zoom-controls">
              <button type="button" className="graph-zoom-btn" onClick={() => rendererRef.current && zoomIn(rendererRef.current)} title="Zoom in"><FontAwesomeIcon icon={faPlus} /></button>
              <button type="button" className="graph-zoom-btn" onClick={() => rendererRef.current && zoomOut(rendererRef.current)} title="Zoom out"><FontAwesomeIcon icon={faMinus} /></button>
              <button type="button" className="graph-zoom-btn" onClick={() => rendererRef.current && zoomFit(rendererRef.current)} title="Fit to view"><FontAwesomeIcon icon={faCompress} /></button>
              <button type="button" className={`graph-zoom-btn${physicsRunning ? " graph-zoom-btn-active" : ""}`} onClick={togglePhysics} title={physicsRunning ? "Pause physics" : "Resume physics"}>
                <FontAwesomeIcon icon={physicsRunning ? faPause : faPlay} />
              </button>
            </div>

            <div className="graph-legend">
              {nodeCounts.log ? <span className="graph-legend-item"><span className="graph-legend-dot" style={{ background: cssVar("--brand", "#3AAFA8") }} />Logs</span> : null}
              {nodeCounts.tag ? <span className="graph-legend-item"><span className="graph-legend-dot" style={{ background: cssVar("--warning", "#e5a913") }} />Tags</span> : null}
              {nodeCounts.reference ? <span className="graph-legend-item"><span className="graph-legend-dot" style={{ background: "#5da2ff" }} />References</span> : null}
              {nodeCounts.file ? <span className="graph-legend-item"><span className="graph-legend-dot" style={{ background: "#ce82ff" }} />Files</span> : null}
              {nodeCounts.iteration ? <span className="graph-legend-item"><span className="graph-legend-dot" style={{ background: cssVar("--success", "#2ec97a") }} />Iterations</span> : null}
            </div>
          </div>

          <aside className="bibliography-graph-detail">
            {selectedNode ? (
              <>
                <div className="bibliography-graph-node-head">
                  <span className={`chip small bibliography-graph-node-kind bibliography-graph-node-kind-${selectedNode.nodeType}`}>
                    {selectedNode.nodeType}
                  </span>
                  <strong>{selectedNode.label}</strong>
                </div>

                {selectedNode.meta ? (
                  <div className="bibliography-graph-node-meta">
                    <span>{selectedNode.meta}</span>
                  </div>
                ) : null}

                {selectedNode.nodeType !== "tag" ? (
                  <div className="bibliography-graph-actions">
                    <button type="button" className="meetings-new-btn" onClick={openSelectedNode}>
                      <FontAwesomeIcon
                        icon={
                          selectedNode.nodeType === "log"
                            ? faFileLines
                            : selectedNode.nodeType === "reference"
                              ? faBookOpen
                              : selectedNode.nodeType === "file"
                                ? faFileArrowUp
                                : faCalendarDay
                        }
                      />{" "}
                      Open
                    </button>
                  </div>
                ) : null}

                <div className="bibliography-graph-links">
                  <strong>Linked</strong>
                  {relatedNodes.length > 0 ? (
                    <div className="bibliography-graph-link-list">
                      {relatedNodes.map(({ node, edgeType }) => (
                        <button
                          key={`${selectedNode.id}-${node.id}`}
                          type="button"
                          className="ghost bibliography-graph-link-item"
                          onClick={() => handleSelectNode(node.id)}
                        >
                          <span className="bibliography-graph-link-title">{node.label}</span>
                          <span className="bibliography-graph-link-meta">
                            <small>{edgeType.replace(/_/g, " ")}</small>
                          </span>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="bibliography-graph-empty">
                      <FontAwesomeIcon icon={selectedNode.nodeType === "tag" ? faHashtag : faShareNodes} />
                      <span>No linked nodes.</span>
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
          onSelect={(id) => { setSearchOpen(false); setFocusMode(true); handleSelectNode(id); }}
          onClose={() => setSearchOpen(false)}
          aggressiveKeyboardCapture
        />
      ) : null}
    </>
  );
}
