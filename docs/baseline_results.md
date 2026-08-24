# Hasil baseline live enam wilayah

> **Batas provenance:** dokumen ini merangkum laporan live historis schema 2
> dengan definisi skenario schema 1 tertanam, dibuat aplikasi 0.9.2. Kandidat
> analisis 0.18.0 tidak menjalankan ulang request tersebut dan tidak boleh
> dicantumkan sebagai versi penghasil hasil.

## Identitas eksperimen

Baseline live dijalankan pada 13 Agustus 2026 menggunakan aplikasi versi 0.9.2,
dataset 150 baris yang terkonsolidasi menjadi 149 node lokasi, konektor CCS2,
jangkauan maksimum kendaraan 300 km, SOC awal 80%, SOC minimum 20%, target SOC
80%, safety factor 0,9, interval SOC 5%, dan radius koridor 10 km.

Jumlah data tersebut adalah konteks dokumentasi proyek; laporan mentah tidak
merekam checksum dataset. Karena itu, kesamaan byte dengan dataset kandidat
0.18.0 tidak dapat dibuktikan hanya dari laporan historis.
Dataset kandidat terbaru kini tetap memiliki 150 baris tetapi terkonsolidasi
menjadi 146 node setelah revisi koordinat/link. Perbedaan jumlah node ini
menegaskan bahwa dataset terbaru tidak boleh dipakai sebagai pengganti input run
historis atau untuk mengubah angka hasil baseline tanpa eksperimen live baru.

Usable range awal dan setelah pengisian sampai target sama-sama 162 km:

```text
(80% - 20%) / 100 × 300 km × 0,9 = 162 km
```

Enam skenario dibagi menjadi dua batch yang masing-masing berisi tiga skenario,
dengan jeda 61 detik setelah batch pertama. Estimasi waktu pengisian tidak
dihitung; seluruh nilai waktu pada dokumen ini adalah waktu berkendara.

Laporan historis tidak merekam `route_sample_step_km`. Definisi skenario schema 2
saat ini menetapkan 5 km untuk run baru, tetapi nilai itu tidak digunakan untuk
mengisi metadata run lama melalui asumsi.

## Hasil per wilayah

| Wilayah dan koridor | Status | SPKLU terpilih | Jarak itinerary | Waktu berkendara | SOC minimum | Kandidat / edge |
|---|---|---|---:|---:|---:|---:|
| Sulawesi Selatan: Makassar–Rantepao | Feasible | SPKLU LAGOTA CAFE | 316,931 km | 461,17 menit | 20,33% | 15 / 93 |
| Sulawesi Tengah: Palu–Moutong | Tidak feasible (`graph_disconnected`) | – | – | – | – | 5 / 5 |
| Sulawesi Tenggara: Kolaka–Kendari | Tidak feasible (`graph_disconnected`) | – | – | – | – | 3 / 2 |
| Sulawesi Utara: Bintauna–Manado | Feasible | SPKLU PLN ULP INOBONTO | 231,322 km | 327,22 menit | 23,94% | 6 / 15 |
| Sulawesi Barat: Polewali–Mamuju | Tidak feasible (`graph_disconnected`) | – | – | – | – | 2 / 0 |
| Gorontalo: Marisa–Kota Gorontalo | Feasible | SPKLU ULP LIMBOTO | 158,578 km | 236,07 menit | 25,02% | 3 / 2 |

Tiga dari enam skenario menghasilkan itinerary feasible sehingga route
feasibility rate baseline adalah 50%. Semua itinerary feasible memiliki satu
perhentian dan tidak ada leg yang tiba di bawah SOC minimum. Rata-rata jumlah
perhentian pada skenario feasible adalah 1,0.

## Rincian itinerary feasible

### Sulawesi Selatan

1. Lokasi awal → SPKLU LAGOTA CAFE: 155,819 km; SOC 80% → 22,29%.
2. Pengisian dimodelkan dari 22,29% menjadi 80%. Tidak ada waktu pengisian yang
   dihitung.
3. SPKLU LAGOTA CAFE → lokasi tujuan: 161,112 km; SOC 80% → 20,33%.

Total detour estimator adalah 0,342 km. Kandidat 15 node menghasilkan 14 node
SPKLU kompatibel di dalam graf, 105 pasangan yang divalidasi melalui Route
Matrix, dan 93 edge yang diterima. DP memproses 41 state dan mengevaluasi 425
transisi.

### Sulawesi Utara

1. Lokasi awal → SPKLU PLN ULP INOBONTO: 93,464 km; SOC 80% → 45,38%.
2. Pengisian dimodelkan dari 45,38% menjadi 75%.
3. SPKLU PLN ULP INOBONTO → lokasi tujuan: 137,858 km; SOC 75% → 23,94%.

Total detour estimator adalah 0,113 km. Sebanyak 21 pasangan jalan divalidasi
dan 15 edge diterima. DP memproses 52 state serta mengevaluasi 518 transisi.

### Gorontalo

1. Lokasi awal → SPKLU ULP LIMBOTO: 145,143 km; SOC 80% → 26,24%.
2. Pengisian dimodelkan dari 26,24% menjadi 30%.
3. SPKLU ULP LIMBOTO → lokasi tujuan: 13,435 km; SOC 30% → 25,02%.

Total detour estimator adalah 1,245 km. Tiga pasangan jalan divalidasi dan dua
edge diterima. DP memproses 13 state serta mengevaluasi 12 transisi.

## Interpretasi skenario tidak feasible

Ketiga skenario tidak feasible berstatus `graph_disconnected`, bukan error API
dan bukan kegagalan DP. Artinya, setelah filter koridor, kompatibilitas CCS2,
pemangkasan geodesik, dan validasi jarak jalan, graf tidak memiliki rangkaian
edge dari origin ke destination yang setiap leg-nya berada dalam usable range
162 km.

- Palu–Moutong memiliki rute dasar 340,725 km. Dari 15 pasangan maju, enam
  dipangkas secara geodesik, dua tidak memiliki rute jalan yang tersedia, dua
  melampaui batas berdasarkan jarak jalan, dan hanya lima edge diterima.
- Kolaka–Kendari memiliki rute dasar 165,927 km, sedikit di atas usable range.
  Dari enam pasangan, satu tidak tersedia dan tiga melampaui batas jarak jalan,
  sehingga dua edge yang tersisa belum menghubungkan origin ke destination.
- Polewali–Mamuju memiliki rute dasar 195,172 km. Dua pasangan tidak tersedia
  dan empat pasangan melampaui batas jarak jalan; tidak ada edge yang diterima.

Hasil infeasible tetap merupakan hasil penelitian yang valid untuk parameter
baseline. Hasil ini tidak berarti seluruh kendaraan atau seluruh konfigurasi
selalu gagal; analisis sensitivitas perlu menguji perubahan parameter secara
terpisah.

## Kinerja komputasi dan quota API

Pada run terperinci, rata-rata runtime per skenario adalah 1.166,48 ms dan peak
memory maksimum yang diamati adalah 3,676 MB. Total penggunaan terdiri atas
sembilan panggilan Compute Routes, 31 request Route Matrix, dan 150 elemen Route
Matrix. Tidak ada error upstream atau penantian otomatis akibat rolling window.

Satu run awal dilakukan sebelum schema laporan diperluas, kemudian run terperinci
diulang untuk menyimpan nama SPKLU, setiap leg, dan statistik pemangkasan. Kedua
run menghasilkan status kelayakan dan metrik numerik algoritmik yang sama.
Pemakaian kumulatif hari itu adalah:

| Dimensi quota | Run awal | Run terperinci | Total | Quota harian project |
|---|---:|---:|---:|---:|
| Compute Routes | 9 | 9 | 18 | 100 per hari, 30 per menit |
| Elemen Route Matrix | 150 | 150 | 300 | 2.000 per hari, 625 per menit |

Masing-masing run memakai dua batch dengan jeda 61 detik. Maksimum kumulatif
Compute Routes per skenario adalah empat untuk skenario feasible dan dua untuk
skenario infeasible, masih di bawah batas 10 per skenario.

Izin pengujian menetapkan hard cap gabungan maksimum 60 Compute Routes untuk
baseline, sedangkan 100 adalah quota harian project. Pemakaian aktual 18 tidak
melewati keduanya. Kedua laporan telah diimpor ke ledger dan tercatat pada hari
quota `2026-08-12` Pacific Time; waktu eksekusinya adalah 13 Agustus di
Indonesia. Perbedaan tanggal ini mengikuti reset quota Google pada tengah malam
Pacific Time.

Nilai 30 dan 625 per menit pada tabel adalah batas yang berlaku ketika baseline
historis dijalankan. Kebijakan kandidat 0.18.0 saat ini memakai 100 Compute
Routes dan 2.000 elemen Matrix per menit, tetap dengan batas harian 100/2.000;
perubahan tersebut tidak mengubah catatan pemakaian historis.

## Integritas artefak lokal

Laporan mentah berada di folder yang diabaikan Git:

```text
reports/generated/baseline-live-20260813-detailed.json
reports/generated/baseline-live-20260813-detailed.csv
```

Hash SHA-256 setelah eksperimen:

```text
JSON  40074a65d5e0d58ed6ae8f4e61f5d28ecb7958f8f67aaa8729c09de8b20a5f51
CSV   90c7ded8687c25cf251163a2c25a3c92f4cdf3f9dbf14e2a3f01b9b7b3c27928
```

Jangan mengubah laporan mentah setelah hash dicatat. Jika eksperimen direplikasi,
gunakan label baru dan laporkan hasilnya sebagai run terpisah karena rute Google,
dataset, serta kondisi layanan dapat berubah.

## Batas kesimpulan

- Baseline hanya mencakup satu koridor per wilayah dan belum mewakili seluruh
  pasangan origin-destination di Sulawesi.
- Model SOC bersifat linier berbasis jangkauan efektif dan safety factor; model
  ini tidak memasukkan cuaca, elevasi, kemacetan, degradasi baterai, atau gaya
  mengemudi.
- Sistem tidak memeriksa status operasional, antrean, ataupun daya charger.
- Detour merupakan estimator per edge terhadap progres rute, bukan selalu selisih
  langsung antara jarak rute rekomendasi dan rute dasar yang dihitung ulang.
- Waktu yang dilaporkan hanya waktu berkendara, bukan waktu perjalanan termasuk
  pengisian.
- Klaim nol pelanggaran SOC berasal dari simulasi itinerary pada implementasi
  0.9.2. Validasi ulang per-leg Compute Routes final yang tersedia di 0.18.0
  belum dijalankan terhadap run historis ini, sehingga keduanya tidak boleh
  disamakan.
- Provenance, periode pengumpulan, metode kompilasi, dan quality assurance
  dataset telah terdokumentasi; checksum mengidentifikasi file yang digunakan,
  tetapi tidak menggantikan izin redistribusi dari pemilik sumber.
