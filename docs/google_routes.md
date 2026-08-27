# Integrasi Google Routes API

## Tujuan

Google Routes API menyediakan jarak jalan, durasi perjalanan, dan polyline untuk
pipeline rekomendasi. Seluruh perhitungan energi tetap dilakukan oleh model SOC
lokal.

## Alur permintaan

1. `Compute Routes` mengambil rute dasar beserta langkah navigasi dari origin
   ke destination. Manuver `FERRY` dan `FERRY_TRAIN` dipisahkan dari segmen
   darat secara generik, tanpa hardcode nama lintasan.
2. Encoded polyline didekode menjadi koordinat dan dipakai oleh Ball Tree untuk
   memilih SPKLU dengan konektor kompatibel di dalam koridor.
3. Pemangkasan geodesik memakai lower bound dengan margin 1% untuk membuang
   pasangan yang tetap melebihi usable range setelah toleransi konservatif.
4. `Compute Route Matrix` hanya memvalidasi pasangan edge yang tersisa. Karena
   Matrix tidak menyediakan langkah navigasi, jarak feri edge diestimasi dari
   irisan progres terhadap segmen feri rute dasar.
5. Dynamic Programming memilih itinerary berdasarkan durasi/jarak, jumlah
   pemberhentian, dan detour.
6. Jika itinerary memiliki SPKLU, `Compute Routes` kedua mengambil polyline akhir
   dengan SPKLU terpilih sebagai intermediate waypoint. Rute langsung memakai
   kembali polyline dasar sehingga tidak menambah permintaan.
7. Untuk setiap hasil feasible, jarak darat dan feri setiap leg rute final
   dipisahkan kembali dari langkah Compute Routes. Hanya jarak darat yang
   mengurangi SOC. Bila
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
kandidat dan direkam pada provenance laporan schema 5.

## Penyeberangan feri

Rute mode `DRIVE` dapat memuat langkah feri. Sistem mendeteksi manuver `FERRY`
atau `FERRY_TRAIN`, mempertahankan jarak serta durasi pelayaran sebagai informasi
perjalanan, tetapi menetapkan konsumsi traksi segmen tersebut menjadi nol. Beban
aksesori kendaraan selama menunggu atau berlayar tidak dimodelkan.

Deteksi Google bukan jaminan bahwa kapal sedang beroperasi, mempunyai ruang,
atau menerima jenis kendaraan pengguna. Semua rute feri diberi status
kondisional dan pengguna wajib mengonfirmasi jadwal, cuaca, antrean, kapasitas,
serta aturan operator. Rincian metodologinya tersedia pada
[`ferry_routes.md`](ferry_routes.md).

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
    "maximum_range_km": 430,
    "current_soc_percent": 80,
    "connectors": ["AC TYPE 2", "CCS2"]
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
hard cap total detour 20 km juga dikelola backend dan divalidasi ulang terhadap
rute final;
perangkat eksperimen dapat menetapkannya secara eksplisit. Baseline kandidat
memakai CCS2 dengan fallback AC Type 2; sensitivitas konektor membandingkannya
dengan CCS2-only, sedangkan hasil historis tetap CCS2-only. Kebijakan fallback
hanya berlaku pada pilihan tepat Combo 2; kombinasi multi-konektor lainnya
diperlakukan setara.

Respons sukses berisi rute dasar, statistik kandidat dan graf, hasil optimasi,
rute rekomendasi, serta statistik penggunaan API. Untuk setiap itinerary
feasible, `optimization.final_route_validation.status` harus `passed` agar rute
final dikembalikan. Rute yang tidak feasible tetap merupakan hasil
perhitungan yang valid dan dikembalikan dengan HTTP 200, tetapi
`optimization.feasible` bernilai `false`.

Untuk Route Matrix, `ROUTE_EXISTS` wajib membawa jarak dan durasi. Satu pengecualian
fail-safe berlaku ketika origin dan destination benar-benar identik: Google dapat
menghilangkan `distanceMeters` dan mengembalikan durasi `0s`; adapter menormalkannya
menjadi jarak/durasi nol. Pasangan nonidentik yang kehilangan field tetap ditolak
sebagai `invalid_response`.
