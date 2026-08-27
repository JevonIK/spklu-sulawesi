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
  "version": "0.18.0",
  "data": {
    "dataset": {
      "filename": "dataset_spklu_sulawesi.csv",
      "sha256": "9c99d5e8e2cf8c595d81ccc184b211d1d6acb8d12bf4b3eb0b4df4d8eed41454",
      "source_rows": 150,
      "logical_nodes": 146
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
    "maximum_range_km": 430,
    "current_soc_percent": 80,
    "connectors": ["AC TYPE 2", "CCS2"]
  },
  "options": {
    "minimum_soc_percent": 20,
    "target_soc_percent": 80,
    "additional_charging_networks": ["HYUNDAI", "TOYOTA"],
    "allow_ferries": true
  }
}
```

`options` boleh dihilangkan dan akan memakai default environment. SPKLU publik
selalu disertakan, sedangkan `additional_charging_networks` menerima nol atau
lebih nilai `HYUNDAI`, `WULING`, dan `TOYOTA`. Endpoint web menerima pilihan SOC,
konektor, dan jaringan tambahan dari pengguna. Safety factor, radius koridor,
interval SOC, serta langkah sampling ditetapkan oleh konfigurasi backend.
Hard cap total detour juga ditetapkan backend; baseline 20 km berasal dari dua
kali radius koridor 10 km dan tidak dapat diubah melalui endpoint publik.
Variasi parameter tersebut tetap dapat digunakan oleh perangkat eksperimen CLI
yang terdokumentasi. Aturan input:

| Field | Aturan |
|---|---|
| latitude / longitude | koordinat finite dan valid; origin berbeda dari destination |
| `maximum_range_km` | lebih besar dari 0 dan maksimal 2.000 km |
| `current_soc_percent` | di atas SOC minimum dan maksimal 100% |
| `minimum_soc_percent` | 0 sampai kurang dari 100% |
| `target_soc_percent` | lebih besar dari SOC minimum dan maksimal 100% |
| `connectors` | daftar berisi sedikitnya satu dari `AC TYPE 2`, `CCS2`, `CHADEMO`, atau `GB/T` |
| `additional_charging_networks` | daftar unik dari `HYUNDAI`, `WULING`, atau `TOYOTA`; boleh kosong |
| `allow_ferries` | boolean; default `true`; jika `false`, Compute Routes diminta menghindari feri dan hasil ditolak bila feri tetap diperlukan |

Node SPKLU dianggap kompatibel jika mendukung sedikitnya satu konektor yang
dipilih pada unit yang juga memenuhi aturan akses jaringan. Memilih suatu
jaringan tidak membuat konektor yang tidak kompatibel menjadi valid. Field
tunggal `vehicle.connector` tetap diterima untuk kompatibilitas dengan skenario
eksperimen dan klien versi lama. Respons ternormalisasi memuat `connectors` serta
`connector` sebagai konektor utama kompatibilitas lama. Untuk pasangan Combo 2,
`preferred_connector` bernilai CCS2 dan `fallback_connectors` memuat AC Type 2.

Respons HTTP 200 selalu berarti pipeline selesai, bukan selalu feasible. Periksa
`data.optimization.feasible`:

- `true`: `itinerary` dan `recommended_route` tersedia;
- `false`: hasil penelitian valid tetapi rute aman tidak ditemukan;
  `itinerary` dan `recommended_route` dapat bernilai `null`.

Objek `data` mencakup request ternormalisasi, parameter energi, rute dasar,
jumlah kandidat sebelum/sesudah filter jaringan, statistik graf, hasil DP, rute
rekomendasi, `route_access`, dan pemakaian API. `route_access.status` bernilai
`public`, `conditional`, atau `not_applicable` untuk hasil tidak feasible;
status kondisional berarti sedikitnya satu charger dealer, fallback AC Type 2,
atau penyeberangan feri dipakai. `route_access.ac_fallback_stop_count` dan field
station `route_selected_connector` menjelaskan fallback. `route_access.ferry`
memuat status, jumlah segmen, jarak, durasi, serta penanda bahwa dukungan
kendaraan harus dikonfirmasi kepada operator. Nilai waktu merepresentasikan
durasi perjalanan Google Routes.
Request ternormalisasi memuat `max_total_detour_km`. Statistik optimizer memuat
`detour_pruned_transitions`; hasil yang kehilangan seluruh jalur karena cap
menggunakan reason `detour_infeasible`.

Itinerary memisahkan `total_road_distance_km` sebagai jarak perjalanan total,
`total_energy_distance_km` sebagai jarak darat yang mengurangi SOC, serta
`total_ferry_distance_km` dan `total_ferry_duration_minutes`. Setiap leg juga
memuat `energy_distance_km`, `ferry_distance_km`, dan `contains_ferry`.

Compute Routes memakai `HIGH_QUALITY` dan `TRAFFIC_UNAWARE`; durasi tidak
memasukkan lalu lintas real-time/prediktif. Untuk setiap rute feasible,
`data.optimization.final_route_validation.status` bernilai `passed` setelah SOC
setiap leg rute final divalidasi ulang. Objek tersebut juga memuat jumlah leg,
jarak matriks, jarak rute final, selisih keduanya, dan SOC minimum teramati.
Untuk rute feri, validasi juga mencatat jarak energi dan jumlah segmen feri.
Validasi final mencatat `max_total_detour_km` dan `total_detour_km`. Rute yang
melampaui cap ditolak dengan error aman `final_route_detour_violation`.

`data.quota_guard` membedakan attempt aktual dari request logis yang berhasil.
Objek ini memuat attempt Compute Routes/Matrix pada request tersebut, tanggal
quota Pacific Time, pemakaian harian, serta sisa harian dan rolling window
60 detik menurut ledger lokal. Batas menit default sama dengan batas harian,
sehingga statistik window tetap tersedia tanpa memaksa jeda tambahan.

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
| 502 | `final_route_leg_mismatch` | jumlah leg rute final tidak sesuai itinerary |
| 502 | `final_route_soc_violation` | rute final melanggar SOC minimum dan tidak ditampilkan |
| 503 | `configuration_error` | server key belum tersedia |
| 500 | `internal_error` | kesalahan internal yang sudah disanitasi |

Tidak ada retry otomatis pada adapter Google Routes. Pemanggil dapat menawarkan
aksi coba lagi kepada pengguna, tetapi setiap pengulangan live tetap harus
mematuhi hard limit dan dicatat sebagai request baru.
