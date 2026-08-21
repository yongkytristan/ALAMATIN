## PRD — ALAMATIN MVP Single-Address Review UI

## Spesifikasi implementasi untuk ALM-027 | Owner implementasi: JasonEvan

## 1. Ringkasan produk

ALAMATIN membantu admin fulfillment, UMKM, dan operator gudang memeriksa satu alamat Indonesia sebelum resi dibuat. UI harus mengubah keluaran parser, normalizer, validator, dan quality gate menjadi keputusan operasional yang jelas: siap diproses, perlu konfirmasi, atau tidak valid. Fokus MVP adalah review satu alamat dari input mentah sampai hasil final yang dapat disalin. UI tidak boleh melakukan koreksi diam-diam atau membuat suggestion terlihat sebagai nilai

final sebelum pengguna mengonfirmasinya.

## 2. Tujuan

- Pengguna dapat memasukkan satu alamat dan memperoleh hasil review tanpa bantuan developer.

- Pengguna memahami bagian alamat yang dikenali, diubah, bermasalah, atau membutuhkan konfirmasi.

- Pengguna dapat mengedit, mengonfirmasi, atau menolak suggestion lalu menjalankan validasi ulang.

- Hanya normalized address yang sudah final dan aman yang dapat disalin sebagai hasil operasional.

- UI melindungi PII dan tidak menyimpan raw address secara tidak perlu.

## 3. Non-goals MVP

- Login, akun pengguna, role management, dan halaman riwayat.

- Dashboard analitik, batch CSV, dan background job.

- Geocoding presisi, map matching, draggable pin, atau klaim lokasi terverifikasi.

- Risk score pengiriman atau klaim failed-delivery.

- Training model, perubahan label schema, atau koreksi reference data dari frontend.


## 4. Pengguna utama dan job-to-be-done

Pengguna utama adalah admin fulfillment, staf UMKM, dan operator gudang yang menerima alamat dari chat/form lalu harus memutuskan apakah alamat cukup aman untuk diproses. Job-to-be-done: “Ketika menerima alamat yang berantakan atau ambigu, saya ingin melihat komponen yang dikenali dan masalah kritisnya, lalu memperbaiki atau meminta konfirmasi

sebelum membuat resi.”

## 5. Alur pengguna utama

- Pengguna membuka halaman review dan melihat textarea alamat kosong.

- Pengguna menempel alamat lalu memilih Periksa alamat.

- UI menampilkan loading state dan mencegah submit ganda.

- UI menampilkan status utama, komponen alamat, provenance, issues, dan normalized address.

- Jika PERLU_KONFIRMASI, pengguna mengonfirmasi, menolak, atau mengedit suggestion.

- Setiap perubahan membuat hasil berstatus perlu validasi ulang.

- UI memanggil validasi ulang dan memperbarui status, issues, serta audit trail.

- Jika SIAP_DIPROSES, pengguna menyalin normalized address.

- Jika TIDAK_VALID, tombol salin hasil final dinonaktifkan dan UI menunjukkan tindakan berikutnya.

## 6. Struktur halaman

## 6.1 Header

- Nama produk ALAMATIN dan deskripsi singkat: pemeriksaan alamat sebelum fulfillment.

- Indikator health/dependency hanya bila endpoint health tersedia; jangan tampilkan detail sensitif.

## 6.2 Kartu input

- Textarea berlabel Alamat mentah dengan contoh non-PII sebagai placeholder.

- Counter karakter opsional, tombol Bersihkan, dan tombol utama Periksa alamat.

- Submit dinonaktifkan untuk input kosong/whitespace.

- Pesan validasi input tampil dekat field dan dapat dibaca screen reader.

## 6.3 Banner status

- SIAP_DIPROSES: label teks dan ikon sukses; normalized address boleh disalin.

- PERLU_KONFIRMASI: label teks dan ikon peringatan; jelaskan field yang belum final.


- TIDAK_VALID: label teks dan ikon error; jelaskan blocker dan tindakan yang mungkin.

- Status tidak boleh dibedakan hanya berdasarkan warna.

## 6.4 Review komponen alamat

Tampilkan sepuluh tipe entitas kanonik bila tersedia: JALAN, NOMOR, RT, RW, KELURAHAN,

KECAMATAN, KOTA_KABUPATEN, PROVINSI, KODEPOS, dan DETAIL_LOKASI.

- Setiap baris menampilkan nama field, nilai terdeteksi, source/provenance, dan status nilai.

- Gunakan istilah model_score, bukan confidence, sebelum kalibrasi tersedia.

- Bedakan nilai original, suggested, confirmed, rejected, dan user-edited secara visual serta tekstual.

- Highlight token di alamat harus konsisten dengan baris komponen dan tetap terbaca tanpa warna.

## 6.5 Panel issues dan klarifikasi

- Setiap issue menampilkan severity, pesan, affected fields, reason code, dan clarification question.

- Urutkan issue high severity sebelum medium dan low.

- Tindakan yang tersedia: Konfirmasi, Tolak, atau Edit nilai, sesuai contract backend.

- Jangan mengubah suggestion menjadi final hanya karena pengguna membuka atau melihatnya.

## 6.6 Normalized address

- Tampilkan hasil normalized dalam area terpisah dari input mentah.

- Labeli dengan jelas sebagai Final atau Belum final.

- Tombol Salin aktif hanya untuk hasil yang telah melewati gate yang disepakati.

- Berikan feedback singkat setelah penyalinan berhasil atau gagal.

## 6.7 Detail teknis opsional

- Bagian collapsible untuk model version, normalizer version, validator version, dan reference version.

- Jangan tampilkan raw log, stack trace, PII, secret, atau internal path.


## 7. State yang wajib diimplementasikan

- Empty: textarea kosong dan belum ada hasil.

- Loading: request berjalan, tombol submit disabled, dan ada indikator progres.

- Ready: status SIAP_DIPROSES dengan hasil final.

- Needs confirmation: status PERLU_KONFIRMASI dengan minimal satu tindakan eksplisit.

- Invalid: status TIDAK_VALID dengan blocker yang dapat dipahami.

- Dirty after edit: hasil lama ditandai usang sampai validasi ulang selesai.

- Input error: input kosong, terlalu panjang, atau schema request tidak valid.

- API error: timeout, network error, internal error, dan dependency unavailable memiliki pesan berbeda yang aman.

## 8. Aturan interaksi

- Gunakan POST /parse untuk pemeriksaan awal dan POST /validate untuk validasi setelah edit/konfirmasi, mengikuti contract final ALM-025/026.

- Frontend tidak menjalankan inference atau lookup sendiri.

- Cegah submit ganda dan abaikan response lama bila request yang lebih baru sudah dikirim.

- Setiap edit harus mempertahankan previous value untuk audit trail.

- Tidak ada auto-correction tanpa tindakan pengguna untuk suggestion yang memerlukan konfirmasi.

- Copy tidak boleh menyalin label UI, provenance, atau PII yang telah direduksi; hanya string normalized address final.

## 9. Privacy dan keamanan

- Jangan menaruh raw address pada URL, query string, analytics event, console log, atau error reporting.

- Jangan menyimpan raw address ke localStorage/sessionStorage secara default.

- Nama dan nomor telepon harus direduksi atau dimasking sesuai output PII backend.

- Gunakan fixture sintetis/non-PII untuk demo, screenshot, dan test.

- Structured error tidak boleh menampilkan stack trace atau payload mentah.

## 10. Responsive dan accessibility

- Desktop: input dan hasil dapat menggunakan dua kolom bila ruang cukup.

- Mobile: semua bagian menjadi satu kolom; tindakan utama tetap mudah dijangkau.

- Semua kontrol dapat digunakan dengan keyboard dan memiliki visible focus state.

- Setiap input mempunyai label; ikon mempunyai accessible name atau disembunyikan bila dekoratif.


- Gunakan semantic HTML, heading berurutan, aria-live untuk status request, dan kontras yang memadai.

- Target minimum: lebar 360 px tanpa horizontal scrolling pada konten utama.

## 11. Kontrak data yang dibutuhkan

Frontend menunggu schema final dari ALM-025. Minimal response yang dibutuhkan: status, redacted input/PII, components, normalized_address, issues, corrections/suggestions, provenance, confirmation state, previous values, serta version metadata. Jika contract backend belum tersedia, gunakan typed mock fixture yang bentuknya ditandai provisional. Jangan mengunci struktur komponen ke response sementara tanpa koordinasi

dengan owner ALM-025/026.

## 12. Skenario acceptance

- Alamat valid lengkap menghasilkan SIAP_DIPROSES dan tombol salin aktif.

- Konflik kode pos menghasilkan PERLU_KONFIRMASI dengan reason code, affected fields, dan pertanyaan spesifik.

- Kelurahan tidak ditemukan menghasilkan TIDAK_VALID atau PERLU_KONFIRMASI sesuai precedence backend, tanpa koreksi diam-diam.

- Input berisi nama/telepon tidak mengekspos nilai PII di UI atau log.

- Pengguna menolak suggestion; previous value tetap tersedia dan validasi diperbarui.

- Pengguna mengedit field; hasil lama menjadi dirty lalu status baru muncul setelah validasi.

- API timeout menampilkan retry yang aman tanpa kehilangan input saat sesi halaman aktif.

- Flow utama selesai dengan keyboard pada desktop dan tetap berfungsi pada viewport 360 px.

## 13. Deliverables Jason

- Implementasi halaman single-address review di direktori web/.

- Komponen UI untuk input, status, entity review, issues, actions, normalized output, dan error states.

- Typed API client dan fixture mock yang mengikuti ALM-025/026.

- Unit/component tests untuk state utama dan interaction rules.

- Minimal satu integration test untuk flow valid dan satu flow perlu konfirmasi.

- README web berisi setup, run, test, keputusan stack, dan known limitations.

- PR melalui branch feat/ui-single-address-review; jangan push langsung ke main.


## 14. Keputusan implementasi yang harus dicatat

- Frontend stack belum dibekukan. Rencana mengizinkan HTML/JS sederhana atau Vite + React. Rekomendasi: Vite + React + TypeScript untuk state interaktif, tetapi keputusan harus dicatat sebelum scaffold/dependency ditambahkan.

- Final JSON schema dan endpoint behavior menunggu ALM-025/026.

- Aturan final kapan tombol Salin aktif harus konsisten dengan quality gate ALM-024.

- Visual design system boleh sederhana; kejelasan status dan provenance lebih penting daripada dekorasi.

## 15. Definition of Done

- Seluruh task dan acceptance criteria issue ALM-027 terpenuhi.

- Tidak ada suggestion yang terlihat sebagai final tanpa konfirmasi.

- Semua state wajib dapat didemokan dengan fixture tetap.

- Test frontend lulus dan flow utama basic responsive serta keyboard-accessible.

- Tidak ada raw PII pada log, storage, URL, fixture, atau screenshot.

- PR direview dan siap diintegrasikan melalui ALM-028.

## 16. Sumber spesifikasi

PRD ini diturunkan dari ALM-027 serta dependency ALM-024, ALM-025, ALM-026, dan integrasi ALM-028; juga dari AIC Rencana Eksekusi Parser Alamat dan web/README.md. Jika terdapat konflik, issue dan contract backend yang sudah dibekukan menjadi sumber operasional utama.
