import type Graph from "graphology";
import type Sigma from "sigma";

/* ── CSS helpers ── */

export function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

export function rgbaFromHex(value: string, alpha: number): string {
  const normalized = value.trim();
  if (!normalized.startsWith("#")) return `rgba(17,17,19,${alpha})`;
  const hex = normalized.slice(1);
  const full =
    hex.length === 3
      ? hex
          .split("")
          .map((c) => `${c}${c}`)
          .join("")
      : hex;
  const r = Number.parseInt(full.slice(0, 2), 16);
  const g = Number.parseInt(full.slice(2, 4), 16);
  const b = Number.parseInt(full.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

/* ── Canvas drawing ── */

export function drawRoundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  radius: number,
) {
  const r = Math.min(radius, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

export function drawGraphLabel(
  ctx: CanvasRenderingContext2D,
  data: { label?: string | null; size?: number; color?: string; x?: number; y?: number },
) {
  if (!data.label || typeof data.x !== "number" || typeof data.y !== "number") return;
  const bg = cssVar("--bg", "#111113");
  const textBright = cssVar("--text-bright", "#ededf0");
  const size = typeof data.size === "number" ? data.size : 10;
  const fontSize = Math.max(11, Math.round(size * 0.92));
  const padX = 8;
  const padY = 5;
  const radius = 7;

  ctx.font = `600 ${fontSize}px var(--font), sans-serif`;
  const textWidth = ctx.measureText(data.label).width;
  const boxW = textWidth + padX * 2;
  const boxH = fontSize + padY * 2;
  const x = data.x + size + 8;
  const y = data.y - boxH / 2;

  ctx.save();
  ctx.shadowColor = rgbaFromHex(bg, 0.46);
  ctx.shadowBlur = 22;
  ctx.fillStyle = rgbaFromHex(bg, 0.84);
  drawRoundedRect(ctx, x, y, boxW, boxH, radius);
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.strokeStyle = rgbaFromHex(data.color || cssVar("--brand", "#3AAFA8"), 0.34);
  ctx.lineWidth = 1;
  drawRoundedRect(ctx, x, y, boxW, boxH, radius);
  ctx.stroke();
  ctx.fillStyle = textBright;
  ctx.textBaseline = "middle";
  ctx.fillText(data.label, x + padX, y + boxH / 2);
  ctx.restore();
}

/* ── Layout helpers ── */

export function buildInitialPositions(ids: string[]) {
  const total = Math.max(ids.length, 1);
  return new Map(
    ids.map((id, index) => {
      const angle = (Math.PI * 2 * index) / total;
      return [id, { x: Math.cos(angle) * 12, y: Math.sin(angle) * 12 }];
    }),
  );
}

/** Size nodes by connection count: base + sqrt(degree) * scale */
export function computeNodeSize(graph: Graph, nodeId: string, baseSize: number, scale = 2): number {
  const degree = graph.degree(nodeId);
  return baseSize + Math.sqrt(degree) * scale;
}

/** Get N-hop neighbors from a node */
export function getNeighborsAtDepth(graph: Graph, nodeId: string, depth: number): Set<string> {
  const visited = new Set<string>([nodeId]);
  let frontier = new Set<string>([nodeId]);
  for (let i = 0; i < depth; i++) {
    const nextFrontier = new Set<string>();
    frontier.forEach((id) => {
      if (!graph.hasNode(id)) return;
      graph.neighbors(id).forEach((neighbor) => {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          nextFrontier.add(neighbor);
        }
      });
    });
    frontier = nextFrontier;
    if (frontier.size === 0) break;
  }
  visited.delete(nodeId);
  return visited;
}

/* ── Interaction: hover tracking ── */

export function setupHoverTracking(
  renderer: Sigma,
  onHoverChange: (nodeId: string | null) => void,
): () => void {
  function handleEnter(e: { node: string }) {
    onHoverChange(e.node);
  }
  function handleLeave() {
    onHoverChange(null);
  }
  renderer.on("enterNode", handleEnter);
  renderer.on("leaveNode", handleLeave);
  return () => {
    renderer.removeListener("enterNode", handleEnter);
    renderer.removeListener("leaveNode", handleLeave);
  };
}

/** Build node/edge reducers that handle hover-highlight, focus mode with depth, and edge labels */
export function applyGraphReducers(
  renderer: Sigma,
  graph: Graph,
  opts: {
    hoveredNode: string | null;
    selectedNode: string | null;
    focusMode: boolean;
    focusDepth?: number;
    hoveredEdge?: string | null;
    cameraRatio?: number;
  },
) {
  const muted = cssVar("--muted", "#6e6e7a");
  const { hoveredNode, selectedNode, focusMode, focusDepth = 1, hoveredEdge, cameraRatio = 1 } = opts;

  // Determine the "active" node: hover takes priority over selection
  const activeNode = hoveredNode || (focusMode ? selectedNode : null);
  // Hover always uses 1-hop; focus mode uses configured depth
  const depth = hoveredNode ? 1 : focusDepth;
  const neighborIds = activeNode && graph.hasNode(activeNode)
    ? getNeighborsAtDepth(graph, activeNode, depth)
    : new Set<string>();

  // For multi-hop, also collect edges that connect visible nodes
  const visibleNodes = new Set(neighborIds);
  if (activeNode) visibleNodes.add(activeNode);

  renderer.setSetting("nodeReducer", (node, data) => {
    if (!activeNode) {
      const nodeType = String((data as { nodeType?: string }).nodeType || "");
      const showHubLabels = cameraRatio <= 1.15;
      const showAllLabels = cameraRatio <= 0.75;
      const keepLabel = showAllLabels || (showHubLabels && nodeType !== "log");
      if (selectedNode && node === selectedNode)
        return { ...data, size: (typeof data.size === "number" ? data.size : 10) + 3, zIndex: 1 };
      return keepLabel ? data : { ...data, label: "" };
    }
    if (node === activeNode)
      return { ...data, size: (typeof data.size === "number" ? data.size : 10) + 3, zIndex: 2 };
    if (neighborIds.has(node)) return { ...data, zIndex: 1 };
    return { ...data, color: muted, label: "" };
  });

  renderer.setSetting("edgeReducer", (edge, data) => {
    // Edge label on hover
    if (hoveredEdge && edge === hoveredEdge) {
      const edgeType = graph.getEdgeAttribute(edge, "edgeType") as string | undefined;
      return { ...data, forceLabel: true, label: edgeType?.replace(/_/g, " ") || "" };
    }
    if (!activeNode) return { ...data, forceLabel: false, label: undefined };
    const extremities = graph.extremities(edge);
    // For multi-hop: show edges between any two visible nodes
    if (visibleNodes.has(extremities[0]) && visibleNodes.has(extremities[1]))
      return { ...data, hidden: false, size: (typeof data.size === "number" ? data.size : 1.2) + 0.6, forceLabel: false, label: undefined };
    return { ...data, hidden: true, forceLabel: false, label: undefined };
  });

  renderer.refresh();
}

/* ── Interaction: node dragging with pinning ── */

export function setupNodeDrag(
  renderer: Sigma,
  graph: Graph,
  pinnedNodes: Set<string>,
  onPinnedChange?: (count: number) => void,
): () => void {
  let draggedNode: string | null = null;
  let isDragging = false;

  function handleDown(e: { node: string }) {
    isDragging = false;
    draggedNode = e.node;
    renderer.getCamera().disable();
  }

  const captor = renderer.getMouseCaptor();

  function handleMove(e: { x: number; y: number; original: MouseEvent | TouchEvent }) {
    if (!draggedNode) return;
    isDragging = true;
    const pos = renderer.viewportToGraph({ x: e.x, y: e.y });
    graph.setNodeAttribute(draggedNode, "x", pos.x);
    graph.setNodeAttribute(draggedNode, "y", pos.y);
  }

  function handleUp() {
    if (draggedNode) {
      if (isDragging) {
        // Pin the node after dragging
        pinnedNodes.add(draggedNode);
        onPinnedChange?.(pinnedNodes.size);
      }
      draggedNode = null;
      renderer.getCamera().enable();
    }
    isDragging = false;
  }

  renderer.on("downNode", handleDown);
  captor.on("mousemovebody", handleMove);
  captor.on("mouseup", handleUp);

  const container = renderer.getContainer();
  container.addEventListener("mouseleave", handleUp);

  return () => {
    renderer.removeListener("downNode", handleDown);
    captor.removeListener("mousemovebody", handleMove);
    captor.removeListener("mouseup", handleUp);
    container.removeEventListener("mouseleave", handleUp);
  };
}

/** Restore positions of pinned nodes after a physics tick */
export function restorePinnedPositions(graph: Graph, pinnedNodes: Set<string>, saved: Map<string, { x: number; y: number }>) {
  saved.forEach(({ x, y }, id) => {
    if (graph.hasNode(id)) {
      graph.setNodeAttribute(id, "x", x);
      graph.setNodeAttribute(id, "y", y);
    }
  });
}

/** Save positions of pinned nodes before a physics tick */
export function savePinnedPositions(graph: Graph, pinnedNodes: Set<string>): Map<string, { x: number; y: number }> {
  const saved = new Map<string, { x: number; y: number }>();
  pinnedNodes.forEach((id) => {
    if (graph.hasNode(id)) {
      saved.set(id, {
        x: graph.getNodeAttribute(id, "x") as number,
        y: graph.getNodeAttribute(id, "y") as number,
      });
    }
  });
  return saved;
}

/* ── Interaction: zoom-to-node ── */

export function zoomToNode(renderer: Sigma, graph: Graph, nodeId: string, duration = 300) {
  if (!graph.hasNode(nodeId)) return;
  const displayData = renderer.getNodeDisplayData(nodeId);
  if (!displayData) return;
  const camera = renderer.getCamera();
  camera.animate({ x: displayData.x, y: displayData.y, ratio: 0.3 }, { duration });
}

/* ── Interaction: zoom controls ── */

export function zoomIn(renderer: Sigma) {
  renderer.getCamera().animatedZoom({ duration: 200 });
}

export function zoomOut(renderer: Sigma) {
  renderer.getCamera().animatedUnzoom({ duration: 200 });
}

export function zoomFit(renderer: Sigma) {
  renderer.getCamera().animatedReset({ duration: 250 });
}

/* ── Export graph as PNG ── */

export function exportGraphAsPng(renderer: Sigma) {
  const canvases = renderer.getCanvases();
  const layers = Object.values(canvases);
  if (layers.length === 0) return;

  const first = layers[0];
  const w = first.width;
  const h = first.height;

  const merged = document.createElement("canvas");
  merged.width = w;
  merged.height = h;
  const ctx = merged.getContext("2d");
  if (!ctx) return;

  // Fill with background
  const bg = cssVar("--bg", "#111113");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);

  // Draw each Sigma layer
  layers.forEach((canvas) => {
    ctx.drawImage(canvas, 0, 0);
  });

  // Trigger download
  const link = document.createElement("a");
  link.download = "graph.png";
  link.href = merged.toDataURL("image/png");
  link.click();
}

/* ── Keyboard navigation ── */

export function getNextNeighbor(
  graph: Graph,
  selectedNode: string | null,
  direction: "next" | "prev",
): string | null {
  if (!selectedNode || !graph.hasNode(selectedNode)) return null;
  const neighbors = graph.neighbors(selectedNode);
  if (neighbors.length === 0) return null;
  // Just return first/last neighbor — caller can track index
  return direction === "next" ? neighbors[0] : neighbors[neighbors.length - 1];
}
