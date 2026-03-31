import { useCallback, useRef, useState } from "react";

/**
 * Double-click-to-confirm pattern for destructive actions.
 * First click sets the id to "confirming" state (button shows "Sure?").
 * Second click within 3 seconds executes the action.
 * Auto-resets after 3 seconds if not confirmed.
 */
export function useConfirmDelete() {
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const requestConfirm = useCallback((id: string, onConfirm: () => void) => {
    if (confirmingId === id) {
      if (timerRef.current) clearTimeout(timerRef.current);
      setConfirmingId(null);
      onConfirm();
    } else {
      if (timerRef.current) clearTimeout(timerRef.current);
      setConfirmingId(id);
      timerRef.current = setTimeout(() => setConfirmingId(null), 3000);
    }
  }, [confirmingId]);

  return { confirmingId, requestConfirm };
}
