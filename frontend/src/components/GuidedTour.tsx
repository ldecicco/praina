import { useEffect, useLayoutEffect, useMemo, useState } from "react";

export type GuidedTourStep = {
  id: string;
  target: string;
  title: string;
  text: string;
};

export function GuidedTour({
  open,
  steps,
  stepIndex,
  onNext,
  onBack,
  onSkip,
  onFinish,
}: {
  open: boolean;
  steps: GuidedTourStep[];
  stepIndex: number;
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
  onFinish: () => void;
}) {
  const step = steps[stepIndex] ?? null;
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);

  const cardPosition = useMemo(() => {
    if (!targetRect) return { top: "50%", left: "50%", transform: "translate(-50%, -50%)" };
    const cardWidth = 320;
    const gap = 18;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const prefersBelow = targetRect.bottom + gap + 220 < viewportHeight;
    const top = prefersBelow
      ? Math.min(targetRect.bottom + gap, viewportHeight - 240)
      : Math.max(24, targetRect.top - 220 - gap);
    const left = Math.min(
      Math.max(24, targetRect.left + targetRect.width / 2 - cardWidth / 2),
      viewportWidth - cardWidth - 24,
    );
    return { top: `${top}px`, left: `${left}px`, transform: "none" };
  }, [targetRect]);

  useLayoutEffect(() => {
    if (!open || !step) return;
    let frame = 0;
    const update = () => {
      const target = document.querySelector<HTMLElement>(`[data-tour-id="${step.target}"]`);
      if (!target) {
        setTargetRect(null);
        return;
      }
      target.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
      setTargetRect(target.getBoundingClientRect());
    };
    const deferred = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    };
    deferred();
    window.addEventListener("resize", deferred);
    window.addEventListener("scroll", deferred, true);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", deferred);
      window.removeEventListener("scroll", deferred, true);
    };
  }, [open, step]);

  useEffect(() => {
    if (!open || !step) return;
    const target = document.querySelector<HTMLElement>(`[data-tour-id="${step.target}"]`);
    if (!target) return;
    target.classList.add("tour-target-active");
    return () => target.classList.remove("tour-target-active");
  }, [open, step]);

  if (!open || !step) return null;

  return (
    <div className="guided-tour-overlay" role="dialog" aria-modal="true">
      <div className="guided-tour-card" style={cardPosition}>
        <div className="guided-tour-step">{stepIndex + 1}/{steps.length}</div>
        <strong>{step.title}</strong>
        <p>{step.text}</p>
        <div className="guided-tour-actions">
          <button type="button" className="ghost" onClick={onSkip}>Skip</button>
          <div className="guided-tour-actions-right">
            <button type="button" className="ghost" onClick={onBack} disabled={stepIndex === 0}>Back</button>
            {stepIndex === steps.length - 1 ? (
              <button type="button" className="meetings-new-btn" onClick={onFinish}>Done</button>
            ) : (
              <button type="button" className="meetings-new-btn" onClick={onNext}>Next</button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
