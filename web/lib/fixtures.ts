import type { AddressComponent, ReviewResult } from "./types";

// Each of these produces its intended status from the REAL backend, verified
// against the running service. The previous set only worked on the fixture
// path, which routes by keyword ("sukamaju" -> invalid); once
// NEXT_PUBLIC_API_BASE_URL was set, all three collapsed to PERLU_KONFIRMASI and
// the demo demonstrated nothing.
export const DEMO_ADDRESSES = {
  // Complete, internally consistent chain with explicit designators. Without
  // "Kel."/"Kec." the rule extractor does not recover the two fields and even a
  // correct address lands in PERLU_KONFIRMASI.
  ready: "Jl. Braga No. 5, Kel. Braga, Kec. Sumur Bandung, Kota Bandung, Jawa Barat 40111",
  // A village absent from the reference: medium severity, because a coverage
  // gap is not evidence the address is wrong.
  confirmation: "Jl. Melati No. 7, Kel. Sukamaju Indah, Kec. Sumur Bandung, Kota Bandung, Jawa Barat 40111",
  // Braga is in Sumur Bandung, so the reference contradicts Coblong outright:
  // high severity, and the only kind of evidence that reaches TIDAK_VALID.
  invalid: "Jl. Braga No. 5, Kel. Braga, Kec. Coblong, Kota Bandung, Jawa Barat 40111",
} as const;

const base = (
  values: Partial<Record<AddressComponent["field"], string>>,
): AddressComponent[] => {
  const fields: Array<[AddressComponent["field"], string]> = [
    ["JALAN", "Jalan"], ["NOMOR", "Nomor"], ["RT", "RT"], ["RW", "RW"],
    ["KELURAHAN", "Kelurahan"], ["KECAMATAN", "Kecamatan"],
    ["KOTA_KABUPATEN", "Kota / Kabupaten"], ["PROVINSI", "Provinsi"],
    ["KODEPOS", "Kode pos"], ["DETAIL_LOKASI", "Detail lokasi"],
  ];
  return fields.map(([field, label], index) => ({
    field,
    label,
    value: values[field] ?? "",
    source: values[field] ? (index < 2 ? "parser" : "reference") : "input",
    state: "original",
    modelScore: values[field] ? Math.max(0.74, 0.98 - index * 0.018) : undefined,
  }));
};

export const readyFixture: ReviewResult = {
  id: "review-ready-01",
  status: "SIAP_DIPROSES",
  redactedInput: DEMO_ADDRESSES.ready,
  normalizedAddress: "Jalan Braga No. 99, Kel. Braga, Kec. Sumur Bandung, Kota Bandung, Jawa Barat 40111",
  isFinal: true,
  issues: [],
  components: base({
    JALAN: "Jalan Braga", NOMOR: "99", KELURAHAN: "Braga", KECAMATAN: "Sumur Bandung",
    KOTA_KABUPATEN: "Kota Bandung", PROVINSI: "Jawa Barat", KODEPOS: "40111",
  }),
  versions: { model: "alamatin-ner 0.4", normalizer: "0.3.1", validator: "0.5.0", reference: "wilayah-id 2026.07" },
};

export const confirmationFixture: ReviewResult = {
  id: "review-confirm-01",
  status: "PERLU_KONFIRMASI",
  redactedInput: DEMO_ADDRESSES.confirmation,
  normalizedAddress: "Jalan Cimanuk No. 12, Kel. Citarum, Kec. Bandung Wetan, Kota Bandung, Jawa Barat 40114",
  isFinal: false,
  components: base({
    JALAN: "Jalan Cimanuk", NOMOR: "12", KELURAHAN: "Citarum", KECAMATAN: "Bandung Wetan",
    KOTA_KABUPATEN: "Kota Bandung", PROVINSI: "Jawa Barat", KODEPOS: "40114",
  }).map((item) => item.field === "KODEPOS" ? {
    ...item, suggestion: "40115", state: "suggested", source: "reference", modelScore: 0.76,
  } : item),
  // An unapplied suggestion is CORRECTION_REQUIRES_CONFIRMATION at medium
  // severity, which is what yields PERLU_KONFIRMASI. Marking it high would make
  // the frozen gate return TIDAK_VALID instead.
  issues: [{
    id: "postal-correction",
    severity: "medium",
    title: "Koreksi menunggu konfirmasi",
    message: "Referensi wilayah menyarankan kode pos lain untuk Kelurahan Citarum. Koreksi belum diterapkan.",
    reasonCode: "CORRECTION_REQUIRES_CONFIRMATION",
    affectedFields: ["KODEPOS"],
    question: "Apakah koreksi kode pos yang disarankan boleh diterapkan?",
  }],
  versions: { model: "alamatin-ner 0.4", normalizer: "0.3.1", validator: "0.5.0", reference: "wilayah-id 2026.07" },
};

export const invalidFixture: ReviewResult = {
  id: "review-invalid-01",
  status: "TIDAK_VALID",
  redactedInput: DEMO_ADDRESSES.invalid,
  normalizedAddress: "Sukamaju, Jawa Barat",
  isFinal: false,
  components: base({ KELURAHAN: "Sukamaju", PROVINSI: "Jawa Barat", DETAIL_LOKASI: "Dekat lapangan utama" }),
  // TIDAK_VALID requires a high-severity, reference-supported conflict.
  // Ambiguity is medium in the frozen gate, so this demonstrates an actual
  // administrative conflict instead. Only ADMINISTRATIVE_FIELDS may appear in a
  // high-severity issue (ALM-024), so DETAIL_LOKASI is not listed.
  issues: [{
    id: "admin-conflict",
    severity: "high",
    title: "Komponen wilayah bertentangan",
    message: "Kecamatan yang disebut tidak berada di kota/kabupaten yang disebut menurut referensi wilayah.",
    reasonCode: "ADMINISTRATIVE_CONFLICT",
    affectedFields: ["KECAMATAN", "KOTA_KABUPATEN"],
    question: "Mohon periksa kecamatan dan kota/kabupaten; nilai mana yang sesuai dengan alamat tujuan?",
  }],
  versions: { model: "alamatin-ner 0.4", normalizer: "0.3.1", validator: "0.5.0", reference: "wilayah-id 2026.07" },
};
