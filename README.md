# Sistem Rekomendasi SPKLU Sulawesi

Prototipe penelitian untuk menyusun rekomendasi pemberhentian SPKLU multi-stop
pada perjalanan antarkota di Sulawesi. Sistem dirancang menggunakan Ball Tree
radius search untuk pencarian kandidat spasial dan Dynamic Programming dengan
state SOC untuk menyusun itinerary yang layak.

## Status pengembangan

Fase 1 telah menyiapkan fondasi aplikasi Flask, konfigurasi berbasis environment
variable, antarmuka awal, health check, dan pengujian dasar. Fase 2 menambahkan
validasi dataset, normalisasi konektor, dan konsolidasi unit pada satu lokasi
menjadi node logis. Fase 3 menambahkan indeks Ball Tree Haversine, radius search,
sampling polyline, filter koridor, dan pencarian kandidat maju berbasis usable
range. Fase 4 menambahkan pemangkasan edge geodesik, adapter batch jarak jalan,
dan graf berarah origin-SPKLU-destination. Fase 5 menambahkan model energi,
diskretisasi SOC konservatif, Dynamic Programming, rekonstruksi itinerary, dan
simulasi akhir setiap leg. Fase 6A mengintegrasikan Google Routes API untuk rute
dasar, matriks edge hasil pemangkasan, rute akhir, endpoint rekomendasi, serta
pencatatan penggunaan API. Fase 6B mengaktifkan Place Autocomplete, peta,
visualisasi rute dan marker SPKLU, formulir parameter, rincian SOC, serta
statistik perhitungan yang responsif.
Fase 7A menambahkan perangkat eksperimen yang dapat direproduksi, enam skenario
regional, analisis sensitivitas parameter, metrik SOC/API/runtime/memori, serta
ekspor laporan JSON dan CSV.
Fase 7B menambahkan validasi konfigurasi produksi, hardening HTTP, halaman
privasi/ketentuan, black-box test end-to-end, Gunicorn, dan container non-root.
Fase 7C menambahkan hard limit request Google Routes untuk menjaga eksperimen
live tetap berada dalam budget quota yang ditetapkan.
Fase 7D menambahkan ledger kuota harian lintas-eksekusi, reservasi atomik,
pencegahan eksperimen paralel, impor laporan idempoten, dan pemulihan proses
terhenti yang tetap mencatat pemakaian API.
Fase 7E memperketat audit eksperimen: laporan parsial tetap disimpan ketika
skenario error, tetapi exit code dan outcome ledger ditandai gagal.
Fase 8 menambahkan continuous integration lintas versi Python, test yang
terisolasi dari secret lokal, batas coverage, dan checklist rilis penelitian.
Fase 9 menerapkan ledger dan hard limit Routes API pada endpoint rekomendasi,
termasuk pencatatan attempt aktual serta penolakan request live paralel.
Fase 10 menambahkan manifest kandidat rilis, audit offline atas dataset,
skenario, ruang lingkup algoritma dan hard limit, serta menjadikannya quality
gate pada seluruh matrix CI.
Fase 11 mengunci dependency langsung dan transitif lintas Python 3.11–3.14,
memasukkan hash constraint ke manifest, dan memverifikasi instalasi container
pada ketiga runtime.
Fase 12 menambahkan quality gate container pada CI: build runtime kandidat, runtime
tanpa jaringan eksternal, healthcheck terbatas, audit rilis, user non-root, dan
uji akses tulis yang dibatasi ke direktori runtime.
Fase 13 menyederhanakan antarmuka untuk pengguna umum, menyediakan pilihan
multi-konektor dari seluruh tipe pada dataset, memindahkan parameter penelitian
lanjutan ke default backend, memperbaiki pengalaman Place Autocomplete, serta
memperjelas kesiapan lokasi dan endpoint sebelum tombol rekomendasi dapat
digunakan.
Fase 14 memisahkan kompatibilitas konektor dari akses jaringan charger,
menyertakan SPKLU publik secara default, menyediakan pilihan tambahan Hyundai,
Wuling, dan Toyota/Lexus, serta menandai itinerary yang memakai charger dealer
sebagai rute kondisional.
Fase 15 menyiapkan kandidat 0.18.0 untuk pelaporan ilmiah: definisi skenario
schema 4 dan laporan baru schema 5, provenance artefak historis, identitas source
dan dependency yang dapat diaudit, geometri rute `HIGH_QUALITY` dengan
`TRAFFIC_UNAWARE`, margin konservatif 1% pada prapemangkasan geodesik, validasi
ulang SOC dari setiap leg rute final, serta bukti CI yang dapat diunduh. Container
CI juga dijalankan dengan root filesystem read-only dan source aplikasi yang
tidak dapat ditulis oleh user runtime.
Fase 16 menetapkan kendaraan referensi Combo 2: CCS2 menjadi pilihan utama dan
AC Type 2 menjadi fallback yang selalu ditandai karena waktu pengisian tidak
dihitung. Jangkauan awal 430 km diturunkan secara deterministik dari median
tujuh model-family WLTP resmi Indonesia (433 km, dibulatkan ke 10 km), dengan
skenario sensitivitas 200/300/400/500 km dan konektor terpisah untuk run baru.
Fase 17 menambahkan hard cap total detour 20 km yang diturunkan dari dua kali
radius koridor 10 km. DP memangkas itinerary yang melampaui cap dan rute final
Google divalidasi ulang; sensitivitas 10/20/30 km disiapkan untuk run baru.
Fase 18 mengeluarkan station yang berjarak maksimal 50 meter dari origin atau
destination sebelum Route Matrix. Adapter juga menerima respons Google
zero-distance tanpa `distanceMeters` hanya ketika kedua koordinat identik dan
durasi nol; respons nonidentik yang tidak lengkap tetap ditolak.

## Ruang lingkup sistem

- Pencarian kandidat SPKLU di sepanjang koridor rute.
- Penyaringan berdasarkan satu atau beberapa konektor kendaraan, detour, dan
  progres perjalanan.
- Penyaringan jaringan publik/dealer pada tingkat unit tanpa mencampurkan
  konektor antarunit dalam satu node lokasi.
- Pembentukan graf berarah dengan edge yang memenuhi batas jangkauan.
- Dynamic Programming dengan state SOC diskret.
- Hard cap total detour 20 km dengan pruning DP dan validasi rute final.
- Rekomendasi urutan SPKLU, jarak setiap leg, SOC tiba/berangkat, dan detour.
- Deteksi feri generik yang memisahkan jarak pelayaran dari konsumsi SOC dan
  menandai akses kendaraan sebagai kondisional.
- Evaluasi kelayakan, jumlah pelanggaran SOC, jumlah pemberhentian, kebutuhan API,
  runtime, dan penggunaan memori.

Estimasi waktu pengisian tidak termasuk dalam ruang lingkup sistem.

## Menjalankan aplikasi secara lokal

Gunakan Python 3.11, 3.12, 3.13, atau 3.14. Python 3.14 direkomendasikan untuk
environment baru dan menjadi runtime container kandidat.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt -c constraints.txt
cp .env.example .env
chmod 600 .env
python run.py
```

Buka `http://127.0.0.1:5000`. Endpoint pemeriksaan sistem tersedia pada
`http://127.0.0.1:5000/api/health`. Endpoint rekomendasi tersedia melalui
`POST http://127.0.0.1:5000/api/recommendations` setelah server API key diisi.

Ringkasan dataset tersedia melalui endpoint
`http://127.0.0.1:5000/api/stations/summary` atau perintah:

```bash
python -m flask --app run.py dataset-summary
```

Eksperimen live memakai kuota Google Routes API dan harus dikonfirmasi secara
eksplisit:

Kebijakan aktif membatasi Compute Routes 100 request per hari dan per menit,
serta Route Matrix 2.000 elemen per hari dan per menit. Satu rekomendasi web
dibatasi maksimal 2 Compute Routes dan 625 elemen Matrix. Angka CLI di bawah
adalah hard cap eksperimen yang lebih kecil, bukan izin otomatis untuk memakai
seluruh sisa quota.

```bash
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

Periksa sisa kuota yang tercatat sebelum menjalankan eksperimen:

```bash
python -m flask --app run.py quota-status
```

Audit kandidat rilis tanpa menggunakan Google Maps API:

```bash
python -m flask --app run.py release-audit
```

Definisi metrik, skenario sensitivitas, dan cara membaca laporan dijelaskan pada
[`docs/evaluation.md`](docs/evaluation.md).

## Menjalankan pengujian

```bash
source .venv/bin/activate
pytest
```

## Struktur awal

```text
spklu-sulawesi/
|-- app/
|   |-- routes/          # Route halaman dan endpoint API
|   |-- services/        # Modul data, spasial, graf, dan optimasi
|   |-- static/          # CSS dan JavaScript
|   |-- templates/       # Template HTML
|   |-- __init__.py      # Application factory
|   `-- config.py        # Konfigurasi environment
|-- docs/                # Dokumentasi data dan penelitian
|-- experiments/         # Skenario baseline dan sensitivitas
|-- notebooks/           # Analisis reproduktif dan snapshot hasil jurnal
|-- tests/               # Pengujian otomatis
|-- dataset_spklu_sulawesi.csv
|-- dataset_metadata.json
|-- constraints.txt
|-- release_manifest.json
|-- research_manifest.json
|-- run.py
|-- requirements.txt
`-- requirements-dev.txt
```

## Keamanan konfigurasi

Salin `.env.example` menjadi `.env` untuk konfigurasi lokal, lalu jalankan
`chmod 600 .env` sebelum mengisinya dengan key. Berkas `.env` sudah dikecualikan
melalui `.gitignore` dan tidak boleh dimasukkan ke GitHub. Gunakan key terpisah
untuk browser dan server serta batasi key ke API yang diperlukan.

Aturan kolom, normalisasi konektor, dan konsolidasi unit dijelaskan pada
[`docs/data_dictionary.md`](docs/data_dictionary.md).

Rancangan indeks Ball Tree dan penyaringan koridor dijelaskan pada
[`docs/spatial_search.md`](docs/spatial_search.md).

Aturan pemangkasan edge dan pembentukan graf dijelaskan pada
[`docs/graph_construction.md`](docs/graph_construction.md).

Model energi dan Dynamic Programming dijelaskan pada
[`docs/dp_soc.md`](docs/dp_soc.md).

Alur, keamanan, payload, dan efisiensi Google Routes API dijelaskan pada
[`docs/google_routes.md`](docs/google_routes.md).

Deteksi langkah feri, penyesuaian energi, keterbatasan Matrix, dan kewajiban
konfirmasi operator dijelaskan pada [`docs/ferry_routes.md`](docs/ferry_routes.md).

Komponen dan alur interaksi antarmuka dijelaskan pada
[`docs/user_interface.md`](docs/user_interface.md).

Matriks pengujian fungsional dan catatan smoke test browser tersedia pada
[`docs/black_box_testing.md`](docs/black_box_testing.md).

Konfigurasi Gunicorn, Docker, HTTPS, Google Maps key, quota, dan checklist
publikasi dijelaskan pada [`docs/deployment.md`](docs/deployment.md).

Hasil baseline live enam wilayah, rincian itinerary, interpretasi rute
infeasible, serta audit quota tersedia pada
[`docs/baseline_results.md`](docs/baseline_results.md).

Hasil analisis sensitivitas live, pengaruh alpha/radius/interval SOC, dan audit
pemakaian API tersedia pada
[`docs/sensitivity_results.md`](docs/sensitivity_results.md).

Notebook pendamping jurnal yang menjalankan analisis dataset, demonstrasi DP,
baseline, sensitivitas, serta visualisasi secara offline tersedia pada
[`notebooks/analisis_sistem_spklu_sulawesi.ipynb`](notebooks/analisis_sistem_spklu_sulawesi.ipynb).
Seluruh narasi, tabel, grafik, dan pesan output notebook disajikan dalam bahasa
Inggris agar dapat digunakan langsung sebagai pendamping jurnal berbahasa Inggris.
Snapshot metrik yang dilacak beserta provenance-nya berada di
`notebooks/data/`; notebook tidak memanggil Google Maps API. Baseline tersebut
dihasilkan aplikasi 0.9.2 dan sensitivitas oleh aplikasi 0.10.0 dengan schema
laporan 2 serta definisi skenario schema 1 tertanam. Kandidat 0.18.0 menganalisis
snapshot itu secara offline dan tidak boleh disebut sebagai versi yang
menghasilkan request live historis.

Definisi skenario saat ini memakai schema 4 dan setiap laporan baru memakai
schema 5. Laporan schema 5 merekam provenance versi aplikasi, source tree,
dataset, skenario, dependency, manifest, parameter algoritma, dan lingkungan
eksekusi. Ketentuan ini berlaku untuk run baru; metadata yang tidak direkam oleh
laporan lama tidak diisi melalui tebakan.

Dasar numerik jangkauan kandidat dapat diaudit pada
[`research/vehicle_range_reference.json`](research/vehicle_range_reference.json).
Artefak tersebut hanya menentukan baseline model; pengguna aplikasi tetap harus
mengisi SOC dan jangkauan aktual kendaraannya.
Definisi, penerapan dua lapis, dan batas interpretasi hard cap detour dijelaskan
pada [`docs/detour_policy.md`](docs/detour_policy.md).
Hasil live 10/20/30 km pada tiga koridor tersedia pada
[`docs/detour_sensitivity_results.md`](docs/detour_sensitivity_results.md).

Asal penyedia, tanggal snapshot, metode pengumpulan, lisensi, dan hak
redistribusi dataset belum dikonfirmasi. `dataset_metadata.json` mencatat status
tersebut sebagai `incomplete`/`unknown`, bukan sebagai lisensi terbuka. Pemilik
penelitian perlu melengkapi bukti sumber dan izin sebelum dataset dipublikasikan
atau didistribusikan. Rincian dan checklist tindak lanjut tersedia pada
[`docs/data_provenance.md`](docs/data_provenance.md).

Hard limit seluruh layanan Google Maps dan daftar API yang dilarang tersedia
pada [`docs/google_maps_api_limits.md`](docs/google_maps_api_limits.md).

Pemisahan kompatibilitas konektor, jaringan dealer, dan status rute kondisional
dijelaskan pada
[`docs/charging_network_access.md`](docs/charging_network_access.md).

Workflow CI tanpa secret dan cara mengaktifkan branch protection dijelaskan pada
[`docs/continuous_integration.md`](docs/continuous_integration.md). Checklist
rilis lengkap tersedia pada
[`docs/release_checklist.md`](docs/release_checklist.md).
Cara kerja manifest dan audit kandidat rilis dijelaskan pada
[`docs/release_audit.md`](docs/release_audit.md).
Strategi dependency lock dan prosedur pembaruannya dijelaskan pada
[`docs/dependencies.md`](docs/dependencies.md).

Kontrak endpoint tersedia pada [`docs/api_reference.md`](docs/api_reference.md),
panduan penggunaan pada [`docs/user_guide.md`](docs/user_guide.md), dan identitas
kandidat rilis 0.18.0 pada
[`docs/release_candidate.md`](docs/release_candidate.md).

Checklist keselarasan ruang lingkup dan koreksi istilah pada proposal tersedia
pada [`docs/proposal_alignment.md`](docs/proposal_alignment.md).
