# Kebijakan hard limit Google Maps API

Kebijakan ini berlaku untuk seluruh pengujian live proyek. Nilai di Google Cloud
Console tetap menjadi pengaman utama. Ledger aplikasi mencatat eksperimen CLI
dan endpoint rekomendasi yang memakai Routes API, tetapi tidak dapat mencatat
request browser.

## Batas aktif

Tabel berikut adalah konfigurasi kandidat 0.16.0. Ia tidak mengubah batas yang
tercatat pada eksperimen historis 0.9.2/0.10.0 dan tidak membuktikan bahwa
override Google Cloud sudah aktif; operator harus memeriksa Console sebelum
setiap tindakan live.

| Layanan | Batas harian | Batas per menit | Satuan |
|---|---:|---:|---|
| Compute Routes | 100 | 100 | request |
| Compute Route Matrix | 2.000 | 2.000 | elemen origin × destination |
| Places Autocomplete | 500 | 500 | request |
| Get Place | 200 | 200 | request |
| Map loads | 100 | 100 | load |

Batas per menit sengaja disamakan dengan batas harian. Dengan demikian, batas
harian tetap menjadi pengaman biaya utama dan tidak ada jeda buatan ketika
aplikasi hanya digunakan pada periode singkat. Konsekuensinya, kesalahan atau
penggunaan berlebihan dapat menghabiskan seluruh jatah hari itu dengan cepat,
meskipun tetap tidak dapat melewati hard cap harian.

Layanan berikut tidak boleh dipanggil oleh aplikasi atau pengujian:

- 3D Maps;
- Maps Grounding Widget;
- Places Photo;
- Nearby Search;
- Text Search; dan
- Review/Media Search.

Frontend saat ini hanya memuat peta 2D, Place Autocomplete, dan `fetchFields`
untuk tempat yang dipilih. Eksperimen CLI hanya memakai Compute Routes dan
Compute Route Matrix sehingga tidak menghasilkan pemakaian Places atau map
load.

## Prosedur wajib sebelum pengujian live

1. Catat tanggal quota Pacific Time dan pemakaian terkini di Google Cloud.
2. Hitung batas atas Compute Routes, elemen Matrix, Places, Get Place, dan map
   load yang mungkin dipakai oleh skenario.
3. Tetapkan hard cap di bawah sisa quota, bukan sama dengan quota penuh jika
   sudah ada pemakaian hari itu.
4. Jalankan request secara berurutan; jangan menjalankan proses live paralel.
5. Jangan melakukan retry otomatis tanpa batas. Setiap rerun manual harus
   mempunyai alasan, label baru, dan perhitungan kumulatif baru.
6. Setelah selesai, catat attempt, request/elemen aktual, error, sisa quota, dan
   hash laporan mentah.

Untuk eksperimen Routes, jalankan `quota-status` sebelum dan sesudah proses.
Ledger menaikkan counter tepat sebelum request dikirim agar timeout atau
kegagalan jaringan dihitung secara konservatif.

```bash
python -m flask --app run.py quota-status
```

Endpoint rekomendasi mereservasi maksimal 2 Compute Routes dan 625 elemen Matrix
sebelum menjalankan pipeline. Reservasi diganti dengan attempt aktual saat
selesai atau gagal. Request paralel ditolak HTTP 429 agar beberapa worker tidak
menghabiskan quota harian secara bersamaan. Ledger tetap menghitung rolling
window 60 detik, tetapi batas window sama dengan batas harian. Request berurutan
dapat langsung dilanjutkan selama reservasi berikutnya masih muat dalam sisa
quota harian dan menit aktif. Eksperimen CLI tidak lagi mewajibkan window bersih
atau jeda antarbatches, tetapi tetap ditolak jika hard cap yang diminta melebihi
sisa kapasitas.

Ledger schema v3 memigrasikan metadata batas menit lama (30/625) menjadi
100/2.000 pada pembacaan dan penulisan berikutnya tanpa menghapus riwayat
pemakaian harian.

## Mengubah quota di Google Cloud Console

Lakukan perubahan ini pada project Google Cloud yang dipakai aplikasi. Jangan
mengubah API key atau mengaktifkan API baru.

1. Buka [Google Maps Platform > Quotas](https://console.cloud.google.com/google/maps-apis/quotas).
2. Pastikan project yang dipilih adalah project SPKLU Sulawesi.
3. Pilih **Routes API**, lalu ubah:
   - Compute Routes per day menjadi `100`;
   - Compute Routes requests per minute menjadi `100`;
   - Compute Route Matrix elements per day menjadi `2000`; dan
   - Compute Route Matrix elements per minute menjadi `2000`.
4. Pilih quota Places/Autocomplete yang digunakan project, lalu ubah:
   - Places Autocomplete per day menjadi `500`;
   - Places Autocomplete per minute menjadi `500`;
   - Get Place/Place Details per day menjadi `200`; dan
   - Get Place/Place Details per minute menjadi `200`.
5. Pilih **Maps JavaScript API**, lalu ubah:
   - Map loads per day menjadi `100`; dan
   - Map loads per minute menjadi `100`.
6. Untuk setiap baris, centang quota, pilih **Edit**, isi nilai baru, pilih
   **Done**, lalu **Submit request**. Nama metric dapat sedikit berbeda menurut
   tampilan project; cocokkan layanan, satuan, dan periode waktunya.
7. Tunggu sampai nilai baru tampil pada kolom **Value**. Jika statusnya pending,
   jangan menganggap perubahan sudah aktif.
8. Filter **Has override: True** dan periksa kembali kesepuluh nilai di atas.
9. Jangan mengaktifkan 3D Maps, Maps Grounding Widget, Places Photo, Nearby
   Search, Text Search, atau Review/Media Search.

Google Cloud dapat meminta peran Quota Administrator atau persetujuan quota.
Panduan resminya tersedia pada [View and manage quotas](https://docs.cloud.google.com/docs/quotas/view-manage).

## Pengujian browser

Test otomatis Flask tidak memuat Google Maps dan tidak memakai quota eksternal.
Smoke test browser live dapat memakai satu map load, Place Autocomplete saat
mengetik, serta Get Place ketika origin/destination dipilih. Sebelum smoke test:

- buka hanya satu tab aplikasi;
- tetapkan batas interaksi, misalnya maksimal 10 request Autocomplete dan dua
  Get Place untuk satu alur origin–destination;
- jangan reload halaman berulang karena setiap reload dapat menambah map load;
- jangan membuka fitur atau contoh Google yang menggunakan API terlarang; dan
- periksa pemakaian aktual pada Google Cloud setelah test.

Ledger lokal tidak mencatat browser API. Jika aplikasi dipublikasikan, quota
Cloud, restriction API key, restriction referrer, serta rate limiting pada
gateway wajib aktif. Untuk demo atau pengambilan data terbatas, tambahkan
autentikasi atau allowlist pengguna/IP agar satu pihak tidak dapat menghabiskan
seluruh jatah harian secara berurutan.
