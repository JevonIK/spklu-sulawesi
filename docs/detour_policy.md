# Kebijakan hard cap total detour

Kandidat 0.18.0 membatasi total detour itinerary sebesar 20 km. Batas ini tidak
dipilih sebagai angka preferensi pengguna yang universal. Ia diturunkan dari
geometri baseline:

```text
radius koridor baseline       = 10 km
pengali keluar–kembali        = 2
hard cap total detour         = 2 × 10 km = 20 km
```

Interpretasinya adalah satu penyimpangan menuju lokasi di tepi koridor dan
kembali menuju arah rute utama. Jalan nyata dapat berkelok sehingga hubungan ini
bukan jaminan geometris eksak; karena itu 20 km disebut **reference policy** dan
bukan nilai optimum empiris.

## Definisi metrik

Untuk setiap edge graf:

```text
estimated_edge_detour = max(0, road_distance - base_route_progress_delta)
```

DP menjumlahkan estimasi tersebut sepanjang itinerary. Transisi ditolak ketika:

```text
cumulative_estimated_detour > max_total_detour_km
```

Statistik `detour_pruned_transitions` mencatat jumlah transisi yang dipangkas.
Jika tidak ada state tujuan setelah pruning dan sedikitnya satu transisi ditolak
oleh cap, reason hasil adalah `detour_infeasible`.

Setelah waypoint SPKLU terpilih, Compute Routes menghasilkan rute final. Sistem
kemudian menghitung ulang:

```text
final_total_detour = max(0, final_route_distance - base_route_distance)
```

Rute ditolak dengan `final_route_detour_violation` bila nilai final melebihi cap
20 km di luar toleransi jarak 0,05 km. Pemeriksaan kedua ini mencegah perbedaan
Route Matrix dan Compute Routes menghasilkan rekomendasi yang melewati batas.

## Sensitivitas

`experiments/scenarios_sensitivity.json` mendefinisikan satu-factor-at-a-time:

| Skenario | Makna relatif terhadap radius 10 km |
|---:|---|
| 10 km | `1 ×` radius; ketat |
| 20 km | `2 ×` radius; baseline |
| 30 km | `3 ×` radius; permisif |

Hasil live tiga koridor tersedia pada
[`detour_sensitivity_results.md`](detour_sensitivity_results.md). Seluruh cap
menghasilkan itinerary yang sama per koridor; perbedaannya hanya pada pruning
DP. Karena itu hasil tidak membuktikan 20 km sebagai optimum unik.

## Batas interpretasi

- Estimator graf bergantung pada progres terhadap satu rute dasar.
- Jumlah estimated edge detour dapat berbeda dari selisih rute final.
- Cap tidak berasal dari survei toleransi detour pengguna Sulawesi.
- Cap bersifat geometris dan tidak memasukkan antrean atau waktu tunggu feri.
- Rute lebih pendek daripada rute dasar memperoleh detour nol.

Dengan batas tersebut, klaim yang aman adalah bahwa sistem menerapkan kebijakan
detour eksplisit dan fail-safe. Sistem belum membuktikan bahwa 20 km merupakan
preferensi optimal seluruh pengguna.
