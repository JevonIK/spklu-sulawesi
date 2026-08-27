# Hasil sensitivitas hard cap total detour

## Identitas dan provenance

Eksperimen live selesai pada 24 Agustus 2026 menggunakan aplikasi 0.18.0,
dataset 150 baris/146 node dengan SHA-256
`9c99d5e8e2cf8c595d81ccc184b211d1d6acb8d12bf4b3eb0b4df4d8eed41454`,
dan definisi `experiments/scenarios_detour_multicorridor.json` dengan SHA-256
`9fe160c0efd02f7544b4beaac3049c74ea735b994f3d657fd4f7bca5fc396742`.

Sembilan skenario membandingkan cap 10/20/30 km pada:

- koridor pendek Gorontalo, 162,448 km;
- koridor menengah Sulawesi Utara, 231,321 km; dan
- koridor panjang Sulawesi Selatan, 316,726 km.

Parameter lain tetap: range 430 km, SOC awal/target 80%, SOC minimum 20%, safety
factor 0,9, interval SOC 5%, radius koridor 10 km, sampling 5 km, jaringan
publik, serta konektor AC Type 2 + CCS2 dengan prioritas CCS2.

Laporan sumber lokal:

```text
JSON  43d4620eea38b370600283b4a489bc26e4c07042c2f3444d5fe6921f9c572063
CSV   654975594382229b13439a99d7d8f4ae2e5fe47bfbc7d7cbb2981e1c4a39756c
```

Snapshot yang dilacak untuk notebook:

```text
notebooks/data/detour_sensitivity_results.csv
SHA-256 361ee6e65ab451f9a00be39b3ee711844fba7a84380332f0a15ab9a5d7cf065c
```

## Hasil utama

| Koridor | Cap | Feasible | Stop | SPKLU | Detour final | SOC minimum | Transisi dipangkas detour |
|---|---:|---|---:|---|---:|---:|---:|
| Pendek | 10 km | Ya | 0 | – | 0 km | 38,024% | 0 |
| Pendek | 20 km | Ya | 0 | – | 0 km | 38,024% | 0 |
| Pendek | 30 km | Ya | 0 | – | 0 km | 38,024% | 0 |
| Menengah | 10 km | Ya | 0 | – | 0 km | 20,227% | 716 |
| Menengah | 20 km | Ya | 0 | – | 0 km | 20,227% | 156 |
| Menengah | 30 km | Ya | 0 | – | 0 km | 20,227% | 0 |
| Panjang | 10 km | Ya | 1 | SPKLU LAGOTA CAFE | 0,205 km | 23,368% | 59 |
| Panjang | 20 km | Ya | 1 | SPKLU LAGOTA CAFE | 0,205 km | 23,368% | 0 |
| Panjang | 30 km | Ya | 1 | SPKLU LAGOTA CAFE | 0,205 km | 23,368% | 0 |

Seluruh skenario selesai tanpa error dan tanpa pelanggaran SOC. Di dalam setiap
koridor, cap 10/20/30 km menghasilkan feasibility, stop, SPKLU, rute final, dan
SOC minimum yang sama. Perbedaan hanya terlihat pada jumlah transisi DP yang
dipangkas.

## Interpretasi

Hasil ini **tidak membuktikan 20 km sebagai nilai optimum unik**. Cap 10 km pun
tidak mengubah itinerary terpilih pada ketiga koridor. Bukti yang tersedia
mendukung kesimpulan lebih terbatas:

- 20 km tidak binding terhadap rekomendasi akhir pada tiga koridor uji;
- 20 km lebih permisif daripada 10 km sehingga memangkas lebih sedikit ruang
  state alternatif;
- 30 km tidak memberi perubahan itinerary dibanding 20 km;
- baseline 20 km tetap dapat dipertahankan sebagai kebijakan tengah yang
  diturunkan dari `2 ×` radius koridor, tetapi bukan preferensi pengguna yang
  tervalidasi.

## Pemakaian API dan audit kegagalan awal

Preflight akhir memperkirakan maksimum 18 Compute Routes dan 1.389 elemen
Matrix. Rerun berhasil menggunakan 12 Compute Routes dan tepat 1.389 elemen
Matrix, tanpa retry otomatis, paralelisasi, pacing, atau pelanggaran cap.

Ledger seluruh sesi—termasuk preflight, satu attempt DNS sandbox, run parsial,
dan dua diagnosis terkontrol—mencatat:

| Dimensi | Pemakaian sesi | Batas harian | Sisa |
|---|---:|---:|---:|
| Compute Routes | 30 attempt | 100 | 70 |
| Route Matrix | 1.843 elemen | 2.000 | 157 |

Run 0.17.0 pertama menyelesaikan tiga skenario pendek dan menghentikan enam
skenario lain karena elemen `ROUTE_EXISTS` zero-distance tidak membawa
`distanceMeters`. Diagnosis 1 elemen membuktikan origin/destination identik dan
durasi `0s`. Versi 0.18.0 kemudian:

1. mengeluarkan station dalam 0,05 km dari endpoint sebelum Matrix; dan
2. menerima jarak nol tanpa `distanceMeters` hanya untuk koordinat identik dan
   durasi nol.

Respons nonidentik yang tidak lengkap tetap fail-fast. Run parsial dipertahankan
lokal sebagai jejak audit dan tidak digunakan dalam tabel hasil final.

## Batas generalisasi

- Hanya tiga koridor dan satu waktu pengambilan data yang diuji.
- Dua koridor dapat ditempuh langsung dengan kendaraan referensi 430 km sehingga
  cap tidak memengaruhi stop.
- Detour akhir koridor panjang hanya 0,205 km, jauh di bawah semua cap.
- Tidak ada koridor uji yang berada dekat ambang 10/20/30 km.
- Antrean, daya charger, dan preferensi detour pengguna tidak dimodelkan.

Eksperimen berikutnya yang hendak mencari threshold optimum harus memilih
koridor dengan alternatif itinerary yang detournya mendekati ketiga cap, bukan
sekadar mengulang koridor ini.
