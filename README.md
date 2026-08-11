# Sistem Rekomendasi SPKLU Sulawesi

Prototipe penelitian untuk menyusun rekomendasi pemberhentian SPKLU multi-stop
pada perjalanan antarkota di Sulawesi. Sistem dirancang menggunakan Ball Tree
radius search untuk pencarian kandidat spasial dan Dynamic Programming dengan
state SOC untuk menyusun itinerary yang layak.

## Status pengembangan

Fase 1 telah menyiapkan fondasi aplikasi Flask, konfigurasi berbasis environment
variable, antarmuka awal, health check, dan pengujian dasar. Fase 2 menambahkan
validasi dataset, normalisasi konektor, dan konsolidasi unit pada satu lokasi
menjadi node logis. Algoritma rekomendasi belum diaktifkan dan akan ditambahkan
secara bertahap.

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
python -m pip install -r requirements-dev.txt
cp .env.example .env
python run.py
```

Buka `http://127.0.0.1:5000`. Endpoint pemeriksaan sistem tersedia pada
`http://127.0.0.1:5000/api/health`.

Ringkasan dataset tersedia melalui endpoint
`http://127.0.0.1:5000/api/stations/summary` atau perintah:

```bash
python -m flask --app run.py dataset-summary
```

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
|-- tests/               # Pengujian otomatis
|-- dataset_spklu_sulawesi.csv
|-- run.py
|-- requirements.txt
`-- requirements-dev.txt
```

## Keamanan konfigurasi

Salin `.env.example` menjadi `.env` untuk konfigurasi lokal. Berkas `.env` sudah
dikecualikan melalui `.gitignore` dan tidak boleh dimasukkan ke GitHub. API key
Google Maps baru akan diperlukan pada fase integrasi peta.

Aturan kolom, normalisasi konektor, dan konsolidasi unit dijelaskan pada
[`docs/data_dictionary.md`](docs/data_dictionary.md).
