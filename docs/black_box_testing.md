# Black-box testing

Black-box testing memeriksa perilaku yang terlihat dari HTTP/UI tanpa
bergantung pada detail internal algoritma. Test otomatis memakai Flask test
client dan layanan rute deterministik; tidak ada request ke Google Maps API.

## Matriks kasus

| ID | Skenario | Hasil yang diharapkan | Otomatis |
|---|---|---|---|
| BB-01 | Halaman utama dibuka | HTTP 200, formulir, peta, dan empat pilihan konektor tampil | `test_app.py` |
| BB-02 | Health check | Dataset, indeks, optimizer, dan status key tersedia | `test_app.py` |
| BB-03 | Input valid, perlu satu SPKLU | HTTP 200, itinerary feasible, SOC aman | `test_black_box.py` |
| BB-04 | Input valid tetapi jangkauan tidak cukup | HTTP 200, `graph_disconnected`, tanpa itinerary | `test_black_box.py` |
| BB-05 | Body bukan JSON | HTTP 400 `invalid_json` | `test_recommendation_api.py` |
| BB-06 | Parameter tidak valid | HTTP 400 dan field penyebab | `test_recommendation_api.py` |
| BB-07 | Google menolak request | HTTP 502 dengan kode aman | `test_recommendation_api.py` |
| BB-08 | Key server belum tersedia | HTTP 503 `configuration_error` | `test_recommendation_api.py` |
| BB-09 | Body lebih dari 64 KiB | HTTP 413 `payload_too_large` | `test_security.py` |
| BB-10 | Endpoint API tidak ada | HTTP 404 JSON | `test_security.py` |
| BB-11 | Metode HTTP salah | HTTP 405 JSON | `test_security.py` |
| BB-12 | Exception tak terduga | HTTP 500 tanpa membocorkan detail internal | `test_security.py` |
| BB-13 | Host produksi tidak dipercaya | HTTP 400 | `test_security.py` |
| BB-14 | Halaman privasi dan ketentuan | HTTP 200 dan tertaut dari halaman utama | `test_security.py` |
| BB-15 | Header keamanan | CSP nonce, anti-frame, nosniff, referrer dan permissions policy | `test_security.py` |
| BB-16 | Setiap konektor dataset dipilih | Pipeline menerima AC Type 2, CCS2, CHAdeMO, dan GB/T | `test_black_box.py` |
| BB-17 | Opsi penelitian dikirim ke endpoint publik | SOC minimum/target dipakai; parameter lanjutan tetap memakai default backend | `test_recommendation.py` |
| BB-18 | Beberapa konektor kendaraan dipilih | Pipeline menerima daftar dan memakai SPKLU yang cocok dengan salah satu konektor | `test_black_box.py` |
| BB-19 | Hasil rute dirender | Overlay petunjuk disembunyikan sebelum bounds peta dihitung | `test_app.py` |
| BB-20 | Browser memakai mode gelap | Place Autocomplete tetap dipaksa ke skema warna terang yang terbaca | `test_app.py` |

## Smoke test browser

Setelah test otomatis lulus, jalankan aplikasi lokal dan periksa:

1. layout desktop dan mobile tidak mengalami overflow;
2. status sistem berubah dari `Memeriksa sistem` menjadi `Sistem siap`;
3. autocomplete origin/destination dapat dipilih;
4. input angka dan satu atau beberapa checkbox konektor dapat diubah;
5. loading state tampil ketika rekomendasi dikirim;
6. hasil feasible dan infeasible dapat dibaca tanpa membuka console;
7. link privasi/ketentuan berfungsi dan dapat kembali ke aplikasi;
8. tidak ada error CSP pada console browser;
9. overlay petunjuk awal hilang setelah rute ditampilkan; dan
10. daftar saran lokasi tetap terbaca pada mode tampilan terang maupun gelap.

Interaksi yang memerlukan Google Maps hanya dilakukan jika browser key aktif.
Pengujian rekomendasi live harus dicatat terpisah karena memakai quota Routes
API. Smoke test deployment tidak boleh berulang kali mengirim rekomendasi hanya
untuk menguji tampilan.

Sebelum smoke test live, hitung batas Places Autocomplete, Get Place, dan map
load sesuai [`google_maps_api_limits.md`](google_maps_api_limits.md). Buka satu
tab dan hindari reload berulang. Test otomatis tidak memakai layanan Google.

## Kriteria lulus

- Seluruh test otomatis lulus.
- Tidak ada itinerary feasible dengan SOC tiba di bawah SOC minimum.
- Error validasi, konfigurasi, upstream, dan internal memiliki status serta
  pesan yang dapat dipahami tanpa menampilkan API key atau exception internal.
- Header keamanan tidak menghalangi pemuatan Google Maps pada environment yang
  key dan domain restriction-nya benar.
- Pemeriksaan browser dicatat bersama tanggal, versi aplikasi, browser, ukuran
  viewport, dan apakah request live diizinkan.

## Catatan smoke test 13 Agustus 2026

| Item | Hasil |
|---|---|
| Versi | 0.9.0 |
| Server | Gunicorn 23.0.0, satu sync worker, port lokal 8765 |
| Browser/viewport | Chromium 151, 1280 × 766 |
| Health dan dataset | Lulus, 149 node logis |
| Layout utama | Lulus; kontrol, peta, footer, dan status sistem terbaca |
| Privasi/ketentuan | Lulus; navigasi dan konten terbaca |
| CSP | Script aplikasi dan library Maps dapat berjalan; formulir aktif |
| Rekomendasi live | Tidak dijalankan agar tidak memakai quota Routes API |
| Render peta | Terblokir oleh otorisasi browser key pada origin port 8765 |

Render peta perlu diuji ulang setelah origin lokal atau domain deployment
ditambahkan pada website restriction browser key. Hasil ini bukan kegagalan CSP:
library Maps berhasil mengaktifkan form, tetapi Google menampilkan error
otorisasi pada canvas. Port 5000 pada mesin pengembangan sedang digunakan proses
lain, sehingga smoke test memakai 8765 tanpa menghentikan proses tersebut.

### Verifikasi ulang 13 Agustus 2026

Setelah `http://127.0.0.1:8765/*` dan `http://localhost:8765/*` ditambahkan ke
website restriction browser key, smoke test versi 0.9.2 berhasil memuat peta,
kontrol kamera, data peta, attribution Google Maps, dan Places. Formulir aktif
dan tidak muncul lagi pesan error otorisasi pada canvas.
