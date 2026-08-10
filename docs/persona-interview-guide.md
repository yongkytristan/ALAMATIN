# Panduan wawancara persona dan pain points

Dokumen ini digunakan untuk menjalankan ALM-003. Tujuannya adalah memvalidasi
workflow verifikasi alamat sebelum resi dibuat, bukan menjual atau menguji konsep
ALAMATIN. Issue belum dapat dianggap selesai hanya karena panduan ini tersedia;
minimal tiga wawancara harus dijalankan, dianonimkan, dan disintesis.

## 1. Target partisipan

Rekrut 3–5 orang yang saat ini pernah menangani alamat pesanan, misalnya:

- admin fulfillment seller atau UMKM;
- staf gudang yang memeriksa data pengiriman;
- staf operasional perusahaan logistik;
- pemilik usaha yang masih menjalankan fulfillment sendiri.

Jangan merekrut hanya berdasarkan jabatan. Gunakan pertanyaan penyaring berikut:

1. Dalam tiga bulan terakhir, apakah Anda memeriksa atau memperbaiki alamat
   sebelum pesanan dikirim?
2. Apakah Anda pernah memutuskan bahwa alamat sudah siap dibuatkan resi?
3. Apakah Anda pernah menghubungi pelanggan karena alamat belum jelas?
4. Kira-kira berapa alamat yang Anda tangani pada hari biasa dan hari sibuk?

Partisipan sesuai jika menjawab "ya" pada pertanyaan 1 dan setidaknya salah satu
dari pertanyaan 2 atau 3. Catat volume sebagai rentang; jangan meminta nama
pelanggan, alamat rumah, nomor telepon, atau data pesanan aktual.

## 2. Aturan privasi dan consent

- Gunakan ID `P01`, `P02`, dan seterusnya; jangan simpan nama asli di repository.
- Jangan meminta partisipan menunjukkan alamat pelanggan aktual. Gunakan contoh
  sintetis jika perlu mendemonstrasikan workflow.
- Jangan merekam layar, suara, atau video tanpa consent terpisah.
- Catatan yang masuk Git harus sudah dianonimkan dan tidak memuat nama bisnis,
  nama orang, nomor telepon, alamat pribadi, kredensial, atau identifier pesanan.
- Simpan rekaman mentah, jika diizinkan, di lokasi terbatas di luar repository;
  tetapkan siapa yang dapat mengakses dan kapan rekaman dihapus.

### Skrip pembukaan

> Kami sedang mempelajari proses pemeriksaan alamat sebelum pengiriman. Kami
> tidak sedang menilai kinerja Anda. Jangan menyebutkan nama, nomor telepon,
> alamat pelanggan, atau informasi pesanan aktual. Catatan akan dianonimkan.
> Anda boleh melewati pertanyaan atau menghentikan wawancara kapan saja. Apakah
> Anda bersedia melanjutkan?

Catat `consent_interview: yes|no`. Hentikan sesi jika jawabannya `no`.

Tanyakan izin kutipan secara terpisah pada akhir sesi. Persetujuan mengikuti
wawancara tidak otomatis berarti persetujuan untuk dikutip atau direkam.

## 3. Metadata sesi

Isi sebelum atau segera setelah wawancara:

```yaml
participant_id: P01
interview_date: YYYY-MM-DD
interviewer_id: TEAM-XX
participant_role: fulfillment-admin|warehouse-staff|logistics-ops|business-owner|other
business_scale: micro|small|medium|large|unknown
daily_address_volume: 1-10|11-50|51-200|201+|unknown
experience_length: <1y|1-3y|3y+|unknown
consent_interview: yes|no
consent_recording: yes|no|not-requested
consent_anonymous_quote: yes|no
recording_retention_until: YYYY-MM-DD|not-recorded
```

Jangan isi `participant_role` berdasarkan asumsi pewawancara; konfirmasi melalui
jawaban partisipan.

## 4. Alur wawancara

Durasi sasaran 30–40 menit. Minta contoh kejadian terbaru agar jawaban tidak
berhenti pada pendapat umum. Probe yang aman: "Apa yang terjadi setelah itu?",
"Bagaimana Anda mengetahuinya?", dan "Bisa beri contoh tanpa data pribadi?".

### A. Peran dan konteks kerja — 5 menit

1. Apa peran Anda dalam proses dari pesanan masuk sampai paket diserahkan ke
   kurir?
2. Bagian mana yang menjadi keputusan Anda sendiri dan bagian mana yang harus
   dikonfirmasi kepada orang lain?
3. Dari kanal apa alamat biasanya diterima, dan dalam format seperti apa?
4. Pada hari biasa dan hari sibuk, kira-kira berapa alamat yang Anda tangani?
5. Alat apa yang saat ini digunakan: dashboard marketplace, spreadsheet, chat,
   peta, sistem gudang, atau alat lain?

### B. Workflow aktual sebelum resi — 8 menit

6. Ceritakan kejadian terbaru ketika Anda memproses alamat dari awal sampai
   memutuskan alamat siap dibuatkan resi.
7. Langkah apa saja yang dilakukan, secara berurutan?
8. Informasi minimum apa yang harus tersedia sebelum Anda berani membuat resi?
9. Field mana yang selalu diperiksa, dan mana yang hanya diperiksa saat ada
   masalah?
10. Siapa yang membuat keputusan final bahwa alamat siap diproses?
11. Pada titik mana Anda menggunakan pencarian web, peta, kode pos, atau bertanya
    kepada pelanggan?
12. Apa yang Anda lakukan ketika dua sumber memberikan informasi wilayah atau
    kode pos yang berbeda?

### C. Error dan alamat bermasalah — 8 menit

13. Ceritakan kejadian terbaru ketika sebuah alamat tidak dapat langsung
    diproses. Hilangkan seluruh data pribadi dari contoh.
14. Masalah apa yang paling sering muncul: field hilang, typo, singkatan, RT/RW,
    gang, landmark, kode pos, konflik wilayah, atau hal lain?
15. Bagaimana masalah tersebut pertama kali diketahui?
16. Masalah apa yang paling mudah terlewat tetapi berdampak besar?
17. Pernahkah koreksi yang terlihat masuk akal ternyata salah? Apa penyebabnya?
18. Apa konsekuensi operasional dari alamat yang salah atau ambigu—misalnya
    waktu ulang, eskalasi, penundaan, atau pekerjaan manual tambahan?
19. Dari masalah yang disebutkan, mana yang sering, mana yang jarang, dan mana
    yang paling berat dampaknya?

### D. Eskalasi dan klarifikasi pelanggan — 5 menit

20. Kondisi apa yang membuat Anda harus menghubungi pelanggan?
21. Pertanyaan apa yang biasanya diajukan agar alamat menjadi cukup jelas?
22. Kanal apa yang digunakan dan siapa yang bertanggung jawab melakukan kontak?
23. Apa yang dilakukan jika pelanggan lambat merespons atau tidak merespons?
24. Apakah ada kasus yang tetap diproses walau belum jelas? Siapa yang menyetujui
    dan berdasarkan aturan apa?
25. Apakah hasil klarifikasi dicatat? Jika ya, di mana dan siapa yang dapat
    melihatnya?

### E. Waktu, volume, dan keberhasilan — 4 menit

26. Berapa lama pemeriksaan satu alamat yang normal dan satu alamat bermasalah?
    Mintalah rentang atau estimasi; jangan mengubahnya menjadi angka presisi
    buatan.
27. Langkah mana yang biasanya menghabiskan waktu paling lama?
28. Apa yang berubah ketika volume sedang tinggi?
29. Bagaimana tim menilai bahwa proses verifikasi alamat berjalan baik?
30. Jika hanya satu bagian workflow yang dapat diperbaiki, bagian apa yang paling
    bernilai dan mengapa?

### F. Privasi, kepercayaan, dan penggunaan layanan eksternal — 5 menit

31. Data pribadi apa yang terlihat saat memeriksa alamat, dan siapa yang boleh
    mengaksesnya?
32. Apakah alamat atau nomor telepon pernah tersalin ke chat, spreadsheet, log,
    atau layanan pihak ketiga? Mengapa?
33. Apa kekhawatiran Anda jika alamat dikirim ke layanan peta atau geocoding?
34. Kapan consent pelanggan diperlukan menurut praktik atau kebijakan Anda?
35. Data apa yang seharusnya disamarkan, tidak dicatat, atau dihapus setelah
    proses selesai?
36. Bukti atau kontrol apa yang diperlukan agar Anda percaya pada alat bantu
    pemeriksaan alamat?

### G. Batas keputusan dan kebutuhan minimum — 3 menit

37. Sebelum resi dibuat, keputusan minimum apa saja yang harus sudah jelas?
38. Perubahan seperti apa yang boleh dilakukan otomatis, dan perubahan apa yang
    wajib dikonfirmasi manusia?
39. Informasi apa yang harus ditampilkan agar saran koreksi dapat diperiksa?
40. Dalam kondisi apa sistem sebaiknya mengatakan "perlu konfirmasi" atau
    "tidak valid" daripada menebak?

### H. Prioritas akhir — 2 menit

41. Dari semua masalah yang dibahas, sebutkan lima yang paling penting.
42. Urutkan kelimanya berdasarkan dampak operasional, lalu jelaskan alasannya.
43. Apakah ada hal penting tentang verifikasi alamat yang belum ditanyakan?

### Skrip penutup dan izin kutipan

> Kami mungkin ingin menggunakan kutipan singkat yang sudah dianonimkan dalam
> dokumentasi atau proposal. Kutipan tidak akan memuat nama, perusahaan, alamat,
> atau identifier pribadi. Apakah Anda mengizinkannya?

Catat `consent_anonymous_quote: yes|no`. Jika `no`, jawaban masih boleh dipakai
untuk sintesis agregat, tetapi jangan disalin sebagai kutipan.

## 5. Template catatan per partisipan

Simpan catatan anonim sebagai `docs/research/interviews/PXX.md` setelah sesi.
Jangan memasukkan transkrip mentah ke Git.

```markdown
# Interview PXX

## Session metadata

<!-- Salin metadata anonim dari bagian 3. -->

## Current workflow

1. ...

## Evidence records

| Evidence ID | Question | Type | Sanitized evidence | Frequency | Impact | Confidence |
|---|---:|---|---|---|---|---|
| PXX-E01 | Q6 | observed/paraphrase/quote | ... | ... | ... | high/medium/low |

## Minimum decisions before waybill

- ...

## Candidate pain points

| Pain point | Evidence IDs | Participant rank | Notes |
|---|---|---:|---|
| ... | PXX-E01 | 1 | ... |

## Privacy concerns

- ...

## Actual observations

- ...

## Team assumptions requiring validation

- ...

## Contradictions and follow-ups

- ...
```

Gunakan kategori bukti berikut:

- `observed`: tindakan terlihat dalam demonstrasi dengan data sintetis;
- `quote`: kata-kata partisipan, hanya jika izin kutipan diberikan;
- `paraphrase`: rangkuman jawaban partisipan;
- `assumption`: interpretasi tim yang belum didukung bukti.

Jangan menyajikan `assumption` sebagai temuan.

## 6. Template sintesis setelah minimal tiga wawancara

Buat `docs/research/persona-validation.md` dengan struktur berikut:

```markdown
# Persona validation synthesis

## Sample and limitations

| Participant | Role | Volume range | Experience | Interview date |
|---|---|---|---|---|

## Validated current workflow

| Step | Actors | Inputs | Decision | Tools | Evidence IDs | Exceptions |
|---|---|---|---|---|---|---|

## Top five pain points

| Rank | Pain point | Participants supporting | Frequency | Impact | Evidence IDs | Contradictions |
|---:|---|---:|---|---|---|---|

## Minimum decisions before waybill

| Decision | Supporting participants | Evidence IDs | Confidence |
|---|---:|---|---|

## Primary persona

- Role and context:
- Goals:
- Current workflow:
- Constraints:
- Privacy concerns:
- Evidence IDs:
- Known limitations:

## Evidence-backed problem statement

<!-- Pisahkan fakta, inferensi, dan hal yang belum diketahui. -->

## Assumptions rejected, supported, or unresolved

| Assumption | Result | Evidence IDs | Next action |
|---|---|---|---|

## Implications for ALM-004

- Positioning implications:
- P0 scope implications:
- Claims that remain unsupported:
```

Top five pain points harus berasal dari lintas-partisipan. Laporkan jumlah
partisipan pendukung dan kontradiksi; jangan menghilangkan pendapat minoritas.

## 7. Pemetaan ke ALM-003

| Kebutuhan issue | Bagian panduan | Bukti selesai |
|---|---|---|
| Rekrut 3–5 target-like users | Bagian 1 | Metadata minimal tiga partisipan yang sesuai screener |
| Workflow saat ini | Q6–Q12 | Workflow dengan evidence ID |
| Error umum | Q13–Q19 | Kategori, frekuensi, dampak, dan contoh anonim |
| Eskalasi pelanggan | Q20–Q25 | Trigger, kanal, owner, timeout, dan pencatatan |
| Waktu verifikasi | Q26–Q30 | Rentang waktu dan bottleneck yang dinyatakan partisipan |
| Kekhawatiran privasi | Q31–Q36 | Risiko, consent, akses, redaksi, dan retensi |
| Observasi vs asumsi | Bagian 5–6 | Evidence record dan assumption register terpisah |
| Top 5 pain points | Q41–Q42 dan Bagian 6 | Ranking lintas-partisipan dengan evidence ID |
| Keputusan minimum sebelum resi | Q8 dan Q37–Q40 | Tabel keputusan dan bukti pendukung |
| Izin kutipan | Skrip penutup | Consent tercatat per partisipan |
| Minimal 3 wawancara anonim | Bagian 2–3 | P01–P03 atau lebih tanpa PII |
| Persona dan problem statement berbukti | Bagian 6 | Keduanya menyertakan evidence ID dan keterbatasan |
| Temuan dapat ditelusuri tanpa PII | Bagian 5–6 | Synthesis → evidence ID → catatan anonim |

## 8. Checklist penyelesaian Issue #3

- [ ] Sebanyak 3–5 partisipan lolos screener.
- [ ] Consent wawancara tercatat untuk setiap partisipan.
- [ ] Minimal tiga wawancara selesai.
- [ ] Semua catatan yang masuk repository telah dianonimkan.
- [ ] Izin kutipan tercatat dan hanya kutipan berizin yang digunakan.
- [ ] Workflow, error, eskalasi, waktu, dan privasi memiliki evidence ID.
- [ ] Observasi aktual dipisahkan dari asumsi tim.
- [ ] Top five pain points disintesis beserta dukungan dan kontradiksi.
- [ ] Keputusan minimum sebelum resi dirangkum.
- [ ] Persona utama dan problem statement memiliki bukti wawancara.
- [ ] Limitasi sampel dan temuan yang belum pasti dilaporkan.
