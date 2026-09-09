import { NextResponse } from "next/server";
import { cafeApiUrl } from "@/lib/api";

export async function POST(request: Request) {
  const body = await request.text();
  const response = await fetch(cafeApiUrl("/api/purchase-orders/drafts"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    cache: "no-store",
  });
  const result = await response.json();
  return NextResponse.json(result, { status: response.status });
}
