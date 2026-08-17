# Kandidat rilis 0.13.0

## Identitas

| Komponen | Nilai |
|---|---|
| Versi aplikasi | 0.13.0 |
| Dataset | 150 baris, 149 node logis |
| SHA-256 dataset | `24992e1225209ed5a2833b8722be6bfabfc94cdc55f795acdf5edf10c21ffa85` |
| Konektor aplikasi | AC Type 2, CCS2, CHAdeMO, GB/T |
| Konektor eksperimen | CCS2 |
| Estimasi waktu pengisian | Tidak termasuk |
| Python didukung | 3.11, 3.12, 3.13 |

## Bukti verifikasi lokal

- 167 test lulus dengan kedua API key dikosongkan;
- coverage total 91,43%, di atas ambang CI 90%;
- `pip check`, kompilasi Python, sintaks JavaScript, dan workflow YAML lulus;
- audit kandidat rilis offline lulus 24/24 check;
- health endpoint dari konfigurasi bersih memuat hash dataset yang benar; dan
- source scan tidak menemukan API key Google tertanam.

Smoke test produksi lokal juga memverifikasi:

- Gunicorn satu worker dapat boot dan melayani health HTTP 200;
- hostname tidak tepercaya ditolak dengan HTTP 400;
- CSP, HSTS, anti-frame, dan header keamanan lain aktif;
- image `spklu-sulawesi:0.13.0-rc1` berhasil dibangun tanpa jaringan;
- healthcheck container berstatus `healthy`;
- audit rilis di dalam container lulus 24/24 check;
- proses container berjalan sebagai user non-root `spklu`; dan
- direktori `/app/reports/generated` dapat ditulis oleh user runtime.

Smoke test hanya mengakses halaman utama dan health endpoint dengan dummy key.
Tidak ada Maps, Places, Compute Routes, atau Route Matrix yang dipanggil.

Quota guard endpoint juga telah diverifikasi dengan layanan palsu: reservasi
harian atomik, pencatatan attempt sukses/gagal, hard cap 2 Compute Routes dan
625 elemen Matrix per request, rolling window lintas-request, migrasi ledger
schema v1 ke v2, serta respons HTTP 429 untuk request paralel atau kapasitas yang
tidak mencukupi.

`release_manifest.json` mengunci versi, hash dependency, identitas dataset,
empat konektor aplikasi, konektor eksperimen CCS2, 6 skenario baseline, 7
skenario sensitivitas, dan enam hard limit.
Command `release-audit` menjadi quality gate pada ketiga job Python di CI dan
tidak menggunakan layanan Google Maps.

Dependency lock yang sama berhasil dipasang pada image Python 3.11, 3.12, dan
3.13. Ketiganya menjalankan NumPy 2.3.5 dan SciPy 1.16.3. Audit versi 0.13.0
memiliki 24 check dan dijalankan kembali oleh matrix CI setelah push.

GitHub Actions harus tetap diperiksa setelah push karena keberhasilan simulasi
lokal tidak menggantikan hasil runner GitHub untuk Python 3.11, Python 3.13,
dan job container tanpa jaringan eksternal.

## Bukti penelitian

- baseline enam wilayah: 6 skenario selesai, 3 feasible, 0 error, dan 0
  pelanggaran SOC pada itinerary feasible;
- sensitivitas Makassar–Rantepao: 7 skenario selesai dan feasible, 0 error, dan
  0 pelanggaran SOC; serta
- pemakaian ledger setelah pengujian: 39/100 attempt Compute Routes dan
  1.012/2.000 elemen Route Matrix pada hari quota terkait.

## Status kandidat rilis

Kandidat rilis siap untuk pengujian CI dan smoke test produksi tanpa request
rekomendasi. Status produksi final tetap memerlukan domain, HTTPS, Map ID,
restriction key, email kontak, quota Cloud, dan persetujuan sebelum test live.
