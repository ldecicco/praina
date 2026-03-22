export function renderHealthIndicator(health: string) {
  return <span className={`health-dot ${health} teaching-health-indicator`} aria-label={health} title={health} />;
}
