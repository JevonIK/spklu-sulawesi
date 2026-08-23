# Ball Tree Radius Search dan Koridor Rute

Modul spasial menggunakan seluruh node lokasi hasil fase validasi data. Tidak ada
pemilihan berdasarkan nilai `K`; query radius mengembalikan semua node yang masih
berada di dalam ambang jarak yang ditentukan.

## Indeks spasial

1. Latitude dan longitude setiap node dikonversi dari derajat menjadi radian.
2. Koordinat dimuat ke `sklearn.neighbors.BallTree` dengan metrik `haversine`.
3. Radius kilometer dikonversi menjadi jarak sudut dengan membaginya terhadap
   radius rata-rata bumi `6371,0088 km`.
4. Jarak hasil query dikonversi kembali menjadi kilometer.

Filter konektor diterapkan setelah query radius. Label input dinormalisasi dengan
aturan yang sama seperti dataset sehingga variasi penulisan tidak mengubah hasil.
Jika kendaraan memiliki beberapa konektor, node dipertahankan ketika mendukung
sedikitnya satu dari konektor pilihan.

## Penghimpunan kandidat koridor

Polyline rute dasar berasal dari Compute Routes dengan kualitas `HIGH_QUALITY`,
lalu disampling dengan jarak antartitik maksimum yang dapat dikonfigurasi.
Ball Tree dipanggil pada setiap titik sampel, kemudian ID node dideduplikasi. Radius
penghimpunan diberi toleransi setengah jarak sampling agar kandidat dekat segmen
tidak terlewat.

Setelah penghimpunan, setiap node diproyeksikan ke segmen polyline terdekat untuk
menghitung:

- jarak geodesik terhadap koridor;
- progres kilometer dari awal rute;
- rasio progres terhadap total panjang polyline;
- segmen dan koordinat proyeksi terdekat.

Proyeksi segmen memakai bidang equirectangular lokal untuk menentukan posisi
terdekat, lalu jarak akhirnya dihitung kembali dengan Haversine. Pendekatan ini
digunakan sebagai filter geografis; jarak jalan tetap menjadi sumber keputusan
akhir pada fase validasi edge.

Hanya node dengan jarak terhadap rute tidak melebihi radius koridor yang dipakai.
Urutan hasil mengikuti progres perjalanan, bukan jarak lurus dari titik awal.

## Query berbasis usable range

Untuk origin atau node SPKLU tertentu, Ball Tree juga dapat mencari seluruh node
dalam `usable_range_km`. Kandidat kemudian harus memenuhi tiga syarat:

1. sedikitnya satu konektornya kompatibel;
2. lokasinya masih berada dalam batas koridor;
3. progresnya lebih besar daripada progres node saat ini.

Jarak pada tahap ini masih berupa jarak geodesik untuk pemangkasan awal. Jarak
jalan dan kelayakan edge akan divalidasi pada fase pembentukan graf.

Kualitas polyline yang lebih tinggi mengurangi kehilangan bentuk jalan pada
filter koridor, tetapi bukan bukti bahwa geometri, koordinat SPKLU, atau kondisi
jalan selalu akurat. Run baru merekam langkah sampling pada skenario schema 3;
laporan historis 0.9.2/0.10.0 tidak merekam nilai tersebut.
