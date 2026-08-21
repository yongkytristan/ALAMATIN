import type { AddressComponent, ReviewResult } from "./types";

export const DEMO_ADDRESSES = {
  ready: "Jl. Braga No. 99, Braga, Sumur Bandung, Kota Bandung, Jawa Barat 40111",
  confirmation: "Jl. Cimanuk No. 12, Citarum, Bandung Wetan, Kota Bandung, Jawa Barat 40114",
  invalid: "Dekat lapangan utama, Sukamaju, Jawa Barat",
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
  issues: [{
    id: "postal-conflict",
    severity: "high",
    title: "Kode pos perlu dipastikan",
    message: "Kode pos pada input berbeda dengan referensi wilayah untuk Kelurahan Citarum.",
    reasonCode: "POSTAL_CODE_CONFLICT",
    affectedFields: ["KODEPOS", "KELURAHAN"],
    question: "Gunakan kode pos referensi 40115 untuk alamat ini?",
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
  issues: [{
    id: "ambiguous-village",
    severity: "high",
    title: "Wilayah belum dapat ditentukan",
    message: "Ada beberapa kelurahan bernama Sukamaju. Kecamatan dan kota/kabupaten dibutuhkan.",
    reasonCode: "AMBIGUOUS_ADMIN_AREA",
    affectedFields: ["KELURAHAN", "KECAMATAN", "KOTA_KABUPATEN"],
    question: "Di kecamatan dan kota/kabupaten mana alamat ini berada?",
  }],
  versions: { model: "alamatin-ner 0.4", normalizer: "0.3.1", validator: "0.5.0", reference: "wilayah-id 2026.07" },
};
