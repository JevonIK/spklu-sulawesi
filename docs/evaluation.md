# Evaluasi eksperimen

Perangkat evaluasi menjalankan pipeline yang sama dengan endpoint rekomendasi,
tetapi menggunakan skenario terdokumentasi dan menghasilkan laporan JSON serta
CSV. Eksekusi dilakukan berurutan agar jumlah panggilan API dan penggunaan
sumber daya per skenario dapat diaudit.

Definisi skenario kandidat 0.17.0 wajib memakai `schema_version: 4`. Laporan
yang dibuat sekarang memakai `schema_version: 5`; angka schema skenario dan
laporan sengaja berbeda karena keduanya memiliki kontrak data yang berbeda.

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

Semua baseline kandidat memakai kendaraan Combo 2 dengan CCS2 sebagai konektor
utama dan AC Type 2 sebagai fallback, jangkauan maksimum 430 km, SOC awal 80%,
SOC minimum 20%, target SOC 80%, safety factor 0,9, interval SOC 5%, dan radius
koridor 10 km. Nilai 430 km berasal dari median tujuh model-family WLTP resmi
Indonesia sebesar 433 km yang dibulatkan ke 10 km; sumber dan perhitungan berada
pada `research/vehicle_range_reference.json`. Ini adalah kendaraan referensi,
bukan klaim spesifikasi seluruh kendaraan listrik.
Baseline membatasi total detour sebesar 20 km, diturunkan dari `2 ×` radius
koridor 10 km sebagai batas deviasi keluar–kembali ke koridor. Nilai ini
merupakan kebijakan geometris yang diuji lagi melalui sensitivitas, bukan
preferensi pengguna yang sudah tervalidasi.
Rumus dan perbedaan estimator graf terhadap detour rute final dijelaskan pada
[`detour_policy.md`](detour_policy.md).

`experiments/scenarios_sensitivity.json` memakai koridor Makassar–Rantepao dan
mengubah satu variabel pada satu waktu:

- safety factor/alpha: 0,8; 0,9; dan 1,0;
- radius koridor: 5, 10, dan 15 km;
- interval diskretisasi SOC: 2,5%; 5%; dan 10%.
- jangkauan maksimum: 200, 300, 400, baseline 430, dan 500 km.
- batas total detour: 10, baseline 20, dan 30 km.

`experiments/scenarios_connector_sensitivity.json` membandingkan CCS2 publik
saja dengan konfigurasi Combo 2 yang mengizinkan fallback AC Type 2. Semua
parameter lain identik. Pemberhentian AC-only direkam sebagai
`ac_fallback_stop_count`; optimizer mendahulukan itinerary tanpa fallback AC.

Jumlah kandidat tidak dipaksakan menjadi nilai tertentu. Sistem mencatat jumlah
kandidat aktual hasil Ball Tree untuk menunjukkan dampak radius koridor.

## Metrik yang direkam

| Kelompok | Metrik |
|---|---|
| Kelayakan | status selesai/error, rute feasible, alasan infeasible |
| Keselamatan | jumlah leg dengan SOC tiba di bawah SOC minimum |
| Itinerary | jumlah perhentian, fallback AC, jarak jalan, waktu berkendara, detour, SOC akhir dan minimum |
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

Untuk setiap itinerary feasible, versi 0.17.0 juga memvalidasi ulang SOC dari
jarak setiap leg rute yang ditampilkan, bukan hanya edge Route Matrix yang
dipakai DP.
Mismatch jumlah leg atau pelanggaran SOC final dicatat sebagai error dan rute
tidak dilaporkan feasible. Jaminan tersebut tetap terbatas pada model SOC linier.

Rute feri menambah metrik `total_energy_distance_km`,
`total_ferry_distance_km`, `total_ferry_duration_minutes`,
`total_travel_duration_minutes`, dan `ferry_segment_count`. SOC hanya dihitung
dari jarak energi/darat. Jadwal, kapasitas, dan akses kendaraan tidak menjadi
metrik karena tidak tersedia secara real-time.

Runtime mencakup validasi input, panggilan Google Routes, pencarian spasial,
pembentukan graf, dan DP. Karena latensi jaringan ikut tercakup, eksperimen
sebaiknya diulang pada kondisi jaringan yang sebanding. Peak memory merupakan
pengukuran proses Python selama skenario dan bukan keseluruhan memori sistem.

Estimasi waktu pengisian tidak dihitung. `total_driving_duration_minutes`
mengecualikan durasi feri, sedangkan `total_travel_duration_minutes` mencakup
durasi darat dan pelayaran dari rute Google tetapi tidak mencakup antrean atau
waktu tunggu jadwal kapal.

## Menjalankan eksperimen

Pastikan server API key sudah dibatasi untuk Routes API dan billing/quota sudah
ditinjau. Perintah sengaja meminta flag konfirmasi karena setiap eksekusi dapat
menggunakan kuota berbayar.

```bash
source .venv/bin/activate
python -m flask --app run.py experiment-run \
  --scenarios experiments/scenarios_baseline.json \
  --label baseline-enam-wilayah \
  --max-compute-routes 60 \
  --max-compute-routes-per-minute 100 \
  --max-compute-routes-per-scenario 10 \
  --max-matrix-elements 2000 \
  --max-matrix-elements-per-minute 2000 \
  --batch-size 100 \
  --batch-interval-seconds 0 \
  --confirm-live-api
```

Analisis sensitivitas:

```bash
python -m flask --app run.py experiment-run \
  --scenarios experiments/scenarios_sensitivity.json \
  --label sensitivitas-live-YYYYMMDD \
  --max-compute-routes 26 \
  --max-compute-routes-per-minute 100 \
  --max-compute-routes-per-scenario 2 \
  --max-matrix-elements 1200 \
  --max-matrix-elements-per-minute 2000 \
  --batch-size 100 \
  --batch-interval-seconds 0 \
  --confirm-live-api
```

Batas Compute Routes contoh berasal dari tiga belas skenario yang masing-masing
memakai maksimal satu rute dasar dan satu rute rekomendasi. Batas Matrix tidak
dapat diturunkan hanya dari jumlah skenario karena bergantung pada kandidat dan
pasangan graf. Hitung estimasi elemen terlebih dahulu, periksa ledger dan Cloud
Console, lalu pecah run ke hari berbeda bila estimasi mendekati 2.000 elemen.

Keluaran default berada di `reports/generated/<label>.json` dan `.csv`. Folder
ini diabaikan Git karena laporan live dapat mengandung hasil yang belum
divalidasi. Setelah hasil diperiksa, salin tabel/angka final yang diperlukan ke
artefak laporan penelitian yang memang hendak dijadikan bukti versi.

Laporan JSON menyimpan ulang definisi skenario secara utuh. CSV menyertakan
parameter kendaraan dan algoritma pada setiap baris sehingga hasil sensitivitas
dapat dibandingkan tanpa bergantung pada berkas skenario yang mungkin berubah.
Schema laporan versi 5 menyimpan daftar konektor, konektor preferen, batas
total detour, jumlah
fallback AC, nama SPKLU terpilih, rincian leg dan SOC,
jarak/durasi rute dasar serta rekomendasi, statistik pemangkasan graf, dan
statistik optimizer. Laporan juga merekam provenance kandidat: versi aplikasi,
hash source scope `application-runtime-v2`, dataset dan metadatanya, definisi
skenario, `constraints.txt`, manifest rilis/penelitian, nilai default algoritma,
`HIGH_QUALITY`, `TRAFFIC_UNAWARE`, margin geodesik 1%, aturan manuver feri,
serta ringkasan lingkungan eksekusi. Polyline, API key, dan koordinat hasil
Google tidak disalin ke laporan.

Baseline dan sensitivitas yang sudah dipakai notebook adalah laporan historis
schema 2, masing-masing dibuat aplikasi 0.9.2 dan 0.10.0. Definisi yang tertanam
di kedua laporan lama memakai schema skenario 1; berkas skenario kandidat saat
ini sudah schema 4. Perubahan tersebut dan schema laporan 5 tidak mengubah
provenance run lama. Khususnya, langkah sampling rute tidak direkam di laporan
lama dan tidak boleh diisi dengan mengasumsikan default 0.17.0.
Kedua laporan historis juga belum mempunyai metrik feri dan tidak dapat dipakai
sebagai validasi empiris untuk fitur ferry-aware kandidat saat ini.

## Pengaman quota live

Compute Routes dan Compute Route Matrix memakai dimensi quota berbeda. Karena
itu, CLI menerapkan hard limit terpisah. Compute Routes dibatasi maksimal 60
panggilan per eksperimen, 100 panggilan dalam rolling window 60 detik, dan 10
panggilan per skenario. Route Matrix dibatasi maksimal 2.000 elemen per
eksperimen dan 2.000 elemen dalam rolling window 60 detik. Batas per menit
disamakan dengan batas harian sehingga tidak menambah jeda selama sisa quota
harian mencukupi.

Penghitung bertambah tepat sebelum request dikirim, termasuk request yang
kemudian timeout atau ditolak upstream. Request yang akan melampaui hard limit
gagal secara lokal dan tidak dikirim ke Google. Mekanisme pacing tetap tersedia
untuk batas kustom yang lebih rendah, tetapi konfigurasi default tidak memaksa
jeda antarskenario.

Default ukuran batch adalah 100 dengan jeda 0 detik, sehingga enam baseline dan
tiga belas sensitivitas berjalan berurutan tanpa jeda buatan. Opsi `--batch-size` dan
`--batch-interval-seconds` tetap dicatat di laporan dan dapat diberi jeda positif
secara manual bila diperlukan.

Laporan JSON memiliki objek `execution` berisi:

- limit, percobaan aktual, dan sisa panggilan Compute Routes;
- limit Compute Routes per menit dan per skenario;
- percobaan Compute Routes untuk setiap ID skenario;
- limit, pemakaian aktual, dan sisa elemen Route Matrix;
- jumlah request Route Matrix aktual;
- total waktu tunggu otomatis akibat rolling window; dan
- `live_api_confirmed`: bukti flag konfirmasi diberikan.

Statistik per skenario tetap mencatat request logis Compute Routes/Matrix yang
berhasil menyelesaikan tahap terkait. Karena itu, gunakan `execution` untuk
audit quota batch dan `results[].api_usage` untuk analisis kebutuhan algoritma.
Jika budget habis, sebagian skenario dapat berstatus `error`; jangan menghitung
feasibility rate final sebelum seluruh skenario selesai tanpa error.

Jika satu atau lebih skenario error, CLI tetap menyimpan JSON/CSV parsial untuk
audit, mengisi `execution.outcome` dengan `completed_with_errors`, menandai run
ledger sebagai `failed`, dan keluar dengan status nonzero. Run hanya berstatus
`completed` apabila `aggregate.error_count` bernilai nol.

Baseline dan sensitivitas merupakan dua perintah terpisah, sedangkan quota
harian Google berlaku gabungan. CLI memakai ledger lokal untuk mencatat laporan
lama, mereservasi hard limit sebelum eksperimen, dan mengganti reservasi dengan
pemakaian aktual setelah proses selesai atau gagal. Eksperimen baru ditolak jika
reservasi ditambah pemakaian hari itu dapat melewati 100 Compute Routes atau
2.000 elemen Route Matrix. Proses live paralel tetap ditolak agar pencatatan dan
reservasi tidak tumpang tindih. Eksperimen CLI dapat dimulai tanpa menunggu
rolling window bersih jika hard cap yang diminta tidak melebihi sisa quota harian
dan sisa kapasitas menit aktif. Jika sudah ada pemakaian hari itu, turunkan opsi
`--max-compute-routes` dan `--max-matrix-elements` sesuai output `quota-status`.

Periksa ledger sebelum meminta izin atau menjalankan eksperimen:

```bash
python -m flask --app run.py quota-status
```

Kuota per hari Google reset pada tengah malam Pacific Time. Karena itu, field
`date` pada output memakai zona `America/Los_Angeles` dan dapat berbeda satu
tanggal dari waktu Indonesia. Konfigurasi `GOOGLE_QUOTA_TIMEZONE` sebaiknya tidak
diubah ke `Asia/Jakarta`. Batas harian ledger harus sama dengan quota yang
ditetapkan pada Google Cloud Console.

Rujukan perilaku reset dan satuan penagihan tersedia pada dokumentasi resmi
[Cloud Quotas](https://docs.cloud.google.com/docs/quotas/overview) dan
[Routes API usage and billing](https://developers.google.com/maps/documentation/routes/usage-and-billing).

Laporan lama yang belum dicatat dapat diimpor secara idempoten. Hash SHA-256 dan
path laporan mencegah laporan yang sama dihitung dua kali:

```bash
python -m flask --app run.py quota-import-report \
  --report reports/generated/baseline-live-20260813.json \
  --report reports/generated/baseline-live-20260813-detailed.json
```

Jika terminal atau proses mati, reservasi sengaja tetap aktif dan eksperimen
berikutnya diblokir. Setelah memastikan proses benar-benar berhenti, pulihkan
reservasi dengan jumlah percobaan yang terlihat pada log. Bila jumlahnya tidak
pasti, gunakan batas maksimum reservasi sebagai batas atas yang aman:

```bash
python -m flask --app run.py quota-recover \
  --reservation ID_RESERVASI \
  --compute-routes-attempts 60 \
  --matrix-element-attempts 2000 \
  --reason "proses berhenti sebelum laporan dibuat" \
  --confirm-process-stopped
```

Ledger bersifat fail-closed dan dipakai bersama oleh eksperimen CLI serta
endpoint web pada satu filesystem. Ia tidak membaca pemakaian yang dibuat
langsung oleh program lain atau API key yang sama di luar aplikasi. Google Cloud
quota tetap menjadi sumber kontrol utama; cocokkan status ledger dengan
dashboard sebelum eksperimen berbayar.

Nilai aktif proyek adalah 100 Compute Routes per hari dan per menit, serta 2.000
elemen Route Matrix per hari dan per menit. Endpoint web mereservasi paling
banyak 2 Compute Routes dan 625 elemen Matrix per request. Places Autocomplete,
Get Place, dan map load masing-masing dibatasi 500, 200, dan 100 per hari serta
per menit; ledger backend tidak mencatat pemakaian browser. Detail dan daftar API
yang dilarang berada pada
[`google_maps_api_limits.md`](google_maps_api_limits.md). Nilai ini adalah
kebijakan kandidat saat ini, bukan bukti pemakaian aktual Google Cloud.

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
6. Catat versi aplikasi penghasil dan schema laporan; jangan mengatribusikan
   hasil historis 0.9.2/0.10.0 kepada kandidat analisis 0.17.0.

Hasil sensitivitas live yang telah divalidasi tersedia pada
[`sensitivity_results.md`](sensitivity_results.md). Kebijakan seluruh layanan
Google Maps, termasuk Places dan map load, tersedia pada
[`google_maps_api_limits.md`](google_maps_api_limits.md).
