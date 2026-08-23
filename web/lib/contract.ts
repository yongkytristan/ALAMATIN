/**
 * Adapter between the frozen ALM-025 wire contract and the UI's view model.
 *
 * The contract is snake_case, wraps every value with provenance, and keeps the
 * quality gate, corrections, and PII in separate sections. The components in
 * this app work with a flat camelCase `ReviewResult`. Mapping happens here and
 * nowhere else, so the wire format can change without touching the UI.
 */
import type {
  AddressComponent,
  AddressField,
  ReviewIssue,
  ReviewResult,
  ReviewStatus,
  Severity,
} from "./types";

/** `source` values the contract may report for a value. */
type ContractSource =
  | "user_input"
  | "rule_extracted"
  | "extracted_by_model"
  | "normalized_by_dictionary"
  | "inferred_from_hierarchy"
  | "returned_by_geocoder"
  | "confirmed_by_user";

interface ContractBasicValue {
  value: string;
  source: ContractSource;
  confirmed: boolean;
}

interface ContractResultValue extends ContractBasicValue {
  model_score: number | null;
  previous_value: ContractBasicValue | null;
}

interface ContractCorrection {
  correction_id: string;
  field: AddressField;
  previous_value: ContractBasicValue;
  proposed_value: ContractBasicValue;
  rule_id: string;
  decision: "requires_confirmation" | "confirmed" | "rejected" | "applied";
  applied: boolean;
  user_confirmation: unknown;
}

export interface ContractResponse {
  document_type: string;
  schema_version: string;
  request_id: string;
  versions: {
    contract: string;
    model: string;
    normalizer: string;
    validator: string;
    reference_data: string;
    quality_gate: string;
  };
  pii: { redacted_text: ContractBasicValue };
  components: Array<{ field: AddressField; result: ContractResultValue }>;
  normalized_address: ContractResultValue;
  quality_gate: {
    status: ReviewStatus;
    issues: Array<{
      reason_code: string;
      severity: Severity;
      message: string;
      affected_fields: AddressField[];
      clarification_question: string;
      source_reason_code: string;
    }>;
  };
  corrections: ContractCorrection[];
}

export interface ContractErrorResponse {
  document_type: "api_error";
  error: { code: string; message: string; retryable: boolean };
}

export const FIELD_LABELS: Record<AddressField, string> = {
  JALAN: "Jalan",
  NOMOR: "Nomor",
  RT: "RT",
  RW: "RW",
  KELURAHAN: "Kelurahan",
  KECAMATAN: "Kecamatan",
  KOTA_KABUPATEN: "Kota/Kabupaten",
  PROVINSI: "Provinsi",
  KODEPOS: "Kode pos",
  DETAIL_LOKASI: "Detail lokasi",
};

/** Short human titles for the six frozen reason codes. */
const REASON_TITLES: Record<string, string> = {
  KODEPOS_TIDAK_COCOK: "Kode pos tidak cocok",
  KELURAHAN_TIDAK_DITEMUKAN: "Kelurahan tidak ditemukan",
  ADMINISTRATIVE_CONFLICT: "Komponen wilayah bertentangan",
  MISSING_ADMINISTRATIVE_FIELDS: "Komponen wilayah belum lengkap",
  AMBIGUOUS_ADMINISTRATIVE_CANDIDATES: "Wilayah ambigu",
  CORRECTION_REQUIRES_CONFIRMATION: "Koreksi menunggu konfirmasi",
  MISSING_STREET_LOCATOR: "Nama jalan atau patokan belum ada",
};

/**
 * Map contract provenance onto the coarser origin the UI displays.
 * `confirmed_by_user` is deliberately grouped with user input: both mean a
 * human decided the value.
 */
function toUiSource(source: ContractSource): AddressComponent["source"] {
  switch (source) {
    case "user_input":
    case "confirmed_by_user":
      return "user";
    case "extracted_by_model":
    case "rule_extracted":
      return "parser";
    case "inferred_from_hierarchy":
    case "normalized_by_dictionary":
    case "returned_by_geocoder":
      return "reference";
    default:
      return "input";
  }
}

/**
 * Generate a request id that satisfies the contract pattern
 * `^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$`.
 */
export function newRequestId(prefix = "web"): string {
  const random = Math.random().toString(36).slice(2, 10);
  return `${prefix}${Date.now().toString(36)}${random}`.slice(0, 64);
}

export function buildParseRequest(
  addressText: string,
  options: { geocodingConsent?: boolean; requestId?: string } = {},
) {
  return {
    document_type: "address_parse_request" as const,
    // Deliberately 1.0.0: contract 1.1.0 is additive on the response side
    // and still accepts 1.0.0 requests, so nothing is gained by bumping
    // what clients send, and keeping it proves backwards compatibility.
    schema_version: "1.0.0" as const,
    request_id: options.requestId ?? newRequestId(),
    input: {
      address_text: addressText,
      // Never true unless the user explicitly consented: the frozen scope
      // requires geocoding to stay opt-in, and the P0 API returns an explicit
      // not-requested result instead of silently calling an external service.
      geocoding_consent: options.geocodingConsent ?? false,
    },
  };
}

/** Rebuild an address line from edited components, for re-validation. */
export function composeAddressText(components: AddressComponent[]): string {
  const pick = (field: AddressField) =>
    components.find((item) => item.field === field)?.value.trim() ?? "";
  const street = [pick("JALAN"), pick("NOMOR") && `No. ${pick("NOMOR")}`]
    .filter(Boolean)
    .join(" ");
  return [
    street,
    pick("RT") && `RT ${pick("RT")}`,
    pick("RW") && `RW ${pick("RW")}`,
    pick("KELURAHAN"),
    pick("KECAMATAN"),
    pick("KOTA_KABUPATEN"),
    pick("PROVINSI"),
    pick("KODEPOS"),
    pick("DETAIL_LOKASI"),
  ]
    .filter(Boolean)
    .join(", ");
}

function toComponent(
  entry: { field: AddressField; result: ContractResultValue },
  corrections: ContractCorrection[],
): AddressComponent {
  const { field, result } = entry;
  const pending = corrections.find(
    (correction) =>
      correction.field === field &&
      correction.decision === "requires_confirmation" &&
      !correction.applied,
  );

  let state: AddressComponent["state"];
  if (pending) {
    state = "suggested";
  } else if (result.confirmed || result.source === "confirmed_by_user") {
    state = "confirmed";
  } else if (result.previous_value) {
    state = "user-edited";
  } else {
    state = "original";
  }

  return {
    field,
    label: FIELD_LABELS[field] ?? field,
    value: result.value,
    previousValue: result.previous_value?.value ?? pending?.previous_value.value,
    suggestion: pending?.proposed_value.value,
    source: toUiSource(result.source),
    state,
    // model_score stays an uncalibrated score. It is never relabelled as
    // confidence; the frozen scope forbids presenting it that way.
    modelScore: result.model_score ?? undefined,
  };
}

function toIssue(
  issue: ContractResponse["quality_gate"]["issues"][number],
  index: number,
): ReviewIssue {
  return {
    id: `${issue.reason_code}-${index}`,
    severity: issue.severity,
    title: REASON_TITLES[issue.reason_code] ?? issue.reason_code,
    message: issue.message,
    reasonCode: issue.reason_code,
    affectedFields: issue.affected_fields,
    question: issue.clarification_question,
  };
}

/**
 * Build placeholder components for fields that only appear in `corrections`.
 *
 * A correction can propose a value for a field the parser never extracted --
 * the ambiguity example suggests `KOTA_KABUPATEN` while `components` holds only
 * `KELURAHAN`. Without this, that suggestion would be invisible and the user
 * could never accept it, so the review could not reach a final decision.
 */
function componentsFromOrphanCorrections(
  response: ContractResponse,
): AddressComponent[] {
  const present = new Set(response.components.map((entry) => entry.field));
  return response.corrections
    .filter(
      (correction) =>
        !present.has(correction.field) &&
        correction.decision === "requires_confirmation" &&
        !correction.applied,
    )
    .map((correction) => ({
      field: correction.field,
      label: FIELD_LABELS[correction.field] ?? correction.field,
      value: correction.previous_value.value,
      previousValue: correction.previous_value.value || undefined,
      suggestion: correction.proposed_value.value,
      source: toUiSource(correction.previous_value.source),
      state: "suggested" as const,
      modelScore: undefined,
    }));
}

/** Convert one contract response into the view model the UI renders. */
export function toReviewResult(response: ContractResponse): ReviewResult {
  const issues = response.quality_gate.issues.map(toIssue);
  return {
    id: response.request_id,
    status: response.quality_gate.status,
    // The redacted text is what the UI is allowed to display. The raw
    // address_text from the response is intentionally never read here.
    redactedInput: response.pii.redacted_text.value,
    components: [
      ...response.components.map((entry) =>
        toComponent(entry, response.corrections),
      ),
      ...componentsFromOrphanCorrections(response),
    ],
    normalizedAddress: response.normalized_address.value,
    // Final only when the frozen gate found nothing left to resolve.
    isFinal: response.quality_gate.status === "SIAP_DIPROSES",
    issues,
    versions: {
      model: response.versions.model,
      normalizer: response.versions.normalizer,
      validator: response.versions.validator,
      reference: response.versions.reference_data,
    },
  };
}
