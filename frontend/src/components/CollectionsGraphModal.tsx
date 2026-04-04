import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBookOpen,
  faCompress,
  faExpand,
  faFileLines,
  faHashtag,
  faImage,
  faMagnifyingGlass,
  faMinus,
  faPause,
  faPlay,
  faPlus,
  faShareNodes,
  faThumbtack,
  faUser,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import type { CollectionGraph } from "../types";
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
  savePinnedPositions,
  restorePinnedPositions,
  exportGraphAsPng,
} from "../lib/graphUtils";
import { CommandPalette } from "./CommandPalette";

type MinimapNode = {
  id: string;
  x: number;
  y: number;
  nodeType: string;
};

function isEditableTarget(target: EventTarget | null) {
  const element = target as HTMLElement | null;
  if (!element) return false;
  const tag = element.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || element.isContentEditable;
}

function cycleNeighbor(graph: Graph, selectedNodeId: string | null, step: 1 | -1) {
  if (!selectedNodeId || !graph.hasNode(selectedNodeId)) return null;
  const neighbors = graph.neighbors(selectedNodeId);
  if (neighbors.length === 0) return null;
  const sorted = [...neighbors].sort((left, right) => {
    const leftLabel = String(graph.getNodeAttribute(left, "label") || left);
    const rightLabel = String(graph.getNodeAttribute(right, "label") || right);
    return leftLabel.localeCompare(rightLabel);
  });
  return step > 0 ? sorted[0] : sorted[sorted.length - 1];
}

export function CollectionsGraphModal({
  graphData,
  onClose,
  onOpenStudy,
  onOpenLog,
}: {
  graphData: CollectionGraph;
  onClose: () => void;
  onOpenStudy: (studyId: string) => void;
  onOpenLog: (logId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [includeLogs, setIncludeLogs] = useState(true);
  const [includeUsers, setIncludeUsers] = useState(true);
  const [includeTags, setIncludeTags] = useState(true);
  const [includeReferences, setIncludeReferences] = useState(true);
  const [focusMode, setFocusMode] = useState(false);
  const [focusDepth, setFocusDepth] = useState(1);
  const [searchOpen, setSearchOpen] = useState(false);
  const [physicsRunning, setPhysicsRunning] = useState(true);
  const [fullScreen, setFullScreen] = useState(false);
  const [pinnedNodeCount, setPinnedNodeCount] = useState(0);
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null);
  const [cameraRatio, setCameraRatio] = useState(1);
  const [minimapNodes, setMinimapNodes] = useState<MinimapNode[]>([]);
  const physicsRef = useRef<{ running: boolean; raf: number | null }>({ running: true, raf: null });
  const pinnedNodesRef = useRef<Set<string>>(new Set());

  const filteredGraph = useMemo(() => {
    const allowedNodeIds = new Set(
      graphData.nodes
        .filter((node) => {
          if (node.node_type === "log") return includeLogs;
          if (node.node_type === "user") return includeUsers;
          if (node.node_type === "tag") return includeTags;
          if (node.node_type === "reference") return includeReferences;
          return true;
        })
        .map((node) => node.id),
    );
    return {
      nodes: graphData.nodes.filter((node) => allowedNodeIds.has(node.id)),
      edges: graphData.edges.filter((edge) => allowedNodeIds.has(edge.source) && allowedNodeIds.has(edge.target)),
    };
  }, [graphData, includeLogs, includeReferences, includeTags, includeUsers]);

  const selectedNode = useMemo(
    () => filteredGraph.nodes.find((item) => item.id === selectedNodeId) ?? null,
    [filteredGraph.nodes, selectedNodeId],
  );

  const relatedNodes = useMemo(() => {
    if (!selectedNode) return [];
    const neighbors = new Map<string, { node: CollectionGraph["nodes"][number]; edgeType: string }>();
    filteredGraph.edges.forEach((edge) => {
      if (edge.source !== selectedNode.id && edge.target !== selectedNode.id) return;
      const neighborId = edge.source === selectedNode.id ? edge.target : edge.source;
      const neighbor = filteredGraph.nodes.find((item) => item.id === neighborId);
      if (!neighbor || neighbors.has(neighborId)) return;
      neighbors.set(neighborId, { node: neighbor, edgeType: edge.edge_type });
    });
    return Array.from(neighbors.values()).sort((a, b) => a.node.label.localeCompare(b.node.label));
  }, [filteredGraph.edges, filteredGraph.nodes, selectedNode]);

  const searchItems = useMemo(
    () => filteredGraph.nodes.map((n) => ({ id: n.id, label: n.label, icon: faShareNodes, section: n.node_type })),
    [filteredGraph.nodes],
  );

  const nodeCounts = useMemo(() => {
    const c: Record<string, number> = {};
    filteredGraph.nodes.forEach((n) => { c[n.node_type] = (c[n.node_type] || 0) + 1; });
    return c;
  }, [filteredGraph.nodes]);

  useEffect(() => {
    setSelectedNodeId(filteredGraph.nodes[0]?.id ?? null);
  }, [filteredGraph.nodes]);

  useEffect(() => {
    pinnedNodesRef.current = new Set(
      Array.from(pinnedNodesRef.current).filter((nodeId) => filteredGraph.nodes.some((node) => node.id === nodeId)),
    );
    setPinnedNodeCount(pinnedNodesRef.current.size);
  }, [filteredGraph.nodes]);

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

    if (filteredGraph.nodes.length === 0) return;

    const graph = new Graph({ multi: true });
    const positions = buildInitialPositions(filteredGraph.nodes.map((item) => item.id));
    const brand = cssVar("--brand", "#3AAFA8");
    const warning = cssVar("--warning", "#D4943A");
    const textBright = cssVar("--text-bright", "#ededf0");
    const surface = cssVar("--surface-3", "#323236");

    filteredGraph.nodes.forEach((node) => {
      const pos = positions.get(node.id) ?? { x: 0, y: 0 };
      const color =
        node.node_type === "study"
          ? rgbaFromHex(brand, 0.84)
          : node.node_type === "log"
            ? rgbaFromHex("#7d84ff", 0.8)
            : node.node_type === "user"
              ? rgbaFromHex("#f28c6f", 0.84)
            : node.node_type === "tag"
              ? rgbaFromHex(warning, 0.8)
              : rgbaFromHex("#5da2ff", 0.8);
      const baseSize =
        node.node_type === "study" ? 10 : node.node_type === "log" ? 6 : node.node_type === "reference" ? 7 : node.node_type === "user" ? 6 : 5;
      graph.addNode(node.id, {
        label: node.label,
        x: pos.x,
        y: pos.y,
        size: baseSize,
        color,
        type: "circle",
      });
    });

    filteredGraph.edges.forEach((edge) => {
      graph.addEdgeWithKey(edge.id, edge.source, edge.target, {
        size: 1.8,
        edgeType: edge.edge_type,
        color:
          edge.edge_type === "shares_reference" || edge.edge_type === "cites_reference"
            ? "rgba(93,162,255,0.18)"
            : edge.edge_type === "authored_log"
              ? "rgba(242,140,111,0.24)"
              : edge.edge_type === "mentioned_in_log"
                ? "rgba(242,140,111,0.16)"
                : edge.edge_type === "assigned_action"
                  ? "rgba(212,148,58,0.24)"
            : edge.edge_type === "links_log"
              ? "rgba(125,132,255,0.22)"
              : edge.edge_type === "contains_log"
                ? "rgba(58,175,168,0.18)"
                : rgbaFromHex(warning, 0.22),
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
      renderEdgeLabels: true,
      enableEdgeEvents: true,
      labelDensity: 0.08,
      labelGridCellSize: 80,
      labelRenderedSizeThreshold: 8,
      edgeLabelSize: 11,
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
    renderer.on("enterEdge", ({ edge }) => setHoveredEdgeId(edge));
    renderer.on("leaveEdge", () => setHoveredEdgeId(null));
    renderer.on("doubleClickNode", ({ node }) => {
      const nd = filteredGraph.nodes.find((n) => n.id === node);
      if (nd?.ref_id) {
        if (nd.node_type === "study") onOpenStudy(nd.ref_id);
        else if (nd.node_type === "log") onOpenLog(nd.ref_id);
      }
    });

    function syncViewState() {
      const currentRatio = renderer.getCamera().ratio;
      setCameraRatio(currentRatio);
      const positions: MinimapNode[] = [];
      graph.forEachNode((nodeId, attrs) => {
        positions.push({
          id: nodeId,
          x: Number(attrs.x) || 0,
          y: Number(attrs.y) || 0,
          nodeType: String(attrs.nodeType || "study"),
        });
      });
      setMinimapNodes(positions);
    }
    renderer.on("afterRender", syncViewState);
    renderer.getCamera().on("updated", syncViewState);

    const cleanupHover = setupHoverTracking(renderer, setHoveredNodeId);
    const cleanupDrag = setupNodeDrag(renderer, graph, pinnedNodesRef.current, setPinnedNodeCount);
    renderer.getCamera().animatedReset({ duration: 250 });
    syncViewState();

    // Live physics
    const fa2Settings = { gravity: 1, scalingRatio: 9, slowDown: 8 };
    physicsRef.current.running = true;
    setPhysicsRunning(true);

    function physicsStep() {
      if (!physicsRef.current.running || !graphRef.current) return;
      const savedPinnedPositions = savePinnedPositions(graphRef.current, pinnedNodesRef.current);
      forceAtlas2.assign(graphRef.current, { iterations: 1, settings: fa2Settings });
      restorePinnedPositions(graphRef.current, pinnedNodesRef.current, savedPinnedPositions);
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
      renderer.removeAllListeners("enterEdge");
      renderer.removeAllListeners("leaveEdge");
      renderer.removeAllListeners("afterRender");
      renderer.getCamera().removeAllListeners("updated");
      renderer.kill();
      rendererRef.current = null;
      graphRef.current = null;
    };
  }, [filteredGraph]);

  // Apply reducers
  useEffect(() => {
    const renderer = rendererRef.current;
    const graph = graphRef.current;
    if (!renderer || !graph) return;
    const threshold = cameraRatio > 1.25 ? 11 : cameraRatio > 0.7 ? 8 : 4;
    renderer.setSetting("labelRenderedSizeThreshold", threshold);
    applyGraphReducers(renderer, graph, {
      hoveredNode: hoveredNodeId,
      selectedNode: selectedNodeId,
      focusMode,
      focusDepth,
      hoveredEdge: hoveredEdgeId,
      cameraRatio,
    });
  }, [cameraRatio, hoveredEdgeId, hoveredNodeId, selectedNodeId, focusDepth, focusMode]);

  const handleSelectNode = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId);
    const renderer = rendererRef.current;
    const graph = graphRef.current;
    if (renderer && graph) zoomToNode(renderer, graph, nodeId);
  }, []);

  useEffect(() => {
    function handleGraphKeys(event: KeyboardEvent) {
      if (searchOpen || isEditableTarget(event.target)) return;
      const graph = graphRef.current;
      if (!graph) return;
      if (event.key === "Tab" && event.shiftKey) {
        event.preventDefault();
        const next = cycleNeighbor(graph, selectedNodeId, -1);
        if (next) handleSelectNode(next);
        return;
      }
      if (event.key === "ArrowRight" || event.key === "ArrowDown" || event.key === "Tab") {
        event.preventDefault();
        const next = cycleNeighbor(graph, selectedNodeId, 1);
        if (next) handleSelectNode(next);
        return;
      }
      if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
        event.preventDefault();
        const next = cycleNeighbor(graph, selectedNodeId, -1);
        if (next) handleSelectNode(next);
        return;
      }
      if (event.key === "Enter" && selectedNode) {
        event.preventDefault();
        if (selectedNode.node_type === "study" && selectedNode.ref_id) onOpenStudy(selectedNode.ref_id);
        if (selectedNode.node_type === "log" && selectedNode.ref_id) onOpenLog(selectedNode.ref_id);
      }
    }
    window.addEventListener("keydown", handleGraphKeys, true);
    return () => window.removeEventListener("keydown", handleGraphKeys, true);
  }, [handleSelectNode, onOpenLog, onOpenStudy, searchOpen, selectedNode, selectedNodeId]);

  function togglePhysics() {
    const next = !physicsRef.current.running;
    physicsRef.current.running = next;
    setPhysicsRunning(next);
    if (next && graphRef.current) {
      function step() {
        if (!physicsRef.current.running || !graphRef.current) return;
        const savedPinnedPositions = savePinnedPositions(graphRef.current, pinnedNodesRef.current);
        forceAtlas2.assign(graphRef.current, { iterations: 1, settings: { gravity: 1, scalingRatio: 9, slowDown: 8 } });
        restorePinnedPositions(graphRef.current, pinnedNodesRef.current, savedPinnedPositions);
        physicsRef.current.raf = requestAnimationFrame(step);
      }
      physicsRef.current.raf = requestAnimationFrame(step);
    }
  }

  function handleResetPins() {
    pinnedNodesRef.current.clear();
    setPinnedNodeCount(0);
  }

  return (
    <>
    <div className="modal-overlay" role="dialog" aria-modal="true" onClick={onClose}>
      <div className={`modal-card bibliography-graph-modal study-graph-modal${fullScreen ? " is-fullscreen" : ""}`} onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <h3>Graph</h3>
          <div className="modal-head-actions">
            <span className="chip small">{nodeCounts.study || 0} studies</span>
            <span className="chip small">{nodeCounts.log || 0} logs</span>
            <span className="chip small">{nodeCounts.user || 0} users</span>
            {pinnedNodeCount > 0 ? <span className="chip small">{pinnedNodeCount} pinned</span> : null}
            <button type="button" className="ghost docs-action-btn" onClick={onClose} title="Close">
              <FontAwesomeIcon icon={faXmark} />
            </button>
          </div>
        </div>

        <div className="bibliography-graph-toolbar">
          <button type="button" className={`bib-toggle-btn${includeLogs ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeLogs((v) => !v)}>
            Logs{nodeCounts.log ? ` (${nodeCounts.log})` : ""}
          </button>
          <button type="button" className={`bib-toggle-btn${includeUsers ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeUsers((v) => !v)}>
            Users{nodeCounts.user ? ` (${nodeCounts.user})` : ""}
          </button>
          <button type="button" className={`bib-toggle-btn${includeTags ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeTags((v) => !v)}>
            Tags{nodeCounts.tag ? ` (${nodeCounts.tag})` : ""}
          </button>
          <button type="button" className={`bib-toggle-btn${includeReferences ? " bib-toggle-btn-active" : ""}`} onClick={() => setIncludeReferences((v) => !v)}>
            References{nodeCounts.reference ? ` (${nodeCounts.reference})` : ""}
          </button>
          <span className="study-graph-toolbar-spacer" />
          <button type="button" className="ghost icon-only graph-toolbar-icon" onClick={() => setSearchOpen(true)} title="Search nodes (Ctrl+F)">
            <FontAwesomeIcon icon={faMagnifyingGlass} />
          </button>
          <button type="button" className={`bib-toggle-btn${!focusMode ? " bib-toggle-btn-active" : ""}`} onClick={() => setFocusMode(false)}>All</button>
          <button type="button" className={`bib-toggle-btn${focusMode ? " bib-toggle-btn-active" : ""}`} onClick={() => selectedNodeId && setFocusMode(true)} disabled={!selectedNodeId}>Focus</button>
          {focusMode ? (
            <div className="graph-depth-control">
              <span>Depth</span>
              <input
                type="range"
                min={1}
                max={3}
                step={1}
                value={focusDepth}
                onChange={(event) => setFocusDepth(Number(event.target.value))}
              />
              <strong>{focusDepth}</strong>
            </div>
          ) : null}
          <button type="button" className="ghost icon-only graph-toolbar-icon" onClick={() => rendererRef.current && exportGraphAsPng(rendererRef.current)} title="Export image">
            <FontAwesomeIcon icon={faImage} />
          </button>
          <button type="button" className="ghost icon-only graph-toolbar-icon" onClick={() => setFullScreen((value) => !value)} title={fullScreen ? "Exit full screen" : "Full screen"}>
            <FontAwesomeIcon icon={fullScreen ? faCompress : faExpand} />
          </button>
        </div>

        <div className="bibliography-graph-shell">
          <div className="bibliography-graph-canvas-wrap">
            {filteredGraph.nodes.length === 0 ? <div className="bibliography-graph-state">No shared graph nodes.</div> : null}
            <div className={`bibliography-graph-canvas${filteredGraph.nodes.length === 0 ? " hidden" : ""}`} ref={containerRef} />

            <div className="graph-zoom-controls">
              <button type="button" className="graph-zoom-btn" onClick={() => rendererRef.current && zoomIn(rendererRef.current)} title="Zoom in"><FontAwesomeIcon icon={faPlus} /></button>
              <button type="button" className="graph-zoom-btn" onClick={() => rendererRef.current && zoomOut(rendererRef.current)} title="Zoom out"><FontAwesomeIcon icon={faMinus} /></button>
              <button type="button" className="graph-zoom-btn" onClick={() => rendererRef.current && zoomFit(rendererRef.current)} title="Fit to view"><FontAwesomeIcon icon={faCompress} /></button>
              <button type="button" className={`graph-zoom-btn${physicsRunning ? " graph-zoom-btn-active" : ""}`} onClick={togglePhysics} title={physicsRunning ? "Pause physics" : "Resume physics"}>
                <FontAwesomeIcon icon={physicsRunning ? faPause : faPlay} />
              </button>
              <button type="button" className={`graph-zoom-btn${pinnedNodeCount > 0 ? " graph-zoom-btn-active" : ""}`} onClick={handleResetPins} title="Clear pinned nodes" disabled={pinnedNodeCount === 0}>
                <FontAwesomeIcon icon={faThumbtack} />
              </button>
            </div>

            <div className="graph-legend">
              {nodeCounts.study ? <span className="graph-legend-item"><span className="graph-legend-shape shape-circle" style={{ background: cssVar("--brand", "#3AAFA8") }} />Studies</span> : null}
              {nodeCounts.log ? <span className="graph-legend-item"><span className="graph-legend-shape shape-square" style={{ background: "#7d84ff" }} />Logs</span> : null}
              {nodeCounts.user ? <span className="graph-legend-item"><span className="graph-legend-shape shape-circle" style={{ background: "#f28c6f" }} />Users</span> : null}
              {nodeCounts.tag ? <span className="graph-legend-item"><span className="graph-legend-shape shape-diamond" style={{ background: cssVar("--warning", "#D4943A") }} />Tags</span> : null}
              {nodeCounts.reference ? <span className="graph-legend-item"><span className="graph-legend-shape shape-square" style={{ background: "#5da2ff" }} />References</span> : null}
            </div>

            {minimapNodes.length > 0 ? (
              <div className="graph-minimap">
                <svg viewBox="0 0 100 100" className="graph-minimap-svg" aria-hidden="true">
                  {(() => {
                    const xs = minimapNodes.map((node) => node.x);
                    const ys = minimapNodes.map((node) => node.y);
                    const minX = Math.min(...xs);
                    const maxX = Math.max(...xs);
                    const minY = Math.min(...ys);
                    const maxY = Math.max(...ys);
                    const scaleX = maxX === minX ? () => 50 : (value: number) => 8 + ((value - minX) / (maxX - minX)) * 84;
                    const scaleY = maxY === minY ? () => 50 : (value: number) => 8 + ((value - minY) / (maxY - minY)) * 84;
                    return minimapNodes.map((node) => {
                      const cx = scaleX(node.x);
                      const cy = scaleY(node.y);
                      const isSelected = node.id === selectedNodeId;
                      const fill =
                        node.nodeType === "study"
                          ? cssVar("--brand", "#3AAFA8")
                          : node.nodeType === "user"
                            ? "#f28c6f"
                          : node.nodeType === "tag"
                            ? cssVar("--warning", "#D4943A")
                            : node.nodeType === "log"
                              ? "#7d84ff"
                              : "#5da2ff";
                      if (node.nodeType === "tag") {
                        return (
                          <rect
                            key={`minimap-${node.id}`}
                            x={cx - 2.5}
                            y={cy - 2.5}
                            width={5}
                            height={5}
                            transform={`rotate(45 ${cx} ${cy})`}
                            fill={fill}
                            opacity={isSelected ? 1 : 0.78}
                          />
                        );
                      }
                      if (node.nodeType === "log" || node.nodeType === "reference") {
                        return (
                          <rect
                            key={`minimap-${node.id}`}
                            x={cx - 2.4}
                            y={cy - 2.4}
                            width={4.8}
                            height={4.8}
                            rx={1}
                            fill={fill}
                            opacity={isSelected ? 1 : 0.78}
                          />
                        );
                      }
                      if (node.nodeType === "user") {
                        return (
                          <circle
                            key={`minimap-${node.id}`}
                            cx={cx}
                            cy={cy}
                            r={2.2}
                            fill={fill}
                            opacity={isSelected ? 1 : 0.82}
                            stroke={isSelected ? "rgba(255,255,255,0.8)" : "none"}
                            strokeWidth={isSelected ? 0.8 : 0}
                          />
                        );
                      }
                      return <circle key={`minimap-${node.id}`} cx={cx} cy={cy} r={2.5} fill={fill} opacity={isSelected ? 1 : 0.78} />;
                    });
                  })()}
                </svg>
              </div>
            ) : null}
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
                {selectedNode.meta ? (
                  <div className="bibliography-graph-node-meta">
                    <span>{selectedNode.meta}</span>
                  </div>
                ) : null}
                {selectedNode.node_type === "study" && selectedNode.ref_id ? (
                  <div className="bibliography-graph-actions">
                    <button type="button" className="meetings-new-btn" onClick={() => onOpenStudy(selectedNode.ref_id!)}>
                      <FontAwesomeIcon icon={faBookOpen} /> Open
                    </button>
                  </div>
                ) : null}
                {selectedNode.node_type === "log" && selectedNode.ref_id ? (
                  <div className="bibliography-graph-actions">
                    <button type="button" className="meetings-new-btn" onClick={() => onOpenLog(selectedNode.ref_id!)}>
                      <FontAwesomeIcon icon={faFileLines} /> Open
                    </button>
                  </div>
                ) : null}
                {selectedNode.node_type === "user" ? (
                  <div className="bibliography-graph-actions">
                    <button type="button" className="ghost docs-action-btn" disabled>
                      <FontAwesomeIcon icon={faUser} /> User
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
                      <FontAwesomeIcon icon={selectedNode.node_type === "tag" ? faHashtag : selectedNode.node_type === "user" ? faUser : faShareNodes} />
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
