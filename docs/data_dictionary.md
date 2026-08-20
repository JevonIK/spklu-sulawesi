# Kamus Data SPKLU Sulawesi

Dokumen ini menjelaskan dataset yang diterima proyek dan transformasi yang
dilakukan aplikasi. CSV tidak diubah oleh proses normalisasi sehingga identitas
byte dan transformasi komputasinya dapat diaudit. Hal itu tidak sama dengan
provenance sumber yang lengkap: penyedia asli, tanggal snapshot, metode
pengumpulan, lisensi, dan hak redistribusi saat ini belum diketahui.

Dataset yang berada pada kandidat 0.15.0 dan dipakai analisis notebook offline
memiliki SHA-256:

```text
24992e1225209ed5a2833b8722be6bfabfc94cdc55f795acdf5edf10c21ffa85
```

Hash harus dihitung ulang dan perubahan dataset harus dijelaskan apabila baris,
koordinat, konektor, atau informasi unit diperbarui.

Laporan live historis baseline 0.9.2 dan sensitivitas 0.10.0 mencatat ukuran data,
tetapi belum merekam SHA-256 dataset. Karena itu, kesamaan byte dataset historis
dengan file kandidat sekarang tidak dapat dibuktikan dari laporan tersebut dan
tidak boleh dinyatakan hanya berdasarkan kecocokan jumlah baris/node.

## Status provenance

`dataset_metadata.json` mencatat dataset sebagai `user_supplied`, dengan
`provenance_status: incomplete`, `license_status: unknown`, dan hak redistribusi
yang belum dikonfirmasi. Nilai kosong tidak boleh diisi dengan dugaan. Sebelum
publikasi atau redistribusi, pemilik penelitian harus memberikan sumber primer,
tanggal snapshot, metode pengumpulan, lisensi/izin, dan format sitasi. Checklist
dan batas klaim tersedia pada [`data_provenance.md`](data_provenance.md).

Hash di atas membuktikan versi file yang dipakai komputasi, bukan bahwa dataset
resmi, lengkap, terkini, atau berlisensi terbuka.

## Kolom sumber

| Kolom | Tipe | Aturan validasi | Penggunaan |
|---|---|---|---|
| `Provinsi` | Teks | Salah satu dari enam provinsi di Sulawesi | Pengelompokan wilayah |
| `Kota/Kabupaten` | Teks | Wajib, tidak kosong | Informasi administratif |
| `Lokasi SPKLU` | Teks | Wajib, tidak kosong | Nama unit/lokasi |
| `Alamat` | Teks | Wajib, tidak kosong | Informasi lokasi |
| `Latitude` | Desimal | -7 sampai 3 | Indeks spasial |
| `Longitude` | Desimal | 118 sampai 126,5 | Indeks spasial |
| `google maps` | URL | URL HTTPS dari Google Maps | Tautan lokasi |
| `Jenis Konektor` | Daftar teks | Harus dikenal sistem | Filter kompatibilitas |

## Normalisasi konektor

Label kanonis yang digunakan sistem adalah:

- `AC TYPE 2`
- `CCS2`
- `CHADEMO`
- `GB/T`

Variasi kapitalisasi, spasi, garis miring, dan tanda hubung dinormalisasi hanya
di memori. Beberapa konektor dalam satu unit dipisahkan dengan koma, titik koma,
atau karakter `|`, kemudian dideduplikasi dan diurutkan secara konsisten.

## Unit dan node lokasi

Satu baris CSV diperlakukan sebagai satu `StationUnit`. Unit dengan koordinat
yang sama sampai enam angka desimal dikonsolidasikan menjadi satu `StationNode`
untuk kebutuhan algoritma rute. Seluruh nama unit, konektor, alamat, tautan, dan
nomor baris sumber tetap tersedia di dalam node tersebut.

Dengan cara ini, dua unit `SPKLU PLN KANTOR ULP BOLMUT 1` dan `SPKLU PLN KANTOR
ULP BOLMUT 2` tetap tercatat sebagai dua unit, tetapi hanya menjadi satu titik
tujuan pada graf perjalanan.

## Metadata jaringan dan akses

CSV sumber tidak mempunyai kolom kebijakan akses. Aplikasi menurunkan metadata
jaringan di memori dari penanda eksplisit pada `Lokasi SPKLU`:

- nama yang memuat `HYUNDAI` diklasifikasikan sebagai `HYUNDAI`;
- nama yang memuat `WULING` diklasifikasikan sebagai `WULING`;
- nama yang memuat `TOYOTA` diklasifikasikan sebagai `TOYOTA`; dan
- nama lainnya diklasifikasikan sebagai `PUBLIC`.

Klasifikasi ini membedakan jaringan untuk kebutuhan sistem; klasifikasi bukan
jaminan hukum atau operasional bahwa charger dapat digunakan. Bluecharge Wisma
Kalla, misalnya, tetap diklasifikasikan sebagai `PUBLIC` karena nama lokasinya
tidak menyatakan fasilitas dealer Toyota.

Kecocokan diperiksa pada tingkat unit dengan aturan berikut:

```text
unit layak = konektor unit cocok
             DAN
             (jaringan PUBLIC ATAU jaringan dealer dipilih pengguna)
```

Pemeriksaan per unit mencegah penggabungan yang keliru pada node multi-unit,
misalnya konektor dari unit publik dianggap tersedia melalui unit dealer yang
berbeda.

## Audit reproduktif

Jalankan perintah berikut dari root proyek setelah virtual environment aktif:

```bash
python -m flask --app run.py dataset-summary
```

Perintah tersebut memvalidasi dataset dan menampilkan jumlah baris sumber, node
logis, node multi-unit, distribusi provinsi, distribusi konektor, serta peringatan
konsolidasi dalam format JSON.
