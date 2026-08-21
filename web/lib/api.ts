import { confirmationFixture, invalidFixture, readyFixture } from "./fixtures";
import type { AddressComponent, ReviewResult } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL;

const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function parseAddress(rawAddress: string, signal?: AbortSignal): Promise<ReviewResult> {
  if (API_BASE) {
    const response = await fetch(`${API_BASE}/parse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address: rawAddress }),
      signal,
    });
    if (!response.ok) throw new Error(response.status === 503 ? "dependency" : "api");
    return response.json() as Promise<ReviewResult>;
  }

  await pause(850);
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  const source = rawAddress.toLowerCase();
  const fixture = source.includes("lapangan") || source.includes("sukamaju")
    ? invalidFixture
    : source.includes("cimanuk") || source.includes("40114")
      ? confirmationFixture
      : readyFixture;
  return structuredClone(fixture);
}

export async function validateAddress(
  result: ReviewResult,
  components: AddressComponent[],
): Promise<ReviewResult> {
  if (API_BASE) {
    const response = await fetch(`${API_BASE}/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ review_id: result.id, components }),
    });
    if (!response.ok) throw new Error(response.status === 503 ? "dependency" : "api");
    return response.json() as Promise<ReviewResult>;
  }

  await pause(700);
  const required = ["KELURAHAN", "KECAMATAN", "KOTA_KABUPATEN", "PROVINSI"];
  const missing = components.filter((item) => required.includes(item.field) && !item.value.trim());
  if (missing.length) {
    return { ...result, components, status: "TIDAK_VALID", isFinal: false };
  }
  const value = (field: AddressComponent["field"]) => components.find((item) => item.field === field)?.value;
  const normalized = [
    [value("JALAN"), value("NOMOR") && `No. ${value("NOMOR")}`].filter(Boolean).join(" "),
    value("KELURAHAN") && `Kel. ${value("KELURAHAN")}`,
    value("KECAMATAN") && `Kec. ${value("KECAMATAN")}`,
    value("KOTA_KABUPATEN"), value("PROVINSI"), value("KODEPOS"), value("DETAIL_LOKASI"),
  ].filter(Boolean).join(", ");
  return { ...result, components, normalizedAddress: normalized, issues: [], status: "SIAP_DIPROSES", isFinal: true };
}
