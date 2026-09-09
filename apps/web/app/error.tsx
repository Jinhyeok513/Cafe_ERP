"use client";

import { CircleAlert, RotateCcw } from "lucide-react";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="error-shell">
      <CircleAlert size={28} aria-hidden="true" />
      <h1>Operations data is unavailable</h1>
      <p>Check that the Cafe API and PostgreSQL are running, then try again.</p>
      <button className="primary-button" type="button" onClick={reset}>
        <RotateCcw size={16} aria-hidden="true" />
        Try again
      </button>
    </main>
  );
}
