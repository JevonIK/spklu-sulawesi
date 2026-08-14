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
Fase 8 menambahkan continuous integration pada tiga versi Python, test yang
terisolasi dari secret lokal, batas coverage, dan checklist rilis penelitian.
Fase 9 menerapkan ledger dan hard limit Routes API pada endpoint rekomendasi,
termasuk pencatatan attempt aktual serta penolakan request live paralel.
Fase 10 menambahkan manifest kandidat rilis, audit offline atas dataset,
skenario, ruang lingkup algoritma dan hard limit, serta menjadikannya quality
gate pada seluruh matrix CI.
Fase 11 mengunci dependency langsung dan transitif lintas Python 3.11–3.13,
memasukkan hash constraint ke manifest, dan memverifikasi instalasi container
pada ketiga runtime.
Fase 12 menambahkan quality gate container pada CI: build Python 3.12, runtime
tanpa jaringan eksternal, healthcheck terbatas, audit rilis, user non-root, dan
uji tulis direktori persisten.

## Ruang lingkup sistem

- Pencarian kandidat SPKLU di sepanjang koridor rute.
- Penyaringan berdasarkan konektor, detour, dan progres perjalanan.
- Pembentukan graf berarah dengan edge yang memenuhi batas jangkauan.
- Dynamic Programming dengan state SOC diskret.
- Rekomendasi urutan SPKLU, jarak setiap leg, SOC tiba/berangkat, dan detour.
- Evaluasi kelayakan, jumlah pelanggaran SOC, jumlah pemberhentian, kebutuhan API,
  runtime, dan penggunaan memori.

Estimasi waktu pengisian tidak termasuk dalam ruang lingkup sistem.

## Menjalankan aplikasi secara lokal

Gunakan Python 3.11, 3.12, atau 3.13. Python 3.12 direkomendasikan untuk menjaga
kompatibilitas pustaka analisis data.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt -c constraints.txt
cp .env.example .env
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

```bash
python -m flask --app run.py experiment-run \
  --scenarios experiments/scenarios_baseline.json \
  --label baseline-enam-wilayah \
  --max-compute-routes 60 \
  --max-compute-routes-per-minute 30 \
  --max-compute-routes-per-scenario 10 \
  --max-matrix-elements 2000 \
  --max-matrix-elements-per-minute 625 \
  --batch-size 3 \
  --batch-interval-seconds 61 \
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
|-- tests/               # Pengujian otomatis
|-- dataset_spklu_sulawesi.csv
|-- constraints.txt
|-- release_manifest.json
|-- run.py
|-- requirements.txt
`-- requirements-dev.txt
```

## Keamanan konfigurasi

Salin `.env.example` menjadi `.env` untuk konfigurasi lokal. Berkas `.env` sudah
dikecualikan melalui `.gitignore` dan tidak boleh dimasukkan ke GitHub. Gunakan
key terpisah untuk browser dan server serta batasi key ke API yang diperlukan.

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

Hard limit seluruh layanan Google Maps dan daftar API yang dilarang tersedia
pada [`docs/google_maps_api_limits.md`](docs/google_maps_api_limits.md).

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
kandidat rilis 0.12.0 pada
[`docs/release_candidate.md`](docs/release_candidate.md).

Checklist keselarasan ruang lingkup dan koreksi istilah pada proposal tersedia
pada [`docs/proposal_alignment.md`](docs/proposal_alignment.md).
