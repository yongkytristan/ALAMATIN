# Status data dan panduan review kode pos Jawa Barat

Dokumen ini adalah panduan kerja untuk reviewer yang menyelesaikan kode pos
yang belum masuk lookup terverifikasi ALAMATIN. Ikuti keputusan per baris dan
jangan menganggap nilai yang paling sering muncul sebagai nilai benar tanpa
bukti tambahan.

## 1. Status snapshot saat ini

Snapshot internal yang direbuild 13 Agustus 2026 berisi 5.957 desa/kelurahan
Jawa Barat.

| Status | Jumlah | Arti | Boleh dipakai aplikasi? |
|---|---:|---|---|
| `usable_verified` / `verified_consensus` | 2.876 | Diskominfo, Open Data Jabar, dan Kodepos.dev sama | Ya, untuk exact postal lookup |
| `usable_verified` / `verified_adjudicated` | 3.081 | Review Pos Indonesia sudah dinormalisasi, divalidasi, dan disetujui melalui adjudikasi | Ya, untuk exact postal lookup |

Seluruh 5.957 baris sudah masuk lookup terverifikasi; tidak ada baris
`unresolved_do_not_guess` yang tersisa untuk Jawa Barat.

Dua baris terakhir yang sempat tertahan (SAMBENG dan SIRNABAYA, Kec. Gunung
Jati, Kab. Cirebon, `village_code` `32.09.21.2016` dan `32.09.21.2017`)
diselesaikan pada 13 Agustus 2026 lewat jalur *manual Pos Indonesia
correction* (lihat `scripts/adjudicate_postal_human_review.py`,
`adjudicate_unresolved_reviews`, cabang `manual_correction_confirmed`).
Pencocokan otomatis gagal karena basis data Pos Indonesia masih mencantumkan
kedua desa itu di kecamatan lama (Suranenggala), bukan kecamatan aktifnya
(Gunung Jati). Cache scrape Pos Indonesia (`pos-indonesia-unresolved-observations.cache.json`)
menunjukkan kecocokan exact desa+kabupaten+provinsi dengan kode pos `45659`,
dan perpindahan kecamatan itu terdokumentasi independen di
`data/kemendagri_code_resolutions.json`. Nilai `45659` ini juga sama dengan
nilai Diskominfo. Sebuah usulan awal (`45150`, dari direktori pihak ketiga
`nomor.net` via pencarian Google manual) ditolak karena sumbernya tidak
memenuhi hierarki evidence di dokumen ini (lihat Bagian 7) — baik skrip
adjudikasi maupun `scripts/build_final_jabar_reference.py` menolak sumber
selain Pos Indonesia untuk baris jenis ini.

## 2. File yang digunakan

Artefak build sumber bersifat read-only:

- `data/processed/jabar-postal-adjudicated.csv` — input canonical hasil
  adjudikasi untuk seluruh 5.957 baris;
- `data/processed/jabar-postal-adjudicated-evidence.csv` — evidence final untuk
  1.974 review yang dipromosikan;
- `data/processed/jabar-postal-adjudication-summary.json` — hitungan keputusan,
  checksum input/output, dan audit promosi;

- `data/processed/jabar-postal-corroborated-candidates.csv` — 1.974 kandidat;
- `data/processed/jabar-postal-unresolved.csv` — 1.107 unresolved;
- `data/processed/jabar-postal-unresolved-source-disagreement.csv` — 625
  unresolved dengan konflik/missing antarsumber;
- `data/processed/jabar-postal-government-consensus-api-conflict.csv` — 482
  unresolved ketika dua sumber pemerintah lokal sama dan API berbeda; dan
- `data/processed/jabar-reference-v1.csv` — tampilan gabungan seluruh status.

Jangan mengedit file di `data/processed/` secara langsung. File tersebut akan
ditimpa ketika build dijalankan ulang dan harus tetap reproducible.

Buat salinan kerja reviewer dengan:

```bash
python scripts/prepare_postal_human_review.py
```

Perintah tersebut menghasilkan:

- `data/interim/postal-review/jabar-postal-corroborated-review.csv` — 1.974
  baris kandidat dengan field reviewer;
- `data/interim/postal-review/jabar-postal-unresolved-review.csv` — 1.107
  baris unresolved dengan konteks cluster dan field reviewer; dan
- `data/interim/postal-review/jabar-postal-human-review-summary.json` — jumlah
  baris serta checksum input/output.

Reviewer hanya mengisi file di `data/interim/postal-review/`. Folder tersebut
diabaikan Git karena dapat berisi hasil layanan yang tidak boleh
didistribusikan.

## 3. Arti kelompok yang direview

### 3.1 Kandidat dua sumber — 1.974 baris

`postal_code_candidate` berisi nilai yang sama antara Kodepos.dev dan tepat
satu sumber lokal:

- 1.927 baris: Open Data Jabar + Kodepos.dev sama, Diskominfo berbeda;
- 47 baris: Diskominfo + Kodepos.dev sama, Open Data Jabar berbeda.

Nilai ini adalah hipotesis kuat, bukan jawaban final. Dua dataset yang sama
dapat memakai upstream lama yang sama, sedangkan Kodepos.dev adalah pihak
ketiga. Reviewer harus mencari bukti resmi yang cocok dengan keseluruhan rantai
desa/kelurahan, kecamatan, kabupaten/kota, dan provinsi.

### 3.2 Unresolved — 1.107 baris

Kelompok awal ini telah diperiksa ke Pos Indonesia pada 12 Agustus 2026. Sebanyak
1.105 baris memperoleh hasil exact dan dipromosikan melalui adjudikasi; Sambeng
dan Sirnabaya di Kecamatan Gunung Jati tetap unresolved karena tidak ada hasil
exact.

Kelompok ini terdiri atas:

| Pola | Jumlah | Tindakan awal |
|---|---:|---|
| Diskominfo dan Open Data Jabar sama; API berbeda | 482 | Verifikasi nilai dua sumber lokal ke sumber resmi |
| Ketiga sumber berbeda | 603 | Jangan memilih berdasarkan voting; cari sumber resmi exact-village |
| Open Data Jabar kosong; Diskominfo dan API berbeda | 19 | Periksa cakupan ODJ dan sumber resmi |
| Diskominfo kosong; ODJ dan API berbeda | 3 | Periksa cakupan Diskominfo dan sumber resmi |

Kolom `suggested_postal_code` pada worksheet unresolved hanya diisi otomatis
untuk dua keadaan:

- dua sumber pemerintah lokal sama; atau
- sudah ada spot-check Pos Indonesia terpilih.

Saran tersebut tetap belum diterima sampai reviewer melengkapi keputusan dan
bukti.

## 4. Kolom sumber: jangan diubah

Kolom berikut menjelaskan identitas dan evidence awal. Reviewer tidak boleh
mengubahnya:

| Kolom | Penjelasan |
|---|---|
| `village_code` | Kode Kemendagri canonical 10 digit bertitik |
| `province_name`, `city_name`, `district_name`, `village_name` | Rantai wilayah yang harus dicocokkan saat mencari |
| `postal_code_diskominfo` | Nilai pada snapshot Diskominfo |
| `postal_code_open_data_jabar` | Nilai pada Open Data Jabar 2023 |
| `postal_code_kodepos_dev` | Nilai audit internal Kodepos.dev |
| `postal_code_candidate` | Kandidat dua sumber; kosong bila tidak ada kandidat aman |
| `postal_candidates` | Seluruh nilai berbeda yang ditemukan |
| `source_ids`, `source_rows`, `snapshot` | Lineage untuk menelusuri data awal |
| `former_village_code` | Kode lama jika ada resolusi Kemendagri |

## 5. Kolom konteks review: jangan diubah

| Kolom | Penjelasan |
|---|---|
| `review_case_type` | `two_source_candidate`, `local_government_consensus_api_conflict`, atau `source_disagreement` |
| `suggested_postal_code` | Nilai yang perlu diuji, bukan nilai final |
| `suggestion_basis` | Alasan nilai disarankan atau alasan tidak ada saran |
| `unresolved_pattern` | Bentuk konflik/missing sumber |
| `district_cluster_id` | Kelompok kecamatan dan pola yang sama |
| `triplet_cluster_id` | Kelompok kombinasi nilai sumber yang sama |
| `affected_rows_if_same_pattern` | Ukuran pola, bukan izin menerapkan hasil ke seluruh cluster |
| `existing_pos_observation` | Hasil spot-check Pos yang sudah pernah dilakukan |
| `existing_pos_match` | Sumber awal yang sama dengan hasil Pos |

Satu hasil untuk wakil cluster tidak boleh otomatis diterapkan ke desa lain.
Kode pos dapat berbeda antar-desa meskipun ketiganya berada dalam kecamatan dan
pola sumber yang sama.

## 6. Kolom yang harus diisi reviewer

### `reviewer`

Nama atau ID reviewer yang dapat ditelusuri. Wajib ketika review dimulai.

### `review_status`

Gunakan salah satu nilai berikut:

- `pending` — belum diperiksa;
- `in_review` — sedang diperiksa;
- `needs_second_review` — keputusan pertama sudah ada dan perlu reviewer kedua;
- `completed` — bukti dan keputusan sudah lengkap; atau
- `blocked` — sumber resmi tidak tersedia atau hasil tetap ambigu.

### `review_decision`

Isi hanya salah satu:

- `accept_suggested` — bukti resmi mendukung `suggested_postal_code`;
- `accept_other` — bukti resmi mendukung nilai lain;
- `remain_unresolved` — bukti belum cukup atau hasil ambigu; atau
- `invalid_administrative_row` — rantai wilayah/kode perlu diperbaiki sebelum
  kode pos dapat dinilai.

### `reviewed_postal_code`

- Wajib berupa lima digit untuk `accept_suggested` atau `accept_other`.
- Harus sama dengan `suggested_postal_code` ketika keputusan
  `accept_suggested`.
- Harus kosong untuk `remain_unresolved` dan `invalid_administrative_row`.
- Jangan menulis `0`, `-`, `N/A`, atau kode pos perkiraan.

### Kolom evidence

- `evidence_source_name` — nama penerbit/sistem resmi;
- `evidence_url` — URL halaman yang benar-benar digunakan;
- `evidence_checked_at` — tanggal akses format `YYYY-MM-DD`;
- `evidence_scope` — gunakan `exact_village`, `district_only`, atau
  `ambiguous_results`; dan
- `review_notes` — ringkasan singkat cara mencocokkan nama serta alasan
  keputusan. Jangan menyalin alamat pelanggan atau data pribadi.

Keputusan accept hanya boleh memakai `evidence_scope=exact_village`.
`district_only` atau `ambiguous_results` harus berakhir sebagai
`remain_unresolved` atau `blocked`.

### Review kedua

- `second_reviewer` — reviewer berbeda dari reviewer pertama;
- `second_review_status` — `not_started`, `approved`, atau
  `changes_requested`.

Review kedua wajib untuk `accept_other`, konflik tiga nilai, perubahan kode
wilayah, dan bukti yang tidak memiliki URL permanen. Review kedua disarankan
untuk seluruh keputusan accept sebelum dataset dipromosikan.

## 7. Sumber evidence yang boleh dan tidak boleh digunakan

Urutan pilihan evidence:

1. pencarian resmi Kode Pos Pos Indonesia untuk konflik terpilih;
2. dokumen atau dataset resmi Pos Indonesia yang dapat ditelusuri;
3. dokumen resmi pemerintah kabupaten/kota atau kelurahan yang secara eksplisit
   mencantumkan kode pos dan wilayah exact; dan
4. konfirmasi tertulis resmi yang dapat diarsipkan serta diberi tanggal.

Google Search, blog, marketplace, direktori bisnis, peta komunitas, dan hasil
AI boleh membantu menemukan sumber, tetapi tidak boleh menjadi satu-satunya
bukti accept. Kodepos.dev sudah menjadi salah satu input dan tidak boleh dihitung
lagi sebagai bukti independen.

Portal Pos Indonesia hanya boleh diperiksa secara manual untuk baris terpilih.
Jangan melakukan bulk scraping. Simpan query, konteks hasil, URL, dan tanggal
akses. Jika pencarian nama menghasilkan banyak wilayah, cocokkan semua level
administratif; jangan memilih hanya karena kode pos tampak masuk akal.

Pengecualian snapshot tercatat diberikan project owner pada 11 Agustus 2026
untuk Section 2 dan 12 Agustus 2026 untuk Section 3. Pengecualian tersebut hanya
berlaku untuk proses internal yang sudah dijalankan dengan cache, delay dua
detik, batch 100 query, dan jeda antarbath. Ini bukan izin umum untuk scraping
ulang atau menaikkan laju akses.

## 8. Prosedur review per baris

1. Ambil satu baris berstatus `pending`, isi `reviewer`, lalu ubah menjadi
   `in_review`.
2. Pastikan `village_code` dan nama desa, kecamatan, kabupaten/kota, serta
   provinsi membentuk rantai yang benar.
3. Catat seluruh nilai pada tiga kolom sumber dan nilai yang disarankan.
4. Cari nama desa/kelurahan pada sumber resmi. Gunakan konteks kecamatan dan
   kabupaten/kota untuk memilih hasil exact.
5. Jika bukti mendukung nilai saran, pilih `accept_suggested`. Jika mendukung
   nilai lain, pilih `accept_other` dan isi lima digit tersebut.
6. Jika hasil kosong, hanya tingkat kecamatan, atau ambigu, pilih
   `remain_unresolved`; jangan menebak.
7. Isi seluruh kolom evidence dan `review_notes`.
8. Set `needs_second_review` bila aturan review kedua berlaku. Reviewer kedua
   memeriksa bukti secara independen.
9. Set `completed` hanya setelah field wajib lengkap dan, bila diwajibkan,
   `second_review_status=approved`.

## 9. Contoh keputusan

### Kandidat dua sumber

Pondok Rajeg memiliki Diskominfo `16913`, Open Data Jabar `16914`, dan
Kodepos.dev `16914`. `suggested_postal_code=16914`. Jika sumber resmi exact
menampilkan `16914`, isi `accept_suggested`. Jika sumber resmi menampilkan
`16913`, isi `accept_other` dengan `reviewed_postal_code=16913` dan minta review
kedua.

### Ketiga sumber berbeda

Cempaka, Plumbon memiliki `45655`, `45155`, dan `45158`. Spot-check Pos yang
sudah ada menampilkan `45655`, tetapi reviewer tetap harus mencatat evidence dan
keputusan eksplisit. Hasil ini tidak boleh diterapkan otomatis ke 14 desa lain
dalam triplet cluster yang sama.

### Dua sumber lokal sama, API berbeda

Limusnunggal memiliki Diskominfo dan Open Data Jabar `16829`, sedangkan API
`16820`. Worksheet menyarankan `16829`. Reviewer harus membuktikannya dengan
sumber official exact-village; kesamaan dua file lokal saja belum menyelesaikan
review.

## 10. Checklist sebelum menyerahkan hasil

- Semua baris yang disentuh mempunyai `reviewer` dan `review_status`.
- Nilai `review_decision` berasal dari daftar yang diizinkan.
- Kode pos hasil review tepat lima digit atau kosong sesuai keputusan.
- Setiap accept mempunyai sumber, URL, tanggal akses, scope exact, dan catatan.
- Tidak ada alamat pelanggan, nama pribadi, nomor telepon, API key, atau data
  sensitif dalam worksheet.
- Reviewer kedua berbeda dari reviewer pertama ketika diwajibkan.
- Hasil cluster tidak disalin otomatis ke baris lain.
- File sumber di `data/processed/` tidak berubah.

## 11. Setelah review selesai

Jangan langsung menyalin `reviewed_postal_code` ke dataset final. Hasil reviewer
harus melewati validasi schema, pemeriksaan reviewer kedua, deduplikasi evidence,
dan build adjudikasi yang akan mempromosikan hanya baris `completed` yang valid.
Build final kemudian dijalankan ulang dan perubahan jumlah
`usable_verified`, `candidate_review_only`, serta `unresolved_do_not_guess`
harus dijelaskan dalam summary dan changelog.

Untuk snapshot ini, jalankan berurutan:

```bash
python scripts/adjudicate_postal_human_review.py
python scripts/build_final_jabar_reference.py
```

Build adjudikasi menolak review yang tidak lengkap, scope selain
`exact_village`, keputusan di luar enum panduan, atau review kedua yang belum
disetujui. Build reference kemudian mempromosikan hanya status
`verified_consensus` dan `verified_adjudicated`.

Dataset belum disebut final penuh selama masih ada baris review terbuka. Artefak
`jabar-reference-v1-verified.json` tetap menjadi satu-satunya postal lookup yang
aman digunakan aplikasi dan sekarang berisi 5.957 baris (semua desa/kelurahan
Jawa Barat, tidak ada lagi baris `unresolved_do_not_guess`).
