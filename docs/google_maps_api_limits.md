# Kebijakan hard limit Google Maps API

Kebijakan ini berlaku untuk seluruh pengujian live proyek. Nilai di Google Cloud
Console tetap menjadi pengaman utama. Ledger aplikasi mencatat eksperimen CLI
dan endpoint rekomendasi yang memakai Routes API, tetapi tidak dapat mencatat
request browser.

## Batas aktif

| Layanan | Batas harian | Batas per menit | Satuan |
|---|---:|---:|---|
| Compute Routes | 100 | 30 | request |
| Compute Route Matrix | 2.000 | 625 | elemen origin × destination |
| Places Autocomplete | 500 | 60 | request |
| Get Place | 200 | 30 | request |
| Map loads | 100 | 30 | load |

Layanan berikut tidak boleh dipanggil oleh aplikasi atau pengujian:

- 3D Maps;
- Maps Grounding Widget;
- Places Photo;
- Nearby Search;
- Text Search; dan
- Review/Media Search.

Frontend saat ini hanya memuat peta 2D, Place Autocomplete, dan `fetchFields`
untuk tempat yang dipilih. Eksperimen CLI hanya memakai Compute Routes dan
Compute Route Matrix sehingga tidak menghasilkan pemakaian Places atau map
load.

## Prosedur wajib sebelum pengujian live

1. Catat tanggal quota Pacific Time dan pemakaian terkini di Google Cloud.
2. Hitung batas atas Compute Routes, elemen Matrix, Places, Get Place, dan map
   load yang mungkin dipakai oleh skenario.
3. Tetapkan hard cap di bawah sisa quota, bukan sama dengan quota penuh jika
   sudah ada pemakaian hari itu.
4. Jalankan request secara berurutan atau gunakan pacing rolling window.
5. Jangan melakukan retry otomatis tanpa batas. Setiap rerun manual harus
   mempunyai alasan, label baru, dan perhitungan kumulatif baru.
6. Setelah selesai, catat attempt, request/elemen aktual, error, sisa quota, dan
   hash laporan mentah.

Untuk eksperimen Routes, jalankan `quota-status` sebelum dan sesudah proses.
Ledger menaikkan counter tepat sebelum request dikirim agar timeout atau
kegagalan jaringan dihitung secara konservatif.

```bash
python -m flask --app run.py quota-status
```

Endpoint rekomendasi mereservasi maksimal 2 Compute Routes dan 625 elemen Matrix
sebelum menjalankan pipeline. Reservasi diganti dengan attempt aktual saat
selesai atau gagal. Request paralel ditolak HTTP 429 agar beberapa worker tidak
menghabiskan quota per menit secara bersamaan. Ledger juga mempertahankan
pemakaian selesai selama rolling window 60 detik; request berurutan ditolak jika
reservasi maksimum berikutnya tidak muat dalam sisa window. Eksperimen CLI yang
memiliki pacing internal hanya dapat dimulai saat rolling window bersama tersebut
sudah bersih, sehingga pemakaian endpoint web sebelumnya tidak tumpang tindih
dengan batch pertama eksperimen.

## Pengujian browser

Test otomatis Flask tidak memuat Google Maps dan tidak memakai quota eksternal.
Smoke test browser live dapat memakai satu map load, Place Autocomplete saat
mengetik, serta Get Place ketika origin/destination dipilih. Sebelum smoke test:

- buka hanya satu tab aplikasi;
- tetapkan batas interaksi, misalnya maksimal 10 request Autocomplete dan dua
  Get Place untuk satu alur origin–destination;
- jangan reload halaman berulang karena setiap reload dapat menambah map load;
- jangan membuka fitur atau contoh Google yang menggunakan API terlarang; dan
- periksa pemakaian aktual pada Google Cloud setelah test.

Ledger lokal tidak mencatat browser API. Jika aplikasi dipublikasikan, quota
Cloud, restriction API key, restriction referrer, serta rate limiting pada
gateway harus tetap aktif.
