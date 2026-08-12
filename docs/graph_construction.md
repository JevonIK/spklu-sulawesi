# Pembentukan Graf Perjalanan

Graf perjalanan merupakan directed acyclic graph dengan tiga jenis node:

- `origin`, selalu memiliki progres 0 km;
- `station`, berasal dari kandidat koridor yang kompatibel;
- `destination`, selalu memiliki progres sebesar panjang polyline utama.

Edge hanya dibentuk menuju node dengan progres lebih besar. Aturan ini mencegah
perjalanan kembali ke arah titik awal.

## Pemangkasan sebelum validasi jalan

Setiap pasangan node maju diperiksa menggunakan jarak Haversine. Pasangan langsung
dihapus jika jarak geodesiknya melebihi usable range sumber:

- edge dari origin memakai initial usable range;
- edge dari SPKLU memakai post-charge usable range maksimum.

Karena jarak jalan tidak mungkin secara material lebih pendek daripada jarak
geodesik, tahap ini aman digunakan untuk mengurangi pasangan yang perlu dikirim ke
provider jarak jalan. Provider menerima seluruh pasangan yang tersisa melalui
antarmuka batch agar implementasi Google Maps nantinya dapat mengatur batching dan
mencatat jumlah permintaan eksternal.

## Validasi edge

Provider mengembalikan jarak jalan dan, bila tersedia, durasi berkendara. Edge
diterima apabila:

1. provider berhasil menemukan rute;
2. jarak jalan tidak melebihi usable range sumber;
3. estimasi detour tidak melampaui batas opsional.

Estimasi detour edge sementara dihitung sebagai selisih nonnegatif antara jarak
jalan dan kenaikan progres pada polyline utama. Perhitungan ini akan memakai data
rute Google Maps pada fase integrasi.

## Statistik evaluasi

Setiap hasil pembangunan graf menyimpan jumlah kandidat, pasangan maju, pasangan
yang dipangkas secara geodesik, pasangan yang dikirim ke provider, hasil yang tidak
tersedia, edge yang gagal karena jarak jalan atau detour, edge yang diterima, dan
jumlah permintaan eksternal. Statistik ini disiapkan untuk evaluasi kebutuhan API
dan efisiensi komputasi.

