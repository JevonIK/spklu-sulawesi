# Panduan pengguna

## Menyiapkan aplikasi lokal

1. Aktifkan virtual environment dan dependency.
2. Salin `.env.example` menjadi `.env`.
3. Isi browser key, server key, dan Map ID sesuai panduan deployment.
4. Jalankan `python run.py`.
5. Buka `http://127.0.0.1:5000`.

Status **Sistem siap** berarti dataset, browser Maps, dan endpoint rekomendasi
telah tersedia. Jika formulir tetap nonaktif, baca pesan status dan bagian
troubleshooting di bawah.

## Membuat rencana perjalanan

1. Pilih lokasi awal dari hasil Place Autocomplete.
2. Pilih lokasi tujuan yang berbeda.
3. Masukkan SOC saat ini dan jangkauan maksimum kendaraan dalam kilometer.
4. Centang satu atau beberapa konektor yang benar-benar dapat digunakan
   kendaraan: AC Type 2, CCS2, CHAdeMO, atau GB/T. Angka pada pilihan
   menunjukkan jumlah lokasi pada dataset.
5. Tentukan SOC minimum sebagai cadangan baterai terendah dan target SOC sebagai
   batas SOC keberangkatan setelah berhenti di SPKLU.
6. Pastikan lokasi awal dan tujuan sudah dipilih dari daftar saran. Tombol
   **Cari rekomendasi SPKLU** baru aktif setelah keduanya tersimpan.
7. Pilih tombol tersebut satu kali dan tunggu hasil.

Jangan menekan tombol berulang selama loading. Setiap rekomendasi merupakan
pengujian live yang dapat memakai Compute Routes dan elemen Route Matrix.

## Membaca hasil

Hasil **Rute aman ditemukan** menampilkan:

- jarak dan waktu berkendara;
- jumlah perhentian;
- SOC akhir;
- urutan leg dan SPKLU;
- SOC berangkat dan tiba pada setiap leg; serta
- statistik kandidat, graf, DP, dan pemakaian API.

Pengisian dari SOC tiba menuju SOC berangkat dimodelkan sebagai perubahan state.
Sistem tidak menghitung lama pengisian.

Hasil **Rute aman belum ditemukan** bukan selalu error aplikasi. Status ini
berarti graf tidak memiliki rangkaian leg yang memenuhi jangkauan, SOC minimum,
konektor, dan parameter backend saat itu. Pengguna dapat memeriksa kembali jenis
konektor atau jangkauan kendaraan, tetapi tidak boleh mengabaikan batas aman
kendaraan aktual.

## Makna pengaturan kendaraan

- **SOC saat ini** adalah persentase baterai sebelum perjalanan dimulai.
- **Jangkauan maksimum** adalah jarak nominal kendaraan saat baterai 100%.
- **SOC minimum** adalah batas tiba terendah yang diizinkan model.
- **Target SOC** adalah batas maksimum keberangkatan yang dievaluasi setelah
  berhenti di SPKLU, bukan estimasi waktu pengisian.
- **Jenis konektor** dapat dipilih lebih dari satu. Sistem mempertimbangkan
  SPKLU yang mendukung sedikitnya satu konektor pilihan.

Safety factor 0,9, radius koridor 10 km, interval SOC 5%, dan langkah sampling
5 km menjadi default backend. Nilai ini tidak ditampilkan pada formulir umum.
Peneliti tetap dapat mengubahnya melalui skenario eksperimen, bukan melalui
interaksi pengguna harian.

## Troubleshooting

| Gejala | Pemeriksaan |
|---|---|
| Form tetap nonaktif | periksa browser key, server key, restriction referrer, Maps JavaScript API, Places API, dan Routes API |
| Tombol pencarian tetap nonaktif | pilih lokasi awal dan tujuan dari daftar saran Google; teks yang hanya diketik belum menyimpan koordinat |
| Tombol nonaktif setelah lokasi dipilih | pastikan sedikitnya satu checkbox konektor masih dicentang |
| Saran lokasi gelap/tidak terbaca | muat ulang aset aplikasi terbaru; widget dipaksa memakai skema warna terang |
| Rute terlihat tetapi petunjuk awal masih menutupi peta | muat ulang aset JavaScript terbaru; overlay semestinya hilang saat rute tersedia |
| Peta menampilkan authorization error | tambahkan origin lengkap termasuk port ke website restriction |
| HTTP 503 | isi server key dan restart aplikasi |
| HTTP 400 | perbaiki field yang disebut pada respons validasi |
| HTTP 429 | tunggu request aktif selesai atau reset quota; jangan retry berulang |
| HTTP 502 | periksa jaringan, Routes API, billing, restriction server key, dan quota |
| Rute tidak feasible | baca reason dan statistik graf; ini dapat menjadi hasil penelitian yang valid |
| Perhitungan lama | tunggu satu request selesai; kandidat/edge dan latensi Google memengaruhi waktu |

Sebelum mencoba ulang error live, periksa quota Cloud dan jangan melakukan retry
tanpa batas. Daftar hard limit berada pada `docs/google_maps_api_limits.md`.
