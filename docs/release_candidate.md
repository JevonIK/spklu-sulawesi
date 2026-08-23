# Kandidat rilis 0.17.0

Dokumen ini adalah identitas kandidat, bukan pernyataan bahwa deployment sudah
produksi. Status lulus hanya boleh diberikan setelah manifest 0.17.0 sinkron,
audit offline lulus, seluruh job GitHub Actions hijau, dan artefak run tersebut
diunduh serta diperiksa.

## Identitas

| Komponen | Nilai kandidat |
|---|---|
| Versi aplikasi/analisis | 0.17.0 |
| Dataset | 150 baris, 146 node logis |
| SHA-256 dataset | `9c99d5e8e2cf8c595d81ccc184b211d1d6acb8d12bf4b3eb0b4df4d8eed41454` |
| Provenance/lisensi dataset | `incomplete` / `unknown` |
| Konektor aplikasi | AC Type 2, CCS2, CHAdeMO, GB/T |
| Jaringan tambahan | Hyundai, Wuling, Toyota/Lexus |
| SPKLU publik | Selalu disertakan |
| Konektor eksperimen kandidat | CCS2 diprioritaskan; AC Type 2 fallback |
| Jangkauan referensi kandidat | 430 km (median WLTP 433 km dibulatkan ke 10 km) |
| Batas total detour | 20 km (`2 ×` radius koridor 10 km); sensitivitas 10/20/30 km |
| Schema skenario / laporan baru | 4 / 5 |
| Mode rute | `DRIVE`, `TRAFFIC_UNAWARE`, `HIGH_QUALITY` |
| Margin lower bound geodesik | 1% |
| Estimasi waktu pengisian | Tidak termasuk |
| Penyeberangan feri | Terdeteksi generik; jarak feri tidak mengurangi SOC; akses kendaraan kondisional |
| Python didukung | 3.11, 3.12, 3.13, 3.14 |
| Runtime container kandidat | Python 3.14 standar |

## Perubahan yang perlu diverifikasi

- laporan schema 5 merekam provenance source, data, skenario, dependency,
  manifest, parameter algoritma, dan lingkungan eksekusi;
- manifest rilis mengunci hash source scope `application-runtime-v2`, metadata
  dataset, definisi skenario, manifest penelitian, dependency, konstanta rute,
  margin geodesik, serta hard limit;
- Compute Routes memakai `HIGH_QUALITY` dan `TRAFFIC_UNAWARE`;
- prapemangkasan geodesik memakai lower bound dengan margin 1%;
- jarak setiap leg Compute Routes final divalidasi ulang terhadap SOC minimum;
- total detour dibatasi 20 km di DP dan divalidasi ulang terhadap rute final;
- CI mengunggah `coverage.xml`, `release-audit.json`, `container-health.json`,
  dan `container-release-audit.json` sebagai artefak 14 hari;
- container smoke test memakai root filesystem read-only, tanpa jaringan
  eksternal, semua capability dihapus, `no-new-privileges`, serta tmpfs terbatas;
- source di image dimiliki root dan harus tidak dapat ditulis oleh user runtime
  `spklu`; hanya direktori ledger/laporan yang diberi media tulis; dan
- audit serta test otomatis tidak memakai Google Maps API atau secret produksi.

Jangan menyalin angka jumlah test, coverage, atau check audit dari rilis lama.
Nilai final harus diambil dari artefak GitHub Actions untuk revision kandidat
0.17.0 yang sama. Keberhasilan versi sebelumnya tidak membuktikan image 0.17.0.

## Hard limit aktif

| Layanan/dimensi | Harian | Per menit |
|---|---:|---:|
| Compute Routes | 100 request | 100 request |
| Compute Route Matrix | 2.000 elemen | 2.000 elemen |
| Places Autocomplete | 500 request | 500 request |
| Get Place | 200 request | 200 request |
| Map loads | 100 load | 100 load |

Endpoint web juga dibatasi maksimal 2 Compute Routes dan 625 elemen Matrix per
request. Nilai di atas adalah kebijakan source saat ini; sebelum tindakan live,
operator tetap harus memeriksa bahwa override Google Cloud benar-benar aktif,
menghitung sisa pemakaian, dan memperoleh izin. API yang dilarang tetap tercantum
pada [`google_maps_api_limits.md`](google_maps_api_limits.md).

## Provenance bukti penelitian

Hasil penelitian yang tersedia tidak dibuat oleh 0.17.0:

| Artefak | Versi penghasil | Schema laporan | Ruang lingkup |
|---|---:|---:|---|
| Baseline enam wilayah | 0.9.2 | 2 | 6 skenario; 3 feasible |
| Sensitivitas Makassar–Rantepao | 0.10.0 | 2 | 7 skenario feasible |

Versi 0.17.0 adalah versi analisis dan kandidat untuk run berikutnya. Notebook
membaca snapshot historis secara offline. Klaim nol pelanggaran SOC pada hasil
lama berasal dari simulasi versi penghasilnya; fitur rekonsiliasi leg final
0.17.0 tidak dijalankan secara retroaktif. Laporan lama juga tidak merekam
langkah sampling rute atau checksum dataset, dan definisi skenario tertanamnya
masih schema 1. Nilai yang hilang tidak boleh ditebak dari default atau file
skenario schema 4 yang sekarang.

Konfigurasi Combo 2/430 km dan sensitivitas baru belum menghasilkan data live.
Artefak `research/vehicle_range_reference.json` mengunci sampel, sumber URL,
median, aturan pembulatan, dan keterbatasan pemilihan baseline tersebut.

Sumber asli, tanggal snapshot, metode pengumpulan, lisensi, dan hak redistribusi
dataset belum dikonfirmasi. Sebelum paper atau CSV dipublikasikan, pemilik
penelitian harus melengkapi bukti tersebut sebagaimana dijelaskan pada
[`data_provenance.md`](data_provenance.md).

## Gerbang penerimaan

Kandidat baru dapat disebut terverifikasi setelah:

1. audit offline berjalan terhadap manifest 0.17.0 tanpa mismatch;
2. test dan coverage lulus pada Python 3.11, 3.12, 3.13, dan 3.14;
3. job container 0.17.0 lulus dalam mode read-only dan tanpa jaringan;
4. artefak kualitas/container dari run yang sama berhasil diunduh dan diperiksa;
5. tidak ada secret atau laporan live mentah dalam commit;
6. data provenance/lisensi ditangani atau batas publikasinya dinyatakan jelas;
7. domain, HTTPS, Map ID, key restriction, email kontak, quota, dan volume
   persisten siap untuk deployment; dan
8. setiap test live mendapat izin terpisah serta laporan pemakaian aktual.

Sampai semua butir relevan terpenuhi, status yang tepat adalah **kandidat untuk
verifikasi**, bukan “siap produksi” atau “tervalidasi penuh”.
