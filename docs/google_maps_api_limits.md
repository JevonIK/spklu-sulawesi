# Kebijakan hard limit Google Maps API

Kebijakan ini berlaku untuk seluruh pengujian live proyek. Nilai di Google Cloud
Console harus menjadi pengaman utama karena ledger aplikasi hanya mencatat
eksperimen Routes API melalui CLI.

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
