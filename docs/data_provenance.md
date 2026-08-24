# Provenance dan penggunaan dataset

Dataset SPKLU Sulawesi merupakan **researcher-compiled dataset** yang disusun
secara manual oleh Jevon Ivander Kangsudarmanto dari sumber operasional publik,
kemudian melalui verifikasi silang per lokasi. Provenance ini membedakan dataset
kompilasi penelitian dari sumber-sumber yang digunakan untuk menyusunnya.

## Identitas dataset

| Atribut | Nilai |
|---|---|
| Judul | Dataset SPKLU Sulawesi |
| Compiler | Jevon Ivander Kangsudarmanto |
| Tahun | 2026 |
| Berkas | `dataset_spklu_sulawesi.csv` |
| SHA-256 | `9c99d5e8e2cf8c595d81ccc184b211d1d6acb8d12bf4b3eb0b4df4d8eed41454` |
| Ukuran | 150 baris/unit; 146 node lokasi setelah konsolidasi |
| Cakupan | Enam provinsi Sulawesi |
| Pengumpulan awal | 27 Juli–11 Agustus 2026 |
| Verifikasi/revisi | 22–23 Agustus 2026 |
| Metode | Kompilasi manual per lokasi dan verifikasi silang multi-sumber |
| Status provenance | `documented_with_limitations` |

## Sumber dan perannya

### Peta SPKLU

[PetaSPKLU.id](https://petaspklu.id/) digunakan sebagai sumber utama daftar
lokasi, nama, alamat, koordinat, dan informasi geografis awal. Situs menampilkan
atribusi “powered by PLN” dan mengarahkan pengguna ke layanan PLN serta PLN
Mobile.

### PLN Mobile

[PLN Mobile](https://play.google.com/store/apps/details?id=com.icon.pln123),
yang dipublikasikan PT PLN (Persero), digunakan untuk memverifikasi jenis
konektor, keberadaan lokasi, serta lokasi tambahan yang belum tercakup pada
sumber web utama.

### Google Maps

[Google Maps](https://maps.google.com/) digunakan sebagai alat verifikasi
geografis sekunder untuk alamat, wilayah administratif, koordinat, dan tautan
keluar menuju pin lokasi. Dataset tidak menyimpan map tiles, Street View
imagery, foto, review, atau media Google.

## Prosedur kompilasi dan verifikasi

1. Lokasi dibaca dan dicatat secara manual dari Peta SPKLU; tidak digunakan
   scraping atau bulk export.
2. Setiap lokasi diperiksa silang melalui PLN Mobile dan Google Maps.
3. Wilayah administratif, alamat, atau koordinat yang tidak konsisten diperiksa
   ulang sebelum direvisi.
4. Konektor diverifikasi melalui PLN Mobile dan ejaannya diseragamkan ke label
   kanonis aplikasi.
5. Lokasi tambahan dimasukkan ketika ditemukan pada PLN Mobile tetapi belum
   tercakup pada Peta SPKLU.
6. Beberapa unit pada tempat fisik yang sama tetap dipertahankan sebagai baris
   terpisah, tetapi koordinatnya diselaraskan agar menjadi satu node algoritma.
7. Seluruh tautan diperiksa agar membuka pin Google Maps dan bukan tampilan
   Street View.

## Quality assurance yang dapat diaudit

- Dataset hanya menerima enam provinsi yang ditetapkan dalam ruang lingkup.
- Koordinat harus finite dan berada dalam bounding box konservatif Sulawesi.
- Nama, wilayah, alamat, dan konektor wajib terisi.
- Konektor harus dapat dinormalisasi menjadi AC Type 2, CCS2, CHAdeMO, atau
  GB/T.
- Seluruh 150 tautan menggunakan HTTPS dan host `maps.app.goo.gl`.
- Tidak ada satu tautan yang dipakai oleh koordinat berbeda.
- Empat lokasi multi-unit mempertahankan dua unit sumber dan menjadi empat node
  terkonsolidasi.
- SHA-256 mengunci byte dataset yang dipakai aplikasi dan eksperimen 0.18.0.

Quality assurance tersebut membuktikan konsistensi dan reproduksibilitas versi
data, sedangkan perubahan kondisi operasional setelah tanggal snapshot berada
di luar cakupan dataset.

## Status penggunaan dan atribusi

Sumber yang digunakan dapat diakses publik. Peta SPKLU menampilkan copyright,
tetapi pada pemeriksaan 24 Agustus 2026 tidak ditemukan pernyataan lisensi
open-data eksplisit. Karena itu dataset dideskripsikan sebagai kompilasi
penelitian yang diatribusikan, bukan sebagai salinan resmi atau open dataset
berlisensi milik PLN.

Google Maps digunakan untuk verifikasi manual dan outbound pin. Penggunaan ini
tetap tunduk pada
[Google Maps End User Additional Terms](https://www.google.com/help/terms_maps/),
yang antara lain mengatur atribusi serta pembatasan penyalinan dan bulk feed.
Dataset tidak dimaksudkan sebagai pengganti layanan pemetaan Google.

Penggunaan yang dinyatakan proyek:

- analisis akademik non-komersial dan reproduksi hasil penelitian;
- sitasi jelas kepada compiler, Peta SPKLU/PLN, PLN Mobile, dan Google Maps
  sebagai sumber verifikasi;
- publikasi metrik, metode, agregat, dan hasil penelitian; serta
- tidak mengklaim afiliasi, endorsement, status data resmi PLN, atau lisensi
  open-data yang tidak dinyatakan sumber.

Jika penerbit meminta raw CSV sebagai supplementary data yang dapat
didistribusikan ulang secara independen, konfirmasi tertulis dari pemilik sumber
tetap merupakan langkah yang direkomendasikan.

## Sitasi yang disarankan

```text
Kangsudarmanto, J. I. (2026). Dataset SPKLU Sulawesi
[Research dataset compiled from Peta SPKLU and verified with PLN Mobile
and Google Maps].
```

Dalam Methods/Data section, tambahkan:

> The Sulawesi EV charging-station dataset was manually compiled by the
> researcher from the publicly accessible Peta SPKLU directory and
> cross-validated location by location using PLN Mobile and Google Maps during
> July–August 2026. Administrative areas, coordinates, connector labels, and
> co-located units were reviewed and normalized before computational use.

Usulan **Data Availability Statement**:

> The versioned research dataset, its SHA-256 checksum, provenance metadata,
> column lineage, and transformation record are documented in the project
> repository. The dataset is a researcher-compiled and attributed research
> artifact derived from publicly accessible operational directories; it is not
> represented as an official or openly licensed PLN dataset. Redistribution of
> source-derived records remains subject to the respective providers' terms,
> and source-owner confirmation will be obtained if required by the journal's
> supplementary-data policy.

## Keterbatasan yang relevan

- Snapshot tidak memuat status operasional real-time, daya charger, tarif,
  antrean, atau jam operasional.
- Verifikasi menggunakan sumber digital dan tidak mencakup inspeksi lapangan
  atau konfirmasi langsung kepada setiap operator.
- Charger dealer teridentifikasi pada sumber, tetapi izin penggunaan oleh merek
  kendaraan lain tetap kondisional.
- Cakupan ditujukan pada seluruh lokasi yang dapat diidentifikasi dari sumber
  yang dikonsultasikan, bukan jaminan sensus resmi atau pembaruan setelah
  23 Agustus 2026.

Keterbatasan tersebut menjelaskan scope temporal dan operasional tanpa
mengurangi bukti bahwa dataset dikompilasi secara sistematis dan diverifikasi
lintas sumber.

## Rantai artefak penelitian

1. `dataset_metadata.json` menyimpan source register, column lineage,
   transformasi, quality assurance, dan status penggunaan.
2. `release_manifest.json` mengunci checksum metadata dan dataset.
3. `research_manifest.json` menghubungkan dataset dengan notebook, snapshot,
   skenario, dan source run.
4. `notebooks/data/provenance.json` mempertahankan checksum sumber dan snapshot
   analisis offline.

Baseline 0.9.2 dan sensitivitas 0.10.0 dibuat sebelum laporan merekam hash
dataset. Eksperimen detour 0.18.0 merekam dataset kandidat 150 baris/146 node,
SHA-256, langkah sampling, source tree, dan definisi sembilan skenario secara
lengkap.
