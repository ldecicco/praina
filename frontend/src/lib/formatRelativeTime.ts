const MINUTE = 60;
const HOUR = 3600;
const DAY = 86400;

/**
 * Formats an ISO date string as a human-readable relative time.
 * Returns "just now", "5m ago", "3h ago", "Yesterday", "3 days ago",
 * or a short date for anything older than 7 days.
 */
export function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = Date.now();
  const diffSec = Math.floor((now - date.getTime()) / 1000);

  if (diffSec < 0) return date.toLocaleDateString();
  if (diffSec < MINUTE) return "just now";
  if (diffSec < HOUR) return `${Math.floor(diffSec / MINUTE)}m ago`;
  if (diffSec < DAY) return `${Math.floor(diffSec / HOUR)}h ago`;
  if (diffSec < DAY * 2) return "Yesterday";
  if (diffSec < DAY * 7) return `${Math.floor(diffSec / DAY)} days ago`;

  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: date.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined });
}
