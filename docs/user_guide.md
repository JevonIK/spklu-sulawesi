# Panduan pengguna

## Menyiapkan aplikasi lokal

1. Aktifkan virtual environment dan dependency.
2. Salin `.env.example` menjadi `.env`.
3. Isi browser key, server key, dan Map ID sesuai panduan deployment.
4. Jalankan `python run.py`.
5. Buka `http://127.0.0.1:5000`.

Status **Sistem siap digunakan** berarti dataset, browser Maps, dan endpoint rekomendasi
telah tersedia. Jika formulir tetap nonaktif, baca pesan status dan bagian
troubleshooting di bawah.

## Membuat rencana perjalanan

1. Pilih lokasi awal dari hasil Place Autocomplete.
2. Pilih lokasi tujuan yang berbeda.
3. Masukkan SOC saat ini dan jangkauan maksimum kendaraan dalam kilometer.
   Nilai awal 430 km adalah baseline penelitian, bukan nilai yang harus dipakai;
   ganti dengan nilai WLTP atau estimasi nyata kendaraan Anda.
4. Centang satu atau beberapa konektor yang benar-benar dapat digunakan
   kendaraan: AC Type 2, CCS2, CHAdeMO, atau GB/T. Angka pada pilihan
   menunjukkan jumlah lokasi pada dataset.
5. SPKLU publik selalu disertakan. Jika diperlukan, centang jaringan charger
   Hyundai, Wuling, atau Toyota/Lexus sebagai lokasi tambahan.
6. Biarkan **Izinkan feri kendaraan** aktif jika penyeberangan boleh digunakan,
   atau nonaktifkan untuk meminta Google menghindari feri sejauh memungkinkan.
   Jika feri tetap menjadi satu-satunya rute, sistem menolak hasil dan meminta
   pengguna mengaktifkannya secara sadar.
7. Tentukan SOC minimum sebagai cadangan baterai terendah dan target SOC sebagai
   batas SOC keberangkatan setelah berhenti di SPKLU.
8. Pastikan lokasi awal dan tujuan sudah dipilih dari daftar saran. Tombol
   **Cari rekomendasi SPKLU** baru aktif setelah keduanya tersimpan.
9. Pilih tombol tersebut satu kali dan tunggu hasil.
10. Gunakan **Reset perjalanan** untuk membersihkan lokasi, parameter, pilihan
   konektor/jaringan, hasil, marker, dan garis rute sebelum membuat rencana baru.

Jangan menekan tombol berulang selama loading. Setiap rekomendasi merupakan
pengujian live yang dapat memakai Compute Routes dan elemen Route Matrix.
Reset perjalanan tidak memanggil Google Routes API dan tidak memerlukan reload
halaman.

## Membaca hasil

Hasil **Rute aman ditemukan** menampilkan:

- jarak darat, jarak feri jika ada, dan waktu perjalanan;
- detour total final serta estimasi detour setiap leg;
- jumlah perhentian;
- SOC akhir;
- urutan leg dan SPKLU;
- SOC berangkat dan tiba pada setiap leg; serta
- statistik kandidat, graf, DP, dan pemakaian API.

Untuk setiap rute feasible, sistem menghitung ulang SOC dari setiap leg rute
Google yang ditampilkan. Hasil tidak ditampilkan sebagai aman bila jumlah leg tidak
sesuai atau SOC tiba melanggar batas minimum. Durasi memakai
`TRAFFIC_UNAWARE`, sehingga tidak memperhitungkan lalu lintas real-time atau
prediktif.

Badge **Rute publik** berarti seluruh pemberhentian pengisian yang dipilih
algoritma berasal dari SPKLU publik. Badge **Rute kondisional** berarti rute
mengandalkan sedikitnya satu charger dealer, fallback AC Type 2, atau feri.
Untuk charger dealer, pengguna wajib memastikan izin, jam operasional, dan
ketersediaan kepada pengelola.

Badge **AC Type 2 fallback** berarti kendaraan Combo 2 tidak memperoleh
itinerary CCS2 penuh dan sedikitnya satu stop memakai AC Type 2. Sistem
memprioritaskan CCS2 sebelum fallback ini. Pengguna perlu memeriksa daya,
kabel, dan kebutuhan berhenti di lokasi terpilih.

Aturan tersebut hanya aktif ketika pilihan konektor tepat CCS2 + AC Type 2.
Apabila pengguna memilih kombinasi lain, misalnya AC Type 2 + CHAdeMO, sistem
memperlakukan keduanya setara. SPKLU multi-konektor menampilkan seluruh pilihan
yang cocok sebagai **kompatibel**.

Badge **Feri kondisional** berarti Google mendeteksi sedikitnya satu
penyeberangan. Ringkasan memisahkan jarak darat dan jarak feri; SOC hanya
berkurang pada jarak darat. Pengguna tetap wajib memeriksa apakah kapal menerima
mobil, jadwal keberangkatan, cuaca, antrean, dan kapasitas aktual. Sistem tidak
menyediakan booking atau status kapal real-time.

Perubahan dari SOC tiba menuju SOC berangkat dimodelkan sebagai transisi state.

Hasil **Rute aman belum ditemukan** bukan selalu error aplikasi. Status ini
berarti graf tidak memiliki rangkaian leg yang memenuhi jangkauan, SOC minimum,
konektor, dan parameter backend saat itu. Pengguna dapat memeriksa kembali jenis
konektor atau jangkauan kendaraan, tetapi tidak boleh mengabaikan batas aman
kendaraan aktual.

## Makna pengaturan kendaraan

- **SOC saat ini** adalah persentase baterai sebelum perjalanan dimulai.
- **Jangkauan maksimum** adalah jarak nominal kendaraan saat baterai 100%.
- **SOC minimum** adalah batas tiba terendah yang diizinkan model.
- **Target SOC** adalah batas maksimum keberangkatan yang dievaluasi setelah
  berhenti di SPKLU; durasi perjalanan ditampilkan sebagai metrik terpisah.
- **Jenis konektor** dapat dipilih lebih dari satu. Sistem mempertimbangkan
  SPKLU yang mendukung sedikitnya satu konektor pilihan.
- **Jaringan charger tambahan** dapat dipilih lebih dari satu. Pilihan ini tidak
  menggantikan filter konektor dan tidak menjamin izin menggunakan charger
  dealer.

Sebagai contoh, memilih CCS2 dan jaringan Wuling tidak memasukkan charger
Wuling karena seluruh lokasi Wuling pada dataset memakai GB/T. SPKLU publik
CCS2 tetap dapat dipertimbangkan. Sistem tidak menambahkan GB/T secara otomatis.

Untuk kendaraan dengan inlet Combo 2, pilihan awal CCS2 + AC Type 2 mencerminkan
dukungan DC dan AC. Pada kombinasi ini, optimizer mendahulukan rute tanpa stop
AC-only; AC Type 2 baru dipakai sebagai fallback dan ditandai pada hasil.

Safety factor 0,9, radius koridor 10 km, interval SOC 5%, dan langkah sampling
5 km menjadi default backend. Batas total detour 20 km diturunkan dari dua kali
radius koridor. Nilai penelitian ini tidak ditampilkan pada formulir umum.
Peneliti tetap dapat mengubahnya melalui skenario eksperimen, bukan melalui
interaksi pengguna harian.
Dasar pemilihan dan batas interpretasinya tersedia di
[`parameter_rationale.md`](parameter_rationale.md).

## Troubleshooting

| Gejala | Pemeriksaan |
|---|---|
| Form tetap nonaktif | periksa browser key, server key, restriction referrer, Maps JavaScript API, Places API, dan Routes API |
| Tombol pencarian tetap nonaktif | pilih lokasi awal dan tujuan dari daftar saran Google; teks yang hanya diketik belum menyimpan koordinat |
| Tombol nonaktif setelah lokasi dipilih | pastikan sedikitnya satu checkbox konektor masih dicentang |
| Wuling tidak masuk ketika CCS2 dipilih | lokasi Wuling pada dataset memakai GB/T; pilih GB/T hanya jika kendaraan benar-benar kompatibel |
| Hasil menampilkan AC Type 2 fallback | tidak ada itinerary terpilih yang seluruh stop-nya memakai CCS2; konfirmasi daya, kabel, dan kebutuhan berhenti sebelum perjalanan |
| Saran lokasi gelap/tidak terbaca | muat ulang aset aplikasi terbaru; widget dipaksa memakai skema warna terang |
| Rute terlihat tetapi petunjuk awal masih menutupi peta | muat ulang aset JavaScript terbaru; overlay semestinya hilang saat rute tersedia |
| Peta menampilkan authorization error | tambahkan origin lengkap termasuk port ke website restriction |
| HTTP 503 | isi server key dan restart aplikasi |
| HTTP 400 | perbaiki field yang disebut pada respons validasi |
| HTTP 429 | tunggu request aktif selesai atau reset quota; jangan retry berulang |
| HTTP 502 | periksa jaringan, Routes API, billing, restriction server key, dan quota |
| Rute final ditolak karena SOC | jarak leg final berbeda dari matriks dan melanggar batas model; jangan memaksa hasil, periksa parameter kendaraan atau pilih rencana lain |
| Rute memakai feri | baca kartu penyeberangan dan konfirmasi layanan kendaraan langsung kepada operator atau pelabuhan |
| Rute tidak feasible | baca reason dan statistik graf; ini dapat menjadi hasil penelitian yang valid |
| Reason `detour_infeasible` | semua itinerary yang mencapai tujuan melampaui hard cap total detour 20 km pada model graf |
| Perhitungan lama | tunggu satu request selesai; kandidat/edge dan latensi Google memengaruhi waktu |

Sebelum mencoba ulang error live, periksa quota Cloud dan jangan melakukan retry
tanpa batas. Daftar hard limit berada pada `docs/google_maps_api_limits.md`.
