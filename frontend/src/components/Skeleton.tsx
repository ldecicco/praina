/**
 * Skeleton loader primitives.
 * Use these to show placeholder shapes while data loads.
 *
 * <SkeletonLine />           — single text-height bar
 * <SkeletonLine width="60%" /> — shorter bar
 * <SkeletonBlock height={120} /> — tall rectangle (card, chart, etc.)
 * <SkeletonTable rows={5} cols={4} /> — table placeholder
 */

export function SkeletonLine({ width = "100%" }: { width?: string }) {
  return <div className="skeleton-line" style={{ width }} />;
}

export function SkeletonBlock({ height = 80 }: { height?: number }) {
  return <div className="skeleton-block" style={{ height }} />;
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="skeleton-table">
      <div className="skeleton-table-header">
        {Array.from({ length: cols }).map((_, i) => (
          <div key={`sh-${i}`} className="skeleton-line" style={{ width: `${60 + Math.random() * 40}%` }} />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={`sr-${r}`} className="skeleton-table-row">
          {Array.from({ length: cols }).map((_, c) => (
            <div key={`sc-${r}-${c}`} className="skeleton-line" style={{ width: `${50 + Math.random() * 50}%` }} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonCards({ count = 3 }: { count?: number }) {
  return (
    <div className="skeleton-cards">
      {Array.from({ length: count }).map((_, i) => (
        <div key={`scard-${i}`} className="skeleton-card">
          <SkeletonLine width="45%" />
          <SkeletonLine width="80%" />
          <SkeletonLine width="65%" />
        </div>
      ))}
    </div>
  );
}
