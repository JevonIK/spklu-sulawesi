# Pemodelan rute feri

## Tujuan dan cakupan

Sistem mendukung rute berkendara Google yang memuat satu atau beberapa
penyeberangan feri di seluruh Sulawesi. Implementasi tidak mengunci nama kota,
pelabuhan, atau lintasan tertentu. Kendari–Lambale hanya salah satu contoh;
statistik Kementerian Perhubungan juga mencatat simpul penyeberangan seperti
Torobulu, Tampo, Wawonii, Amolengo, Labuan, Kamaru, Wanci, Baubau, dan lainnya.

Sumber rujukan:

- [Referensi Compute Routes dan manuver FERRY](https://developers.google.com/maps/documentation/routes/reference/rest/v2/TopLevel/computeRoutes)
- [Keterbatasan Route Modifiers pada Compute Route Matrix](https://developers.google.com/maps/documentation/routes/route-modifiers)
- [Perhubungan Darat Dalam Angka 2024](https://hubdat.dephub.go.id/documents/1940/Perhubungan_Darat_Dalam_Angka_PDDA_Tahun_2024_nNEdzSR.pdf)

## Deteksi generik

Compute Routes diminta mengembalikan langkah, koordinat awal/akhir langkah,
jarak, durasi, travel mode, dan navigation maneuver. Langkah dengan maneuver
`FERRY` atau `FERRY_TRAIN` ditandai sebagai penyeberangan. Sistem kemudian
memproyeksikan terminal langkah tersebut terhadap progres polyline rute dasar.

Tidak ada pemanggilan Places Search, pencarian jadwal, atau API operator kapal.
Deteksi hanya menyatakan bahwa rute Google memuat feri; deteksi bukan bukti
operasional atau jaminan kendaraan dapat terangkut.

Pengguna dapat menonaktifkan **Izinkan feri kendaraan**. Dalam keadaan itu,
Compute Routes menerima `routeModifiers.avoidFerries=true`. Modifier Google
merupakan preferensi, bukan larangan absolut; apabila respons masih mempunyai
langkah feri, sistem menghentikan pipeline sebelum Matrix dan meminta pengguna
memilih tujuan darat lain atau mengaktifkan feri secara sadar.

## Model energi

Untuk setiap edge:

```text
jarak_energi = max(0, jarak_total - jarak_feri)
konsumsi_SOC = jarak_energi / jangkauan_efektif × 100%
```

Jarak dan durasi feri tetap disimpan sebagai bagian perjalanan. Konsumsi traksi
selama pelayaran ditetapkan nol karena kendaraan tidak bergerak dengan motornya
sendiri. Beban aksesori, AC, sentry mode, antrean di pelabuhan, idle sebelum
boarding, dan layanan tambahan di kapal berada di luar model energi rute.

## Integrasi dengan graph dan Matrix

Compute Route Matrix hanya mengembalikan total jarak/durasi per pasangan dan
tidak memberikan langkah feri. Untuk menjaga kuota, sistem tidak mengganti
setiap elemen Matrix dengan Compute Routes tambahan. Sebagai gantinya:

1. segmen feri diperoleh satu kali dari rute dasar;
2. setiap pasangan graph dibandingkan dengan interval progres feri;
3. pasangan yang beririsan tidak dipangkas memakai lower bound geodesik;
4. estimasi jarak feri dikurangi dari jarak Matrix hanya untuk constraint SOC;
5. jarak total tetap dipakai untuk informasi perjalanan dan detour; dan
6. Compute Routes final memisahkan ulang langkah aktual lalu mensimulasikan SOC
   setiap leg sebelum hasil ditampilkan.

Jika pembagian rute final membuat SOC melanggar minimum atau pemberhentian tidak
lagi benar-benar mengisi, mekanisme fail-safe yang ada menolak rekomendasi.

## Status akses

Semua itinerary yang memuat feri diberi status **kondisional**. Pengguna wajib
mengonfirmasi langsung kepada operator atau pelabuhan mengenai:

- apakah kapal mengangkut mobil;
- jadwal dan status operasional;
- kapasitas serta antrean kendaraan;
- pembatasan dimensi/berat kendaraan;
- tiket atau prosedur booking; dan
- cuaca serta penghentian layanan sementara.

Sistem tidak boleh menampilkan deteksi Google sebagai jaminan akses. Informasi
jadwal real-time berada di luar dataset SPKLU dan di luar ruang lingkup model.

## Keterbatasan penelitian

Penyesuaian edge Matrix memakai segmen feri rute dasar sebagai estimasi. Rute
Matrix antarpasangan dapat berbeda dari rute dasar. Karena itu hasil akhir selalu
divalidasi ulang menggunakan langkah Compute Routes final. Metode ini menjaga
kuota tetap maksimum dua Compute Routes per rekomendasi dan 625 elemen Matrix,
tetapi tidak membuktikan bahwa itinerary adalah optimum global pada semua
kombinasi lintasan feri.
