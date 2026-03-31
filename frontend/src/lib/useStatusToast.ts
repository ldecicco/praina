import { useCallback, useState } from "react";
import { toast } from "sonner";

/**
 * Drop-in replacement for `useState("")` pairs used for status/error messages.
 * Automatically fires a toast when a non-empty message is set.
 */
export function useStatusToast() {
  const [error, setErrorRaw] = useState("");
  const [status, setStatusRaw] = useState("");

  const setError = useCallback((msg: string) => {
    setErrorRaw(msg);
    if (msg) toast.error(msg);
  }, []);

  const setStatus = useCallback((msg: string) => {
    setStatusRaw(msg);
    if (msg) toast.success(msg);
  }, []);

  return { error, setError, status, setStatus };
}
