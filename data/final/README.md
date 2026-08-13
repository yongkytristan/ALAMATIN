# Merge-ready postal sections

`python scripts/stage_final_postal_sections.py` reproducibly produces:

- `section-1-verified-consensus.csv` — 2.876 baris consensus tiga sumber;
- `section-2-verified-adjudicated.csv` — 1.974 baris hasil review dan adjudikasi
  Pos Indonesia;
- `section-3-verified-adjudicated.csv` — 1.107 baris Section 3, termasuk 2
  baris yang diselesaikan lewat jalur manual Pos Indonesia correction (lihat
  `docs/postal-data-status-and-review-guide.md` bagian 1);
- `jabar-postal-final-merged.csv` — ketiga section digabung vertikal,
  diurutkan berdasarkan `village_code`, 5.957 baris, seluruh desa/kelurahan
  Jawa Barat, tidak ada lagi baris unresolved. Skema penuh (26 kolom) — ini
  **artefak audit/provenance**: siapa yang review, sumber mana per baris,
  evidence apa. Dipakai untuk `dataset_card.md` dan proposal §Governance,
  bukan untuk dibaca langsung oleh kode aplikasi;
- `jabar-postal-app-lookup.csv` — versi ramping 9 kolom yang diturunkan dari
  file gabungan: `village_code, province_code, province_name, city_code,
  city_name, district_code, district_name, village_name, postal_code`.
  **Inilah file yang sebaiknya dikonsumsi backend/Validator** kalau tidak
  memakai `data/processed/jabar-reference-v1-verified.json` (yang juga sudah
  punya alias per level wilayah untuk pencocokan nama tidak baku); dan
- `sections-summary.json` — jumlah baris, status kompatibilitas skema, dan
  checksum seluruh output di atas.

## Yang benar-benar ada di repo ini

Hanya **`jabar-postal-app-lookup.csv`** yang redistribusinya disetujui dan
dicommit ke repo public — lihat keputusan bertanggal di `data/sources.md`
(`documented_exceptions` pada `open_data_jabar_postal_2023` dan
`kodepos_dev_rest_api`). `section-1/2/3-*.csv`, `jabar-postal-final-merged.csv`,
dan `sections-summary.json` masih menyimpan kolom mentah per-sumber
(`postal_code_diskominfo`, `postal_code_open_data_jabar`,
`postal_code_kodepos_dev`) yang **belum** tercakup keputusan itu, sehingga
tetap artefak lokal/privat saja. Menjalankan skrip di atas akan
menghasilkan semuanya secara lokal; jangan commit file-file itu ke repo
public tanpa keputusan redistribusi baru yang terpisah.

Header identik antar section dan tidak ada overlap `village_code`, sehingga
penggabungan dan penurunan kolom ini aman dan reproducible.
