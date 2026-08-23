# Pembentukan Graf Perjalanan

Graf perjalanan merupakan directed acyclic graph dengan tiga jenis node:

- `origin`, selalu memiliki progres 0 km;
- `station`, berasal dari kandidat koridor yang kompatibel;
- `destination`, selalu memiliki progres sebesar panjang polyline utama.

Edge hanya dibentuk menuju node dengan progres lebih besar. Aturan ini mencegah
perjalanan kembali ke arah titik awal.

## Pemangkasan sebelum validasi jalan

Setiap pasangan node maju diperiksa menggunakan jarak Haversine. Untuk mengurangi
risiko membuang edge layak akibat perbedaan model bumi dan presisi koordinat,
sistem memakai lower bound dengan margin 1%:

```text
lower_bound = jarak_geodesik × (1 - 0,01)
```

Pasangan langsung dihapus hanya jika `lower_bound` tersebut melebihi usable
range sumber (ditambah toleransi numerik kecil):

- edge dari origin memakai initial usable range;
- edge dari SPKLU memakai post-charge usable range maksimum.

Jika pasangan melintasi segmen feri rute dasar, lower bound geodesik tidak
dipakai untuk pemangkasan energi karena jarak lurus di laut bukan jarak traksi
kendaraan. Pasangan tersebut tetap divalidasi oleh Route Matrix. Jarak energinya
kemudian dihitung dari jarak total Matrix dikurangi estimasi jarak feri yang
beririsan dengan progres edge.

Margin ini adalah toleransi prapemangkasan geometri, bukan safety factor energi.
Ia membuat filter sedikit lebih permisif agar pasangan dekat ambang tetap
divalidasi oleh Route Matrix. Provider menerima seluruh pasangan yang tersisa
melalui antarmuka batch untuk mengatur batching dan mencatat jumlah permintaan
eksternal.

## Validasi edge

Provider mengembalikan jarak jalan dan, bila tersedia, durasi berkendara. Edge
diterima apabila:

1. provider berhasil menemukan rute;
2. jarak energi setelah mengeluarkan segmen feri tidak melebihi usable range
   sumber;
3. metrik jalan dan detour dapat dibentuk secara konsisten.

Sebagai pemeriksaan integritas respons, jarak jalan yang lebih pendek daripada
lower bound geodesik di luar toleransi absolut ditolak sebagai data tidak masuk
akal. Keputusan kelayakan energi memakai jarak Matrix setelah bagian feri
dipisahkan, bukan jarak Haversine. Compute Routes final kemudian mengganti
estimasi itu dengan pembagian langkah aktual dan mensimulasikan SOC ulang
sebelum hasil ditampilkan.

Estimasi detour edge dihitung sebagai selisih nonnegatif antara jarak jalan dan
kenaikan progres pada polyline utama. Setelah itinerary terpilih, total detour
rute akhir dihitung kembali dari Compute Routes final terhadap rute dasar.
Pipeline kandidat tidak memakai hard cap per-edge. Sebaliknya, DP menjumlahkan
detour seluruh edge dan menerapkan hard cap total 20 km. Dengan demikian,
beberapa deviasi kecil tidak dapat secara kumulatif menghasilkan itinerary yang
melampaui batas perjalanan.

## Statistik evaluasi

Setiap hasil pembangunan graf menyimpan jumlah kandidat, pasangan maju, pasangan
yang dipangkas secara geodesik, pasangan yang dikirim ke provider, hasil yang tidak
tersedia, edge yang gagal karena jarak jalan atau detour, edge yang diterima, dan
jumlah permintaan eksternal. Jumlah pasangan yang mendapat penyesuaian feri dan
estimasi total jarak ferinya juga dicatat. Statistik ini disiapkan untuk evaluasi
kebutuhan API dan efisiensi komputasi.
