import {
  buildParseRequest,
  composeAddressText,
  toReviewResult,
  type ContractErrorResponse,
  type ContractResponse,
} from "./contract";
import { DEMO_ADDRESSES, confirmationFixture, invalidFixture, readyFixture } from "./fixtures";
import type { AddressComponent, ReviewResult } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL;

const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Turn a backend response into either a review or a safe error.
 *
 * The API answers with the frozen `api_error` contract on failure, so the
 * error code is read from the body rather than guessed from the status. No
 * response text is echoed to the user: the body may quote input, and raw
 * addresses must not leak into UI copy or logs.
 */
async function readContractResponse(response: Response): Promise<ReviewResult> {
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    throw new Error("api");
  }

  if (!response.ok) {
    const error = payload as ContractErrorResponse;
    const code = error?.error?.code;
    if (code === "PIPELINE_UNAVAILABLE" || response.status === 503) {
      throw new Error("dependency");
    }
    if (code === "REQUEST_VALIDATION_ERROR") throw new Error("request");
    if (code === "PROCESSING_TIMEOUT" || response.status === 504) {
      throw new Error("timeout");
    }
    throw new Error("api");
  }

  return toReviewResult(payload as ContractResponse);
}

export async function parseAddress(rawAddress: string, signal?: AbortSignal): Promise<ReviewResult> {
  if (API_BASE) {
    const response = await fetch(`${API_BASE}/parse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildParseRequest(rawAddress)),
      signal,
    });
    return readContractResponse(response);
  }

  await pause(850);
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  // Matched against the demo constants themselves rather than substrings of
  // them. The previous keyword routing ("sukamaju" -> invalid) silently
  // mis-routed as soon as a demo address changed, and coupled the fixture path
  // to the wording of addresses chosen for the real backend.
  const normalized = rawAddress.trim().toLowerCase();
  const fixture =
    normalized === DEMO_ADDRESSES.invalid.toLowerCase()
      ? invalidFixture
      : normalized === DEMO_ADDRESSES.confirmation.toLowerCase()
        ? confirmationFixture
        : readyFixture;
  return structuredClone(fixture);
}

export async function validateAddress(
  result: ReviewResult,
  components: AddressComponent[],
): Promise<ReviewResult> {
  if (API_BASE) {
    // The frozen contract gives /validate the same request shape as /parse, so
    // re-validation submits the address rebuilt from the edited components
    // rather than a component list the schema would reject.
    const response = await fetch(`${API_BASE}/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildParseRequest(composeAddressText(components))),
    });
    return readContractResponse(response);
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
