# Integrasi Google Routes API

## Tujuan

Google Routes API menyediakan jarak jalan, durasi berkendara, dan polyline untuk
pipeline rekomendasi. API ini tidak menghitung waktu pengisian. Seluruh
perhitungan energi tetap dilakukan oleh model SOC lokal.

## Alur permintaan

1. `Compute Routes` mengambil rute dasar dari origin ke destination.
2. Encoded polyline didekode menjadi koordinat dan dipakai oleh Ball Tree untuk
   memilih SPKLU dengan konektor kompatibel di dalam koridor.
3. Pemangkasan geodesik memakai lower bound dengan margin 1% untuk membuang
   pasangan yang tetap melebihi usable range setelah toleransi konservatif.
4. `Compute Route Matrix` hanya memvalidasi pasangan edge yang tersisa.
5. Dynamic Programming memilih itinerary berdasarkan durasi/jarak, jumlah
   pemberhentian, dan detour.
6. Jika itinerary memiliki SPKLU, `Compute Routes` kedua mengambil polyline akhir
   dengan SPKLU terpilih sebagai intermediate waypoint. Rute langsung memakai
   kembali polyline dasar sehingga tidak menambah permintaan.
7. Untuk setiap hasil feasible, jarak setiap leg rute yang ditampilkan
   disimulasikan ulang dengan model SOC. Bila
   jumlah leg berbeda dari itinerary atau satu leg tiba di bawah SOC minimum,
   rekomendasi ditolak dan tidak ditampilkan sebagai rute feasible.

## Konfigurasi rute

Compute Routes dan Route Matrix memakai `DRIVE` dengan
`routingPreference: TRAFFIC_UNAWARE`. Durasi karena itu merepresentasikan
estimasi berkendara tanpa lalu lintas real-time atau prediktif. Compute Routes
meminta `polylineQuality: HIGH_QUALITY` dan `ENCODED_POLYLINE` agar geometri
koridor serta visualisasi memakai bentuk rute yang lebih rinci.

`HIGH_QUALITY` tidak menjamin akurasi lokasi SPKLU atau kondisi jalan aktual,
sedangkan `TRAFFIC_UNAWARE` tidak boleh ditafsirkan sebagai estimasi waktu tiba
di kondisi lalu lintas saat perjalanan. Kedua nilai dikunci dalam manifest
kandidat dan direkam pada provenance laporan schema 3.

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
    "additional_charging_networks": ["HYUNDAI"]
  }
}
```

Objek `options` bersifat opsional dan menggunakan nilai default dari konfigurasi.
Aplikasi umum menerima satu atau beberapa konektor dataset dan mempertahankan
node yang mendukung sedikitnya satu pilihan. Field tunggal `connector` tetap
diterima untuk kompatibilitas. Safety factor, radius koridor, interval SOC, dan
langkah sampling tetap menjadi konfigurasi backend pada endpoint publik;
perangkat eksperimen dapat menetapkannya secara eksplisit. Baseline dan
sensitivitas penelitian tetap dibatasi ke CCS2.

Respons sukses berisi rute dasar, statistik kandidat dan graf, hasil optimasi,
rute rekomendasi, serta statistik penggunaan API. Untuk setiap itinerary
feasible, `optimization.final_route_validation.status` harus `passed` agar rute
final dikembalikan. Rute yang tidak feasible tetap merupakan hasil
perhitungan yang valid dan dikembalikan dengan HTTP 200, tetapi
`optimization.feasible` bernilai `false`.
