# Referensi API aplikasi

Seluruh endpoint menggunakan JSON dan mengirim header `Cache-Control: no-store`.
Endpoint rekomendasi memanggil Google Routes API sehingga hanya boleh digunakan
setelah server key, quota, dan izin pengujian live diperiksa.

## `GET /api/health`

Mengembalikan kesiapan aplikasi tanpa memanggil Google. HTTP 200 menunjukkan
dataset dan komponen lokal berhasil dimuat. Field konfigurasi key hanya berupa
boolean; nilai key tidak pernah dikirim.

Contoh bagian penting respons:

```json
{
  "status": "ok",
  "service": "spklu-sulawesi",
  "version": "0.13.0",
  "data": {
    "dataset": {
      "filename": "dataset_spklu_sulawesi.csv",
      "sha256": "24992e1225209ed5a2833b8722be6bfabfc94cdc55f795acdf5edf10c21ffa85",
      "source_rows": 150,
      "logical_nodes": 149
    },
    "google_maps": {
      "browser_key_configured": true,
      "server_key_configured": true,
      "recommendation_endpoint_ready": true
    }
  }
}
```

## `GET /api/stations/summary`

Mengembalikan jumlah baris, node logis, distribusi provinsi/konektor, daftar
lokasi multi-unit, warning konsolidasi, dan SHA-256 dataset. Endpoint tidak
memanggil layanan eksternal.

## `POST /api/recommendations`

Menyusun rekomendasi dari koordinat yang dipilih pengguna. Request body:

```json
{
  "origin": {
    "latitude": -5.148463607,
    "longitude": 119.4158186
  },
  "destination": {
    "latitude": -2.972703162,
    "longitude": 119.8979519
  },
  "vehicle": {
    "maximum_range_km": 300,
    "current_soc_percent": 80,
    "connectors": ["CCS2", "CHADEMO"]
  },
  "options": {
    "minimum_soc_percent": 20,
    "target_soc_percent": 80
  }
}
```

`options` boleh dihilangkan dan akan memakai default environment. Endpoint web
hanya menerima pilihan SOC minimum dan target dari pengguna. Safety factor,
radius koridor, interval SOC, serta langkah sampling ditetapkan oleh konfigurasi
backend. Variasi parameter tersebut tetap dapat digunakan oleh perangkat
eksperimen CLI yang terdokumentasi. Aturan input:

| Field | Aturan |
|---|---|
| latitude / longitude | koordinat finite dan valid; origin berbeda dari destination |
| `maximum_range_km` | lebih besar dari 0 dan maksimal 2.000 km |
| `current_soc_percent` | di atas SOC minimum dan maksimal 100% |
| `minimum_soc_percent` | 0 sampai kurang dari 100% |
| `target_soc_percent` | lebih besar dari SOC minimum dan maksimal 100% |
| `connectors` | daftar berisi sedikitnya satu dari `AC TYPE 2`, `CCS2`, `CHADEMO`, atau `GB/T` |

Node SPKLU dianggap kompatibel jika mendukung sedikitnya satu konektor yang
dipilih. Field tunggal `vehicle.connector` tetap diterima untuk kompatibilitas
dengan skenario eksperimen dan klien versi lama. Respons ternormalisasi memuat
`connectors` serta `connector` sebagai konektor utama kompatibilitas lama.

Respons HTTP 200 selalu berarti pipeline selesai, bukan selalu feasible. Periksa
`data.optimization.feasible`:

- `true`: `itinerary` dan `recommended_route` tersedia;
- `false`: hasil penelitian valid tetapi rute aman tidak ditemukan;
  `itinerary` dan `recommended_route` dapat bernilai `null`.

Objek `data` mencakup request ternormalisasi, parameter energi, rute dasar,
jumlah kandidat, statistik graf, hasil DP, rute rekomendasi, dan pemakaian API.
Waktu yang dilaporkan adalah waktu berkendara, bukan waktu pengisian.

`data.quota_guard` membedakan attempt aktual dari request logis yang berhasil.
Objek ini memuat attempt Compute Routes/Matrix pada request tersebut, tanggal
quota Pacific Time, pemakaian harian, serta sisa harian dan rolling window
60 detik menurut ledger lokal.

## Respons error

Semua error memakai envelope berikut tanpa stack trace atau isi respons Google:

```json
{
  "status": "error",
  "error": {
    "code": "validation_error",
    "message": "Pesan aman untuk pengguna"
  }
}
```

| HTTP | Code | Arti |
|---:|---|---|
| 400 | `invalid_json` | body bukan JSON |
| 400 | `validation_error` | field input tidak valid; field penyebab ikut dikirim |
| 404 | `not_found` | endpoint API tidak tersedia |
| 405 | `method_not_allowed` | metode HTTP salah |
| 413 | `payload_too_large` | body melewati 64 KiB secara default |
| 429 | `local_quota_exceeded` atau kode budget | quota lokal habis, request paralel, atau hard cap tercapai |
| 502 | kode aman Google Routes | upstream menolak, timeout, atau respons tidak valid |
| 503 | `configuration_error` | server key belum tersedia |
| 500 | `internal_error` | kesalahan internal yang sudah disanitasi |

Tidak ada retry otomatis pada adapter Google Routes. Pemanggil dapat menawarkan
aksi coba lagi kepada pengguna, tetapi setiap pengulangan live tetap harus
mematuhi hard limit dan dicatat sebagai request baru.
