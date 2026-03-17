import { useState } from "react";

import { api } from "../lib/api";
import type { AuthTokens, MeResponse } from "../types";
import prainaFullWhite from "../assets/praina-full-white.svg";

type Props = {
  onAuthenticated: (tokens: AuthTokens, me: MeResponse) => void;
};

type Mode = "login" | "register";

export function AuthScreen({ onAuthenticated }: Props) {
  const [mode, setMode] = useState<Mode>("login");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit() {
    if (!email || !password || (mode === "register" && !displayName)) return;
    try {
      setBusy(true);
      setError("");

      if (mode === "register") {
        await api.register({
          email,
          password,
          display_name: displayName,
        });
      }

      const tokens = await api.login({ email, password });
      api.setAuthToken(tokens.access_token);
      const me = await api.me();
      onAuthenticated(tokens, me);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-screen">
      <section className="auth-card">
        <img src={prainaFullWhite} alt="Praina" style={{ height: 48, display: 'block', margin: '0 auto 16px' }} />
        <div className="auth-tabs">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
            Sign in
          </button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
            Register
          </button>
        </div>

        <div className="auth-form">
          {mode === "register" ? (
            <label>
              Name
              <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Jane Doe" />
            </label>
          ) : null}
          <label>
            Email
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@org.eu" />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") void handleSubmit(); }}
            />
          </label>
        </div>

        {error ? <p className="error">{error}</p> : null}

        <div className="auth-actions">
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={busy || !email || !password || (mode === "register" && !displayName)}
          >
            {busy ? "Signing in..." : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </div>
      </section>
    </div>
  );
}
