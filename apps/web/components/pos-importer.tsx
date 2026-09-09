"use client";

import { AlertCircle, CheckCircle2, Download, FileUp, LoaderCircle, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import Papa from "papaparse";
import { useMemo, useRef, useState } from "react";
import type { MenuItem } from "@/lib/api";

type RawPosRow = {
  sale_date?: string;
  menu_item_id?: string;
  quantity_sold?: string;
  unit_price?: string;
};

type PosRow = {
  sale_date: string;
  menu_item_id: string;
  quantity_sold: number;
  unit_price: string;
};

export function PosImporter({ menuItems }: { menuItems: MenuItem[] }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const menuMap = useMemo(() => new Map(menuItems.map((item) => [item.menu_item_id, item])), [menuItems]);
  const [fileName, setFileName] = useState("");
  const [rows, setRows] = useState<PosRow[]>([]);
  const [message, setMessage] = useState("");
  const [state, setState] = useState<"idle" | "ready" | "saving" | "saved" | "error">("idle");

  function selectFile(file: File | undefined) {
    if (!file) return;
    setFileName(file.name);
    setRows([]);
    setMessage("");
    Papa.parse<RawPosRow>(file, {
      header: true,
      skipEmptyLines: "greedy",
      complete(result) {
        if (result.errors.length) {
          setState("error");
          setMessage(`CSV row ${result.errors[0].row ?? 0}: ${result.errors[0].message}`);
          return;
        }
        const parsed: PosRow[] = [];
        for (const [index, row] of result.data.entries()) {
          const quantity = Number(row.quantity_sold);
          const price = Number(row.unit_price);
          if (!row.sale_date || !/^\d{4}-\d{2}-\d{2}$/.test(row.sale_date)) {
            setState("error"); setMessage(`Row ${index + 2}: sale_date must use YYYY-MM-DD.`); return;
          }
          if (!row.menu_item_id || !menuMap.has(row.menu_item_id)) {
            setState("error"); setMessage(`Row ${index + 2}: unknown menu_item_id ${row.menu_item_id ?? ""}.`); return;
          }
          if (!Number.isInteger(quantity) || quantity <= 0) {
            setState("error"); setMessage(`Row ${index + 2}: quantity_sold must be a positive whole number.`); return;
          }
          if (!Number.isFinite(price) || price < 0) {
            setState("error"); setMessage(`Row ${index + 2}: unit_price must be zero or greater.`); return;
          }
          parsed.push({ sale_date: row.sale_date, menu_item_id: row.menu_item_id, quantity_sold: quantity, unit_price: price.toFixed(2) });
        }
        if (!parsed.length) {
          setState("error"); setMessage("The CSV contains no sales rows."); return;
        }
        setRows(parsed);
        setState("ready");
        setMessage(`${parsed.length} rows validated and ready to post.`);
      },
    });
  }

  async function postUsage() {
    setState("saving");
    setMessage("");
    try {
      const response = await fetch("/api/pos/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recorded_by: "Jin Manager", rows }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? "POS import failed");
      setState("saved");
      setMessage(`${result.inserted_rows} sales posted, ${result.movement_count} inventory movements created, ${result.skipped_rows} duplicates skipped.`);
      router.refresh();
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : "POS import failed");
    }
  }

  return (
    <section className="panel import-panel" aria-labelledby="import-title">
      <div className="panel-header">
        <div><h2 id="import-title">Import POS sales</h2><p>Validate daily menu totals before posting recipe usage</p></div>
        <FileUp size={20} aria-hidden="true" />
      </div>
      <div className="import-body">
        <input ref={inputRef} className="file-input" type="file" accept=".csv,text/csv" onChange={(event) => selectFile(event.target.files?.[0])} />
        <button className="upload-zone" type="button" onClick={() => inputRef.current?.click()}>
          <span><Upload size={20} aria-hidden="true" /></span>
          <strong>{fileName || "Choose POS CSV"}</strong>
          <small>sale_date, menu_item_id, quantity_sold, unit_price</small>
        </button>
        <a className="template-link" href="/pos-sales-template.csv" download><Download size={14} aria-hidden="true" /> Download CSV template</a>

        {rows.length ? (
          <div className="import-preview">
            <div className="preview-heading"><strong>Preview</strong><span>{rows.length} rows</span></div>
            {rows.slice(0, 4).map((row, index) => (
              <div className="preview-row" key={`${row.sale_date}-${row.menu_item_id}-${index}`}>
                <span>{row.sale_date}</span>
                <strong>{menuMap.get(row.menu_item_id)?.menu_item_name}</strong>
                <span>{row.quantity_sold} × ${row.unit_price}</span>
              </div>
            ))}
            {rows.length > 4 ? <p className="more-rows">+ {rows.length - 4} more rows</p> : null}
          </div>
        ) : null}

        {message ? <div className={`import-message ${state === "error" ? "error" : ""}`}>{state === "error" ? <AlertCircle size={15} aria-hidden="true" /> : <CheckCircle2 size={15} aria-hidden="true" />}<span>{message}</span></div> : null}
        <button className="primary-button post-button" type="button" disabled={state !== "ready"} onClick={postUsage}>
          {state === "saving" ? <LoaderCircle className="spin" size={16} aria-hidden="true" /> : <Upload size={16} aria-hidden="true" />}
          Post recipe usage
        </button>
      </div>
    </section>
  );
}
