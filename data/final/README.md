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
  Barat, tidak ada lagi baris unresolved.

Header identik antar section dan tidak ada overlap `village_code`, sehingga
penggabungan ini aman dan reproducible.

Bangun ulang folder ini dengan:

```bash
python scripts/stage_final_postal_sections.py
```
