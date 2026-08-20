# Provenance dan lisensi data

Dokumen ini membedakan identitas teknis dataset dari asal serta izin hukumnya.
Checksum dapat membuktikan bahwa dua proses membaca byte yang sama, tetapi tidak
membuktikan siapa pembuat data, kapan data dikumpulkan, apakah data lengkap, atau
apakah data boleh didistribusikan.

## Status yang dapat dinyatakan saat ini

| Atribut | Status |
|---|---|
| Berkas kandidat saat ini | `dataset_spklu_sulawesi.csv` |
| SHA-256 | `24992e1225209ed5a2833b8722be6bfabfc94cdc55f795acdf5edf10c21ffa85` |
| Ukuran logis | 150 baris sumber; 149 node lokasi setelah konsolidasi |
| Cakupan yang dinyatakan | Enam provinsi di Pulau Sulawesi |
| Cara diperoleh proyek | Disediakan oleh pemilik penelitian (`user_supplied`) |
| Penyedia/pembuat asli | Belum diketahui |
| URL atau sitasi sumber | Belum diketahui |
| Tanggal snapshot | Belum diketahui |
| Metode pengumpulan/verifikasi | Belum diketahui |
| Status lisensi | `unknown` |
| Hak redistribusi | Belum dikonfirmasi |
| Status provenance | `incomplete` |

Nilai kosong tersebut disengaja. Jangan menggantinya dengan dugaan seperti
“data resmi PLN”, “open data”, atau tanggal commit pertama tanpa bukti primer.
Sampai bukti tersedia, dataset hanya dapat disebut sebagai dataset yang diberikan
oleh pemilik penelitian dan dipakai oleh prototipe.

## Rantai artefak

Rantai audit kandidat 0.15.0 memakai empat tingkat yang berbeda:

1. `dataset_metadata.json` mencatat identitas dataset, transformasi yang
   diketahui, status provenance, status lisensi, dan keterbatasan;
2. `release_manifest.json` mengunci checksum metadata, dataset, skenario,
   dependency, source aplikasi, parameter algoritma, serta hard limit kandidat;
3. manifest penelitian menghubungkan snapshot notebook yang dilacak ke laporan
   live sumber dan versi aplikasi penghasilnya; dan
4. `notebooks/data/provenance.json` mempertahankan checksum laporan historis dan
   snapshot analisis offline.

Baseline live berasal dari aplikasi 0.9.2 dan sensitivitas dari aplikasi 0.10.0,
keduanya memakai schema laporan 2 dengan definisi skenario schema 1 tertanam.
Versi analisis 0.15.0 tidak boleh diatribusikan sebagai penghasil kedua run
tersebut. Definisi skenario saat ini memakai schema 2 dan laporan live baru
memakai schema 3 dengan provenance lebih lengkap. Kekosongan metadata pada
laporan lama, termasuk langkah sampling rute, tetap ditandai tidak tercatat dan
tidak direkonstruksi dari default versi baru.
Kedua laporan lama juga tidak merekam hash dataset; kecocokan jumlah baris/node
tidak membuktikan bahwa byte datasetnya identik dengan kandidat sekarang.

Laporan mentah historis disimpan lokal dan diabaikan Git. Checksum yang dicatat
memungkinkan pemeriksaan bila berkas itu tersedia, tetapi clone repository saja
tidak membuktikan keberadaan laporan mentah. Snapshot CSV yang dilacak adalah
turunan terverifikasi, bukan pengganti arsip sumber.

## Tindakan yang harus dilakukan pemilik penelitian

Sebelum paper atau dataset dipublikasikan:

1. identifikasi pembuat atau penyedia asli dataset;
2. simpan URL, surat, email, dokumen serah-terima, atau bukti primer lain;
3. catat tanggal snapshot dan rentang waktu pengumpulan;
4. jelaskan metode pengumpulan, pembersihan, geocoding, dan verifikasi;
5. konfirmasi lisensi serta apakah CSV boleh dimasukkan ke repository publik;
6. tentukan format sitasi dan versi dataset;
7. perbarui field kosong pada `dataset_metadata.json` hanya berdasarkan bukti;
8. hitung ulang checksum metadata dan manifest, lalu jalankan audit offline; dan
9. jika izin redistribusi tidak diperoleh, keluarkan CSV dari distribusi publik
   dan sediakan prosedur memperoleh data secara sah.

Untuk naskah sebelum tindakan itu selesai, gunakan formulasi terbatas seperti:
“Penelitian menggunakan dataset SPKLU Sulawesi yang disediakan oleh pemilik
penelitian; sumber asli, tanggal snapshot, dan lisensinya belum terdokumentasi.”
Jangan menyebut data lengkap, resmi, terkini, atau bebas digunakan.

## Transformasi yang diketahui

CSV tidak ditulis ulang oleh aplikasi. Pada saat dibaca, sistem:

- menormalisasi label konektor di memori;
- mempertahankan dua unit pada koordinat identik sebagai unit terpisah, tetapi
  mengonsolidasikannya menjadi satu node algoritma; dan
- menurunkan label jaringan Hyundai, Wuling, dan Toyota/Lexus dari penanda
  eksplisit pada nama lokasi.

Transformasi tersebut mendukung reproduksibilitas komputasi, tetapi tidak
memvalidasi status operasional, akses dealer, daya, tarif, atau ketersediaan
real-time setiap charger.
