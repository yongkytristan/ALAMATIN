# Merge-ready postal sections

Folder ini mempertahankan section yang sudah memiliki skema canonical sama,
plus satu file gabungan final:

- `section-1-verified-consensus.csv` — 2.876 baris consensus tiga sumber;
- `section-2-verified-adjudicated.csv` — 1.974 baris hasil review dan adjudikasi
  Pos Indonesia;
- `section-3-verified-adjudicated.csv` — 1.107 baris Section 3, termasuk 2
  baris yang diselesaikan lewat jalur manual Pos Indonesia correction (lihat
  `docs/postal-data-status-and-review-guide.md` bagian 1); dan
- `sections-summary.json` — jumlah baris, status kompatibilitas skema, dan
  checksum seluruh output.

Ketiga section digabung secara vertikal, diurutkan berdasarkan `village_code`,
menjadi satu file final:

- `jabar-postal-final-merged.csv` — 5.957 baris, seluruh desa/kelurahan Jawa
  Barat, tidak ada lagi baris unresolved. Skema penuh (26 kolom) — ini adalah
  **artefak audit/provenance**: siapa yang review, sumber mana per baris,
  evidence apa. Dipakai untuk `dataset_card.md` dan proposal §Governance,
  bukan untuk dibaca langsung oleh kode aplikasi.

Dari file gabungan itu, hanya 9 kolom yang benar-benar dipakai logic Parser →
Normalizer → Validator (kode/nama hierarki wilayah + kode pos final), jadi
diturunkan lagi menjadi satu file ramping:

- `jabar-postal-app-lookup.csv` — 5.957 baris, kolom:
  `village_code, province_code, province_name, city_code, city_name,
  district_code, district_name, village_name, postal_code`. **Inilah file
  yang sebaiknya dikonsumsi backend/Validator** kalau tidak memakai
  `data/processed/jabar-reference-v1-verified.json` (yang juga sudah punya
  alias per level wilayah untuk pencocokan nama tidak baku).

Header identik antar section dan tidak ada overlap `village_code`, sehingga
penggabungan dan penurunan kolom ini aman dan reproducible.

Bangun ulang folder ini dengan:

```bash
python scripts/stage_final_postal_sections.py
```
