# Sintesis Wawancara Persona dan Pain Points ALAMATIN

## Status studi

Empat wawancara aktual dilakukan melalui telepon dan dicatat secara tertulis tanpa rekaman audio, sesuai pilihan masing-masing narasumber. Seluruh catatan menggunakan kode anonim dan tidak memuat nama narasumber, nama toko, alamat pelanggan, nomor telepon, atau nomor pesanan.

Wawancara mengikuti [panduan workflow alamat yang netral](../neutral-address-workflow-interview.md). Pertanyaan memisahkan pengalaman langsung, perkiraan narasumber, dan skenario hipotetis pemeriksaan sebelum pengiriman.

| Kode | Tanggal | Profil anonim | Skala operasional |
|---|---|---|---|
| `R01` | 15 Agustus 2026 | Admin fulfillment sekaligus staf gudang marketplace | Toko kecil, sekitar 30–50 pesanan per hari |
| `R02` | 15 Agustus 2026 | Pemilik dan pembuat produk press-on nails | Usaha rumahan mikro, sekitar 11–50 pesanan per hari |
| `R03` | 16 Agustus 2026 | Pemilik toko bahan kue offline dan online | Kecil–menengah, sekitar 60–100 pesanan online per hari |
| `R04` | 22 Agustus 2026 | Pemilik dapur makanan siap saji dan frozen food | Usaha rumahan mikro, sekitar 15–40 pesanan per hari |

Catatan sumber:

- [`R01`](interviews/R01-fulfillment.md)
- [`R02`](interviews/R02-press-on-nails.md)
- [`R03`](interviews/R03-toko-bahan-kue.md)
- [`R04`](interviews/R04-makanan-online.md)

## Persona utama

Persona utama ALAMATIN adalah operator sisi seller yang memproses pesanan sebelum diserahkan kepada kurir: admin fulfillment, staf gudang, atau pemilik UMKM yang merangkap pekerjaan operasional. Mereka dapat melihat alamat dan memutuskan apakah pesanan diteruskan atau ditahan, tetapi umumnya tidak dapat mengubah alamat yang sudah terkunci di marketplace.

Variasi konteks memengaruhi besar dampak. Produk custom milik `R02` sulit dijual ulang setelah retur, sedangkan bahan makanan milik `R03` dan `R04` sensitif terhadap keterlambatan. `R04` juga membutuhkan kesesuaian titik peta untuk pengiriman instan. Walaupun demikian, keempat narasumber mengalami batasan operasional yang serupa: masalah alamat diketahui terlambat dan tindakan seller terbatas.

## Problem statement berbasis wawancara

Operator seller membutuhkan pemeriksaan alamat yang singkat dan dapat ditindaklanjuti sebelum pesanan diproses, karena saat ini alamat sering langsung digunakan untuk mencetak resi, sedangkan seller tidak memiliki kewenangan untuk memperbaiki data setelah pesanan terkunci. Peringatan harus menyebut komponen yang bermasalah dan mengarahkan konfirmasi kepada pihak yang berwenang, tanpa melakukan koreksi penting secara diam-diam.

## Lima pain points utama

1. **Masalah diketahui terlalu terlambat.** Keempat narasumber menggambarkan alamat yang biasanya baru diperhatikan setelah kurir kesulitan mencari lokasi atau paket kembali. Pemeriksaan paling berguna saat checkout atau ketika pesanan baru masuk, sebelum pencetakan resi dan packing.
2. **Seller dapat melihat tetapi tidak dapat memperbaiki alamat.** Keempat narasumber menyatakan alamat yang sudah masuk ke sistem tidak dapat diedit dari sisi seller. Peringatan tanpa tindakan atau jalur konfirmasi berisiko diabaikan.
3. **Informasi kegagalan tidak spesifik.** Status seperti alamat tidak lengkap atau penerima tidak ditemukan tidak menjelaskan komponen yang salah, upaya kurir, atau tindakan berikutnya. Operator kemudian harus bertanya kepada pembeli tanpa konteks yang cukup.
4. **Penanda lokasi, konsistensi wilayah, kontak, dan titik peta sering menjadi informasi minimum.** Nomor rumah, blok, kamar, atau patokan; kecamatan dan kode pos yang konsisten; nomor telepon yang dapat dihubungi; serta pinpoint untuk pengiriman instan berulang kali disebut sebagai dasar keputusan.
5. **Insentif dan dampak operasional memperbesar masalah.** Pembatalan oleh seller dapat dianggap merugikan performa toko, sementara retur menambah pekerjaan dan dapat merusak produk custom atau mudah rusak. Besarnya frekuensi dan kerugian hanya merupakan laporan narasumber dan belum diverifikasi secara independen.

## Keputusan minimum sebelum pesanan diproses

Hasil lintas wawancara menunjukkan bahwa operator setidaknya perlu mengetahui:

- apakah alamat menunjuk satu tujuan yang cukup spesifik;
- apakah penanda bangunan atau lokasi tersedia;
- apakah rantai wilayah dan kode pos konsisten;
- apakah nomor kontak dapat digunakan untuk klarifikasi;
- untuk pengiriman instan, apakah titik peta selaras dengan alamat tertulis;
- siapa yang berwenang memperbaiki atau mengonfirmasi nilai bermasalah.

ALAMATIN tidak boleh mengklaim bahwa suatu alamat menyebabkan kegagalan pengiriman hanya dari sinyal-sinyal tersebut. Sistem hanya dapat menunjukkan kelengkapan, konflik, ambiguitas, dan kebutuhan konfirmasi berdasarkan bukti yang tersedia.

## Observasi aktual dan asumsi

### Observasi yang konsisten dalam catatan

- Seluruh narasumber terlibat langsung dalam pemrosesan pesanan dan serah terima kepada kurir.
- Alamat umumnya tidak diperiksa secara sistematis sebelum resi dicetak.
- Seller tidak memiliki akses untuk mengubah alamat yang sudah terkunci.
- Masalah biasanya diketahui melalui kurir, status aplikasi, atau paket retur.
- Narasumber menginginkan pesan sederhana yang menyebut bagian bermasalah, bukan skor tanpa penjelasan.
- Koreksi substantif seperti nomor rumah atau titik peta harus dikonfirmasi, sedangkan perapian format sederhana dapat diperlakukan berbeda.
- Semua narasumber mengkhawatirkan penyebaran nama, nomor telepon, atau alamat pelanggan ke layanan lain.

### Asumsi atau klaim yang belum terverifikasi

- Frekuensi retur dan persentase kasus yang disebabkan oleh alamat adalah perkiraan narasumber, bukan hasil audit data pengiriman.
- Penilaian bahwa alamat merupakan penyebab kegagalan sering dibuat setelah membaca alamat paket retur; status kurir tidak selalu membuktikan penyebabnya.
- Besaran kerugian, penalti, dan dampak terhadap performa toko belum diverifikasi terhadap laporan marketplace atau ekspedisi.
- Efektivitas ALAMATIN dalam mengurangi retur, waktu penanganan, atau kerugian belum diuji melalui user study terkontrol.
- Validitas nomor telepon, ketersediaan WhatsApp, dan akurasi titik peta berada di luar kemampuan parser alamat berbasis teks kecuali ada sumber dan persetujuan tambahan.

## Implikasi scope ALAMATIN

### P0

- Memeriksa kelengkapan dan konsistensi komponen alamat sebelum fulfillment.
- Menampilkan komponen bermasalah, alasan, dan pertanyaan klarifikasi.
- Memisahkan koreksi format deterministik dari saran yang wajib dikonfirmasi.
- Mengembalikan status operasional `SIAP_DIPROSES`, `PERLU_KONFIRMASI`, atau `TIDAK_VALID` berdasarkan aturan yang dapat diaudit.
- Melindungi PII dalam log, tampilan, dan bukti pengujian.

### Di luar klaim yang diizinkan saat ini

- Menyatakan bahwa alamat tertentu pasti menyebabkan gagal kirim.
- Mengklaim penurunan tingkat retur atau biaya tanpa evaluasi terkontrol.
- Menyatakan lokasi telah terverifikasi tanpa bukti geospasial yang sesuai.
- Menghasilkan risk score pengiriman atau confidence yang belum dikalibrasi.
- Mengubah alamat penting secara otomatis tanpa konfirmasi pengguna.

## Kesimpulan

Empat wawancara memenuhi kebutuhan jumlah minimum dan mendukung persona operator seller serta problem statement pemeriksaan alamat pra-fulfillment. Bukti ini cukup untuk keputusan scope produk, tetapi belum cukup untuk klaim kausal mengenai kegagalan pengiriman atau dampak bisnis. Klaim dampak harus menunggu user study dan evaluasi terpisah.
