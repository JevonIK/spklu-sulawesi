# Antarmuka Pengguna Google Maps

## Komponen

Antarmuka fase 6B terdiri dari:

- Place Autocomplete untuk lokasi awal dan tujuan;
- peta Google dengan overview polyline rute;
- marker lokasi awal, tujuan, dan SPKLU terpilih;
- formulir parameter kendaraan dengan checkbox AC Type 2, CCS2, CHAdeMO, dan
  GB/T yang dapat dipilih lebih dari satu;
- ringkasan jarak, durasi berkendara, jumlah pemberhentian, dan SOC akhir;
- itinerary per leg dengan SOC berangkat dan tiba; serta
- statistik kandidat, graf, state DP, dan penggunaan API.

Antarmuka tidak menampilkan estimasi waktu pengisian karena fitur tersebut berada
di luar ruang lingkup penelitian.

## Alur interaksi

1. Halaman memeriksa health endpoint dan memuat Maps JavaScript API.
2. Form tetap dinonaktifkan sampai health endpoint, endpoint rekomendasi, serta
   library `maps`, `places`, dan `marker` siap.
3. Pengguna wajib memilih hasil dari Place Autocomplete agar koordinat valid.
4. Tombol rekomendasi tetap nonaktif sampai origin, destination, dan sedikitnya
   satu konektor tersimpan.
5. Autocomplete dibatasi ke Indonesia dan ke bounding box wilayah Sulawesi.
6. Input pengguna dikirim sebagai JSON ke `POST /api/recommendations`, sedangkan
   safety factor, radius koridor, interval SOC, dan sampling berasal dari backend.
7. Selama perhitungan, tombol dan peta menampilkan status loading.
8. Rute feasible ditampilkan dengan marker SPKLU dan rincian SOC; petunjuk awal
   di tengah peta disembunyikan segera setelah data rute tersedia.
9. Jika tidak feasible, rute dasar tetap divisualisasikan dan alasan kegagalan
   ditampilkan tanpa membuat hasil seolah-olah berhasil.

## Keamanan key

Browser key memang dikirim ke browser karena dibutuhkan oleh Maps JavaScript API.
Key ini harus dibatasi menggunakan HTTP referrer dan hanya diberi akses ke Maps
JavaScript API serta Places API (New). Server key tidak pernah dirender ke HTML,
JavaScript, atau respons browser.

## Map ID

Nilai `DEMO_MAP_ID` digunakan untuk pengujian lokal Advanced Marker. Saat
deployment, buat JavaScript Map ID pada Google Cloud Console dan isi:

```dotenv
GOOGLE_MAPS_MAP_ID=map-id-produksi
```

Map ID bukan rahasia, tetapi map ID produksi memudahkan pengelolaan styling dan
konfigurasi peta sendiri.

## Tampilan responsif

Pada layar desktop, panel parameter dapat digulir sementara peta tetap memenuhi
area kanan. Pada tablet dan ponsel, panel parameter dan peta disusun vertikal.
Animasi juga dipangkas ketika sistem operasi mengaktifkan preferensi reduced
motion.

Place Autocomplete dipaksa memakai skema warna terang karena antarmuka aplikasi
memakai panel terang. Dengan demikian, teks prediksi tetap memiliki kontras yang
terbaca walaupun browser atau sistem operasi menggunakan mode gelap.
