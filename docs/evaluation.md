# Evaluasi eksperimen

Perangkat evaluasi menjalankan pipeline yang sama dengan endpoint rekomendasi,
tetapi menggunakan skenario terdokumentasi dan menghasilkan laporan JSON serta
CSV. Eksekusi dilakukan berurutan agar jumlah panggilan API dan penggunaan
sumber daya per skenario dapat diaudit.

## Skenario penelitian

`experiments/scenarios_baseline.json` memuat satu koridor pada masing-masing
wilayah penelitian:

| Wilayah | Koridor baseline |
|---|---|
| Sulawesi Selatan | Makassar–Rantepao |
| Sulawesi Tengah | Palu–Moutong |
| Sulawesi Tenggara | Kolaka–Kendari |
| Sulawesi Utara | Bintauna–Manado |
| Sulawesi Barat | Polewali–Mamuju |
| Gorontalo | Marisa–Kota Gorontalo |

Semua baseline memakai konektor CCS2, jangkauan maksimum 300 km, SOC awal 80%,
SOC minimum 20%, target SOC 80%, safety factor 0,9, interval SOC 5%, dan radius
koridor 10 km. Nilai tersebut merupakan parameter eksperimen, bukan klaim
spesifikasi seluruh kendaraan listrik.

`experiments/scenarios_sensitivity.json` memakai koridor Makassar–Rantepao dan
mengubah satu variabel pada satu waktu:

- safety factor/alpha: 0,8; 0,9; dan 1,0;
- radius koridor: 5, 10, dan 15 km;
- interval diskretisasi SOC: 2,5%; 5%; dan 10%.

Jumlah kandidat tidak dipaksakan menjadi nilai tertentu. Sistem mencatat jumlah
kandidat aktual hasil Ball Tree untuk menunjukkan dampak radius koridor.

## Metrik yang direkam

| Kelompok | Metrik |
|---|---|
| Kelayakan | status selesai/error, rute feasible, alasan infeasible |
| Keselamatan | jumlah leg dengan SOC tiba di bawah SOC minimum |
| Itinerary | jumlah perhentian, jarak jalan, waktu berkendara, detour, SOC akhir dan minimum |
| Algoritma | kandidat koridor, node/edge graf, state dan transisi DP |
| Efisiensi API | Compute Routes, Compute Route Matrix, elemen matriks, total request |
| Komputasi | runtime wall-clock dan peak memory yang diamati `tracemalloc` |

Feasibility rate menggunakan jumlah skenario yang selesai sebagai denominator.
Kegagalan API atau exception dicatat sebagai `error`, bukan dipaksakan menjadi
rute infeasible. Dengan demikian, masalah infrastruktur tidak tercampur dengan
ketidaklayakan jaringan SPKLU.

`soc_violation_count` dihitung ulang dari SOC tiba setiap leg hasil itinerary.
Skenario infeasible tidak memiliki leg dan mendapat nilai nol; status
`route_feasible` dan `reason` tetap harus dibaca bersamanya.

Runtime mencakup validasi input, panggilan Google Routes, pencarian spasial,
pembentukan graf, dan DP. Karena latensi jaringan ikut tercakup, eksperimen
sebaiknya diulang pada kondisi jaringan yang sebanding. Peak memory merupakan
pengukuran proses Python selama skenario dan bukan keseluruhan memori sistem.

Estimasi waktu pengisian tidak dihitung. Kolom waktu hanya merujuk pada
`total_driving_duration_minutes` dari rute jalan Google.

## Menjalankan eksperimen

Pastikan server API key sudah dibatasi untuk Routes API dan billing/quota sudah
ditinjau. Perintah sengaja meminta flag konfirmasi karena setiap eksekusi dapat
menggunakan kuota berbayar.

```bash
source .venv/bin/activate
python -m flask --app run.py experiment-run \
  --scenarios experiments/scenarios_baseline.json \
  --label baseline-enam-wilayah \
  --max-api-requests 100 \
  --confirm-live-api
```

Analisis sensitivitas:

```bash
python -m flask --app run.py experiment-run \
  --scenarios experiments/scenarios_sensitivity.json \
  --label sensitivitas-makassar-rantepao \
  --max-api-requests 100 \
  --confirm-live-api
```

Keluaran default berada di `reports/generated/<label>.json` dan `.csv`. Folder
ini diabaikan Git karena laporan live dapat mengandung hasil yang belum
divalidasi. Setelah hasil diperiksa, salin tabel/angka final yang diperlukan ke
artefak laporan penelitian yang memang hendak dijadikan bukti versi.

Laporan JSON menyimpan ulang definisi skenario secara utuh. CSV menyertakan
parameter kendaraan dan algoritma pada setiap baris sehingga hasil sensitivitas
dapat dibandingkan tanpa bergantung pada berkas skenario yang mungkin berubah.

## Pengaman quota live

`--max-api-requests` adalah hard limit jumlah percobaan HTTP aktual ke Google
Routes API selama satu eksekusi CLI. Nilai defaultnya 100 dan rentang yang
diterima 1–1.000. Penghitung bertambah tepat sebelum request dikirim, termasuk
request yang kemudian timeout atau ditolak upstream. Setelah batas tercapai,
request berikutnya gagal lokal dengan `request_budget_exceeded` dan tidak dikirim
ke Google.

Laporan JSON memiliki objek `execution` berisi:

- `api_request_budget`: batas yang dipilih;
- `api_request_attempt_count`: request HTTP yang benar-benar dicoba;
- `api_request_budget_remaining`: sisa budget;
- `api_request_budget_exhausted`: apakah batas telah habis; dan
- `live_api_confirmed`: bukti flag konfirmasi diberikan.

Statistik per skenario tetap mencatat request logis Compute Routes/Matrix yang
berhasil menyelesaikan tahap terkait. Karena itu, gunakan `execution` untuk
audit quota batch dan `results[].api_usage` untuk analisis kebutuhan algoritma.
Jika budget habis, sebagian skenario dapat berstatus `error`; jangan menghitung
feasibility rate final sebelum seluruh skenario selesai tanpa error.

Baseline dan sensitivitas merupakan dua perintah terpisah. Dengan budget default,
batas gabungannya paling banyak 200 percobaan request, bukan 100. Turunkan budget
jika quota atau anggaran penelitian memerlukan batas yang lebih kecil.

CLI menolak menimpa laporan lama. Gunakan label baru untuk replikasi, misalnya
`baseline-enam-wilayah-uji-2`. Opsi `--overwrite` hanya digunakan jika
penggantian berkas memang disengaja.

## Interpretasi minimum

Sebelum mengambil kesimpulan, periksa hal berikut:

1. `error_count` harus nol agar feasibility rate mewakili semua skenario.
2. Itinerary feasible harus memiliki `total_soc_violations = 0`.
3. Bandingkan jumlah kandidat, node/edge, state/transisi, request API, runtime,
   dan memori ketika parameter sensitivitas berubah.
4. Jelaskan rute infeasible berdasarkan `reason`, kandidat koridor, dan bentuk
   graf; jangan menyimpulkan bahwa implementasi gagal hanya dari infeasibility.
5. Catat tanggal, label keluaran, parameter, dan kondisi eksperimen pada laporan.
