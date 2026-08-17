# Integrasi Google Routes API

## Tujuan

Google Routes API menyediakan jarak jalan, durasi berkendara, dan polyline untuk
pipeline rekomendasi. API ini tidak menghitung waktu pengisian. Seluruh
perhitungan energi tetap dilakukan oleh model SOC lokal.

## Alur permintaan

1. `Compute Routes` mengambil rute dasar dari origin ke destination.
2. Overview polyline didekode menjadi koordinat dan dipakai oleh Ball Tree untuk
   memilih SPKLU dengan konektor kompatibel di dalam koridor.
3. Pemangkasan geodesik membuang pasangan node yang pasti melebihi usable range.
4. `Compute Route Matrix` hanya memvalidasi pasangan edge yang tersisa.
5. Dynamic Programming memilih itinerary berdasarkan durasi/jarak, jumlah
   pemberhentian, dan detour.
6. Jika itinerary memiliki SPKLU, `Compute Routes` kedua mengambil polyline akhir
   dengan SPKLU terpilih sebagai intermediate waypoint. Rute langsung memakai
   kembali polyline dasar sehingga tidak menambah permintaan.

## Efisiensi pemakaian API

Permintaan matriks dikelompokkan berdasarkan origin. Setiap destination dalam
kelompok tepat berkorespondensi dengan satu edge hasil pemangkasan, sehingga
tidak ada perkalian pasangan origin-destination yang tidak diperlukan. Respons
API mencatat:

- jumlah permintaan `Compute Routes`;
- jumlah permintaan `Compute Route Matrix`;
- jumlah elemen matriks atau edge yang divalidasi; dan
- total permintaan eksternal.

Pengujian otomatis menggunakan session palsu dan tidak memanggil Google, sehingga
menjalankan `pytest` tidak menggunakan kuota.

## Keamanan

- Key browser dan server harus berbeda.
- Key server hanya dibaca dari `GOOGLE_MAPS_SERVER_API_KEY` di `.env`.
- Key tidak ditempatkan di URL, payload, respons API aplikasi, atau pesan error.
- Key server dibatasi hanya untuk Routes API dan sebaiknya dibatasi lagi dengan
  IP publik server ketika deployment.
- Timeout dapat diatur melalui `GOOGLE_ROUTES_TIMEOUT_SECONDS`.

## Endpoint rekomendasi

`POST /api/recommendations` menerima JSON berikut:

```json
{
  "origin": {"latitude": -5.1477, "longitude": 119.4327},
  "destination": {"latitude": -0.8986, "longitude": 119.8506},
  "vehicle": {
    "maximum_range_km": 300,
    "current_soc_percent": 80,
    "connectors": ["CCS2", "CHADEMO"]
  },
  "options": {
    "minimum_soc_percent": 20,
    "target_soc_percent": 80,
    "safety_factor": 0.9,
    "soc_step_percent": 5,
    "corridor_radius_km": 10
  }
}
```

Objek `options` bersifat opsional dan menggunakan nilai default dari konfigurasi.
Aplikasi umum menerima satu atau beberapa konektor dataset dan mempertahankan
node yang mendukung sedikitnya satu pilihan. Field tunggal `connector` tetap
diterima untuk kompatibilitas. Eksperimen baseline dan sensitivitas tetap
dibatasi ke CCS2 sesuai rancangan penelitian.

Respons sukses berisi rute dasar, statistik kandidat dan graf, hasil optimasi,
rute rekomendasi, serta statistik penggunaan API. Rute yang tidak feasible tetap
merupakan hasil perhitungan yang valid dan dikembalikan dengan HTTP 200, tetapi
`optimization.feasible` bernilai `false`.
