"use client";

import { RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

export function RefreshButton() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  return (
    <button
      className="icon-button"
      type="button"
      title="Refresh dashboard data"
      aria-label="Refresh dashboard data"
      disabled={isPending}
      onClick={() => startTransition(() => router.refresh())}
    >
      <RefreshCw className={isPending ? "spin" : undefined} size={18} aria-hidden="true" />
    </button>
  );
}
