export type ReviewStatus = "SIAP_DIPROSES" | "PERLU_KONFIRMASI" | "TIDAK_VALID";
export type ComponentState = "original" | "suggested" | "confirmed" | "rejected" | "user-edited";
export type Severity = "high" | "medium" | "low";

export type AddressField =
  | "JALAN"
  | "NOMOR"
  | "RT"
  | "RW"
  | "KELURAHAN"
  | "KECAMATAN"
  | "KOTA_KABUPATEN"
  | "PROVINSI"
  | "KODEPOS"
  | "DETAIL_LOKASI";

export interface AddressComponent {
  field: AddressField;
  label: string;
  value: string;
  previousValue?: string;
  suggestion?: string;
  source: "input" | "parser" | "reference" | "user";
  state: ComponentState;
  modelScore?: number;
}

export interface ReviewIssue {
  id: string;
  severity: Severity;
  title: string;
  message: string;
  reasonCode: string;
  affectedFields: AddressField[];
  question?: string;
}

export interface ReviewResult {
  id: string;
  status: ReviewStatus;
  redactedInput: string;
  components: AddressComponent[];
  normalizedAddress: string;
  isFinal: boolean;
  issues: ReviewIssue[];
  versions: {
    model: string;
    normalizer: string;
    validator: string;
    reference: string;
  };
}
