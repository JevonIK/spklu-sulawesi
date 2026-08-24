# Hasil analisis sensitivitas live

> **Batas provenance:** dokumen ini merangkum laporan live historis schema 2
> dengan definisi skenario schema 1 tertanam, dibuat aplikasi 0.10.0. Kandidat
> analisis 0.18.0 hanya membaca snapshot secara offline dan bukan versi yang
> menghasilkan request live tersebut.

## Identitas eksperimen

Analisis sensitivitas dijalankan pada 13 Agustus 2026 menggunakan aplikasi
versi 0.10.0 dan koridor Makassar–Rantepao. Tujuh skenario mengubah satu
parameter pada satu waktu terhadap baseline: safety factor 0,8/0,9/1,0, radius
koridor 5/10/15 km, dan interval SOC 2,5/5/10%. Kendaraan memiliki jangkauan
maksimum 300 km, SOC awal 80%, SOC minimum 20%, target SOC 80%, dan konektor
CCS2.

Semua skenario selesai, feasible, dan tidak memiliki pelanggaran SOC. Nilai
waktu hanya menunjukkan waktu berkendara; waktu pengisian tidak dihitung.

Laporan historis tidak merekam `route_sample_step_km`. Nilai 5 km pada definisi
skenario schema 2 saat ini berlaku untuk run baru dan tidak boleh dianggap
sebagai metadata yang terbukti untuk run ini.
Laporan juga tidak merekam checksum dataset, sehingga kesamaan byte dengan file
kandidat saat ini tidak dapat dibuktikan dari jumlah skenario atau hasilnya.

## Hasil per skenario

| Skenario | Kandidat / edge | Perhentian | Jarak jalan | SOC minimum | State / transisi DP | Elemen Matrix |
|---|---:|---:|---:|---:|---:|---:|
| Baseline: alpha 0,9; radius 10 km; SOC 5% | 15 / 93 | 1 | 316,931 km | 20,329% | 41 / 425 | 105 |
| Alpha 0,8 | 15 / 70 | 3 | 317,940 km | 21,969% | 38 / 269 | 94 |
| Alpha 1,0 | 15 / 97 | 1 | 316,931 km | 21,296% | 42 / 401 | 105 |
| Radius 5 km | 14 / 82 | 1 | 316,931 km | 20,329% | 40 / 415 | 93 |
| Radius 15 km | 15 / 93 | 1 | 316,931 km | 20,329% | 41 / 425 | 105 |
| Interval SOC 2,5% | 15 / 93 | 1 | 316,931 km | 20,329% | 86 / 1.702 | 105 |
| Interval SOC 10% | 15 / 93 | 1 | 316,931 km | 20,329% | 27 / 177 | 105 |

Baseline, kedua variasi radius, dan kedua variasi interval SOC memilih SPKLU
LAGOTA CAFE. Alpha 1,0 juga memilih lokasi yang sama, tetapi cukup berangkat dari
SPKLU pada SOC 75% karena konsumsi model lebih rendah. Alpha 0,8 memilih tiga
perhentian: SPKLU PLN ULP MAROS, SPKLU LAGOTA CAFE, dan SPKLU PLN UP3 PINRANG.

## Pengaruh safety factor

Penurunan alpha dari 0,9 menjadi 0,8 mengurangi usable range setelah pengisian
dari 162 km menjadi 144 km. Edge graf turun dari 93 menjadi 70 dan elemen yang
perlu divalidasi turun dari 105 menjadi 94. Rute tetap feasible, tetapi jumlah
perhentian meningkat dari satu menjadi tiga, jarak bertambah 1,009 km, dan waktu
berkendara bertambah 4,3 menit.

Peningkatan alpha menjadi 1,0 memberi usable range 180 km dan menambah edge graf
menjadi 97. Rute, jarak, waktu berkendara, dan lokasi perhentian sama dengan
baseline, sedangkan SOC minimum meningkat menjadi 21,296%. Hasil ini menunjukkan
bahwa safety factor memengaruhi struktur graf, konsumsi SOC, dan kebutuhan
perhentian walaupun origin dan destination tidak berubah.

## Pengaruh radius koridor

Radius 5 km mengurangi kandidat dari 15 menjadi 14, edge dari 93 menjadi 82, dan
elemen Matrix dari 105 menjadi 93 tanpa mengubah itinerary terpilih. Radius 15 km
tidak menambah kandidat dibanding radius 10 km sehingga seluruh hasilnya sama
dengan baseline. Pada koridor ini, tidak ada node CCS2 tambahan dalam pita 10–15
km dari rute yang lolos proses pencarian kandidat.

Temuan tersebut khusus untuk Makassar–Rantepao dan dataset saat eksperimen. Ia
tidak membuktikan bahwa radius 10 dan 15 km selalu setara pada koridor lain.

## Pengaruh interval SOC

Perubahan interval SOC tidak mengubah graf atau itinerary karena parameter ini
bekerja pada state optimizer setelah graf dibentuk. Interval 2,5% meningkatkan
state yang diproses dari 41 menjadi 86 dan transisi yang dievaluasi dari 425
menjadi 1.702. Interval 10% menurunkannya menjadi 27 state dan 177 transisi.

Itinerary ketiganya sama karena target SOC 80% selalu dimasukkan sebagai level
eksplisit oleh optimizer. Satu run live tidak cukup untuk menyimpulkan hubungan
runtime secara statistik karena waktu pengukuran juga mencakup latensi jaringan.
Perbandingan state dan transisi merupakan bukti komputasi yang lebih langsung.

## Audit hard limit API

Sebelum eksekusi, pemakaian diperkirakan sebesar 7–14 Compute Routes dan sekitar
700–850 elemen Route Matrix. Hard cap ditetapkan menjadi 14 Compute Routes,
10 per menit, 2 per skenario, 1.200 elemen Matrix, dan 625 elemen Matrix per
menit. Skenario dijalankan berurutan dalam batch berisi dua dengan jeda 61 detik.

Percobaan pertama tidak dapat keluar dari sandbox dan seluruh skenario berhenti
pada Compute Routes pertama. Tidak ada retry otomatis. Percobaan tersebut
mencatat tujuh attempt Compute Routes dan nol elemen Matrix; ledger tetap
menghitungnya secara konservatif meskipun request tidak berhasil mencapai
layanan Google.

Setelah penyebab diketahui, tepat satu rerun terkontrol dijalankan melalui akses
jaringan. Rerun berhasil memakai:

| Dimensi | Estimasi | Hard cap rerun | Aktual rerun |
|---|---:|---:|---:|
| Compute Routes | 7–14 | 14 | 14 |
| Elemen Route Matrix | 700–850 | 1.200 | 712 |
| Request HTTP Route Matrix | – | dibatasi melalui elemen | 97 |
| Places Autocomplete | 0 | 0 untuk CLI | 0 |
| Get Place | 0 | 0 untuk CLI | 0 |
| Map loads | 0 | 0 untuk CLI | 0 |
| API terlarang | 0 | 0 | 0 |

Total sesi sensitivitas menurut ledger adalah 21 attempt Compute Routes dan 712
elemen Matrix, termasuk tujuh attempt yang gagal karena konektivitas. Setelah
digabung dengan dua run baseline sebelumnya, ledger hari quota `2026-08-12`
Pacific Time mencatat 39/100 Compute Routes dan 1.012/2.000 elemen Matrix. Sisa
yang tercatat adalah 61 Compute Routes dan 988 elemen Matrix, tanpa reservasi
aktif.

Batas 10 Compute Routes dan 625 elemen Matrix per menit pada bagian ini adalah
konfigurasi historis saat eksperimen dijalankan. Kebijakan kandidat 0.18.0 saat
ini memakai batas menit 100 Compute Routes dan 2.000 elemen Matrix, sama dengan
batas hariannya; perubahan tersebut tidak merevisi ledger atau hasil historis.

## Integritas artefak lokal

Laporan mentah berhasil berada pada folder yang diabaikan Git:

```text
reports/generated/sensitivitas-live-20260813-rerun1.json
reports/generated/sensitivitas-live-20260813-rerun1.csv
```

Hash SHA-256 laporan berhasil:

```text
JSON  a46b02163bd443db9516d8da1cd42d49e4ed2e53b458a48d6fdf45f0d97a7d3c
CSV   2c0f41cdb940963aa5d3c4a3ec5fc9d0e20419c81f7b9e0c4b0c0fd386728786
```

Laporan percobaan gagal juga dipertahankan sebagai jejak audit dengan suffix
tanpa `rerun1`. Jangan mengubah artefak mentah setelah hash dicatat.

## Batas kesimpulan

- Analisis hanya menggunakan satu koridor dan satu konfigurasi kendaraan.
- Setiap variasi dijalankan satu kali; runtime dan memori belum memiliki
  replikasi statistik.
- Model SOC linier tidak memasukkan elevasi, cuaca, kemacetan, degradasi baterai,
  gaya mengemudi, status operasional charger, atau antrean.
- Perubahan data jalan Google atau dataset dapat menghasilkan angka berbeda pada
  replikasi berikutnya.
- Feasible berarti layak menurut model dan parameter penelitian, bukan jaminan
  kondisi perjalanan aktual.
- Klaim nol pelanggaran SOC berasal dari simulasi itinerary pada 0.10.0.
  Rekonsiliasi SOC berdasarkan setiap leg Compute Routes final pada 0.18.0 belum
  dijalankan terhadap run historis ini.
- Provenance, periode pengumpulan, metode kompilasi, dan quality assurance
  dataset telah terdokumentasi; sumber dapat diakses publik, tetapi tidak
  ditemukan lisensi open-data eksplisit atau pernyataan hak redistribusi sumber.
