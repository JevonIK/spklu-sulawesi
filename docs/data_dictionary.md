# Kamus Data SPKLU Sulawesi

Dokumen ini menjelaskan dataset mentah dan transformasi yang dilakukan aplikasi.
CSV sumber tidak diubah oleh proses normalisasi agar asal-usul data tetap dapat
ditelusuri dan eksperimen dapat direproduksi.

Dataset yang dipakai pada baseline dan sensitivitas memiliki SHA-256:

```text
24992e1225209ed5a2833b8722be6bfabfc94cdc55f795acdf5edf10c21ffa85
```

Hash harus dihitung ulang dan perubahan dataset harus dijelaskan apabila baris,
koordinat, konektor, atau informasi unit diperbarui.

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

## Audit reproduktif

Jalankan perintah berikut dari root proyek setelah virtual environment aktif:

```bash
python -m flask --app run.py dataset-summary
```

Perintah tersebut memvalidasi dataset dan menampilkan jumlah baris sumber, node
logis, node multi-unit, distribusi provinsi, distribusi konektor, serta peringatan
konsolidasi dalam format JSON.
