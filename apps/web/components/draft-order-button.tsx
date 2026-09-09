"use client";

import { Check, FilePlus2, LoaderCircle } from "lucide-react";
import { useState } from "react";

type DraftItem = {
  product_id: string;
  ordered_quantity: string;
};

export function DraftOrderButton({
  supplierId,
  expectedDeliveryDate,
  items,
}: {
  supplierId: string;
  expectedDeliveryDate: string;
  items: DraftItem[];
}) {
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState("");

  async function createDraft() {
    setState("saving");
    setMessage("");
    try {
      const response = await fetch("/api/reorder/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          supplier_id: supplierId,
          expected_delivery_date: expectedDeliveryDate,
          ordered_by: "Jin Manager",
          items,
        }),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail ?? "Draft order could not be created");
      }
      setState("saved");
      setMessage(`Draft PO #${result.po_id} created`);
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : "Draft order could not be created");
    }
  }

  return (
    <div className="draft-action">
      <button className="primary-button" type="button" onClick={createDraft} disabled={state === "saving" || state === "saved"}>
        {state === "saving" ? <LoaderCircle className="spin" size={16} aria-hidden="true" /> : state === "saved" ? <Check size={16} aria-hidden="true" /> : <FilePlus2 size={16} aria-hidden="true" />}
        {state === "saved" ? "Draft created" : "Create draft PO"}
      </button>
      {message ? <span className={state === "error" ? "action-message error" : "action-message"}>{message}</span> : null}
    </div>
  );
}
