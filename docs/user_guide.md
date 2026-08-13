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
4. Pastikan kendaraan memakai konektor CCS2.
5. Biarkan parameter penelitian pada nilai default untuk baseline, atau buka
   **Pengaturan penelitian** untuk mengubah safety factor, radius koridor, dan
   interval SOC.
6. Pilih **Cari rekomendasi SPKLU** satu kali dan tunggu hasil.

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
konektor, dan parameter saat itu. Pengguna dapat mengevaluasi kendaraan dengan
jangkauan berbeda atau parameter penelitian lain, tetapi tidak boleh mengabaikan
batas aman kendaraan aktual.

## Makna parameter penelitian

- **Safety factor** menurunkan jangkauan nominal untuk membentuk margin aman.
- **Radius koridor** menentukan lebar pencarian SPKLU di sekitar rute dasar.
- **Interval SOC** menentukan granularitas state Dynamic Programming; interval
  lebih kecil umumnya menambah state dan komputasi.
- **SOC minimum** adalah batas tiba terendah yang diizinkan model.
- **Target SOC** adalah batas maksimum keberangkatan yang dievaluasi setelah
  berhenti di SPKLU, bukan estimasi waktu pengisian.

## Troubleshooting

| Gejala | Pemeriksaan |
|---|---|
| Form tetap nonaktif | periksa browser key, restriction referrer, Maps JavaScript API, dan Places API |
| Peta menampilkan authorization error | tambahkan origin lengkap termasuk port ke website restriction |
| HTTP 503 | isi server key dan restart aplikasi |
| HTTP 400 | perbaiki field yang disebut pada respons validasi |
| HTTP 502 | periksa jaringan, Routes API, billing, restriction server key, dan quota |
| Rute tidak feasible | baca reason dan statistik graf; ini dapat menjadi hasil penelitian yang valid |
| Perhitungan lama | tunggu satu request selesai; kandidat/edge dan latensi Google memengaruhi waktu |

Sebelum mencoba ulang error live, periksa quota Cloud dan jangan melakukan retry
tanpa batas. Daftar hard limit berada pada `docs/google_maps_api_limits.md`.
