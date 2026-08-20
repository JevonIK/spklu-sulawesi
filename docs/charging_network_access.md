# Kebijakan Jaringan Charger Dealer

Dokumen ini menjelaskan pemisahan antara kompatibilitas konektor dan akses
jaringan pada Sistem Rekomendasi SPKLU Sulawesi. Dataset mentah tidak diubah;
klasifikasi jaringan diturunkan di memori agar transformasi komputasinya dapat
direproduksi. Hal ini tidak membuktikan provenance atau lisensi dataset; status
tersebut dijelaskan pada [`data_provenance.md`](data_provenance.md).

## Dasar keputusan

Konektor yang cocok tidak otomatis memberi izin menggunakan charger. Sistem
karena itu memakai dua filter yang terpisah:

1. konektor kendaraan sebagai syarat teknis; dan
2. jaringan charger sebagai pilihan akses pengguna.

SPKLU publik selalu disertakan. Jaringan Hyundai, Wuling, dan Toyota/Lexus
hanya dimasukkan ketika dicentang. Pilihan tersebut merupakan persetujuan
pengguna untuk mempertimbangkan fasilitas dealer, bukan jaminan akses dari
pengelola.

## Ringkasan dataset

| Jaringan | Node lokasi | Konektor pada dataset | Perlakuan default |
|---|---:|---|---|
| SPKLU publik | 117 | AC Type 2, CCS2, CHAdeMO | Selalu disertakan |
| Hyundai | 8 | AC Type 2 | Opsional dan kondisional |
| Wuling | 17 | GB/T | Opsional dan kondisional |
| Toyota/Lexus | 7 | AC Type 2 | Opsional dan kondisional |

Jumlah node berbeda dari jumlah baris karena dua unit SPKLU PLN ULP Bolmut
dikonsolidasikan menjadi satu node lokasi.

## Bukti kebijakan merek

- Hyundai menyatakan jaringan EV Charging dalam aplikasi myHyundai tersedia
  bagi EV Hyundai dan merek lain. Kebijakan dan operasional tetap dapat berbeda
  per lokasi: <https://www.hyundai.com/id/id/myhyundaicare/kepemilikan/ev-charging>.
- Wuling menjelaskan beberapa fasilitas pengisian sebagai fasilitas khusus
  pengguna Wuling. Tidak ditemukan izin lintas merek yang berlaku umum untuk
  dealer Kumala Sulawesi:
  <https://wuling.id/id/blog/press-release/wuling-hadirkan-layanan-purna-jual-bertajuk-comfortable-in-confidence-untuk-cloud-ev>.
- Toyota menjelaskan charging spot dealer sebagai fasilitas bagi kendaraan
  elektrifikasi Toyota dan Lexus:
  <https://pressroom.toyota.astra.co.id/toyota-bangun-ekosistem-menyeluruh-guna-dukung-mobilitas-kendaraan-elektrifikasi-dan-meningkatkan>.
- Regulasi ESDM membedakan SPKLU umum dari instalasi listrik privat:
  <https://jdih.esdm.go.id/dokumen/download?id=Permen+ESDM+Nomor+1+Tahun+2023.pdf>.

Sumber tersebut digunakan untuk memilih pendekatan konservatif, bukan untuk
menyatakan kebijakan permanen setiap dealer. Kebijakan lokasi dapat berubah dan
perlu dikonfirmasi kembali sebelum perjalanan.

## Aturan algoritma

Sebuah unit charger menjadi kandidat jika konektornya cocok dan jaringannya
publik atau dipilih pengguna. Node lokasi menjadi kandidat jika sedikitnya satu
unit di dalamnya memenuhi kedua syarat tersebut.

Contoh: jika CCS2 dan Wuling dipilih, 17 lokasi Wuling tetap dikeluarkan karena
seluruhnya memakai GB/T. SPKLU publik CCS2 tetap dipertimbangkan. Sistem tidak
menambahkan GB/T secara otomatis.

Rute diberi status `conditional` hanya apabila itinerary yang akhirnya dipilih
benar-benar menggunakan charger dealer. Mencentang jaringan dealer tanpa
memakainya tidak mengubah rute publik menjadi kondisional.

## Interpretasi hasil

- **Rute publik**: seluruh pemberhentian pengisian yang dipilih menggunakan unit
  publik yang kompatibel.
- **Rute kondisional**: sedikitnya satu pemberhentian menggunakan unit jaringan
  dealer. Pengguna wajib memeriksa izin, jam operasional, dan ketersediaannya.

Status tersebut tidak menggantikan pemeriksaan kondisi nyata, antrean, gangguan
charger, ataupun batas keselamatan kendaraan.
