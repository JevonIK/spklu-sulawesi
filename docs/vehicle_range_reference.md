# Dasar ilmiah jangkauan kendaraan referensi

Nilai awal `maximum_range_km=430` pada kandidat 0.16.0 bukan spesifikasi untuk
semua kendaraan. Nilai tersebut adalah baseline terkontrol untuk eksperimen dan
placeholder yang wajib diganti pengguna sesuai kendaraannya.

## Protokol pemilihan

Artefak mesin `research/vehicle_range_reference.json` menerapkan kriteria:

- BEV penumpang dipasarkan resmi di Indonesia;
- kompatibel dengan ekosistem AC Type 2/CCS2;
- mempunyai angka WLTP dari sumber resmi pabrikan yang dapat diaudit;
- satu observasi per model-family agar jumlah trim tidak langsung menjadi bobot;
- NEDC, CLTC, EPA, angka preliminary, PHEV, dan kendaraan komersial tidak
  digabungkan ke estimasi utama; dan
- sampel tidak dibobot penjualan karena data registrasi/model khusus Sulawesi
  yang dapat diverifikasi tidak tersedia dalam proyek.

## Sampel dan transformasi

| Model-family | Angka WLTP sumber | Aturan representatif | Nilai model |
|---|---:|---|---:|
| Hyundai IONIQ 5 | 384, 481, 384, 451 km | median empat varian | 417,5 km |
| Hyundai IONIQ 6 | 519 km | nilai tunggal | 519 km |
| Chery OMODA E5 | 430 km | nilai tunggal | 430 km |
| Kia EV9 | 497 km | nilai tunggal | 497 km |
| BMW iX1 eDrive20 | 417–439 km | midpoint rentang | 428 km |
| Mercedes-Benz EQB 250+ | 535 km | nilai tunggal | 535 km |
| MINI All-Electric Countryman | 433 km | nilai tunggal | 433 km |

Median tujuh nilai model adalah **433 km**. Aturan yang ditetapkan pada artefak,
`nearest_10_km_half_up`, menghasilkan:

```text
median 433 km → baseline 430 km
```

Validator `app/services/vehicle_reference.py` menghitung ulang nilai per model,
median, pembulatan, dan kesesuaian dengan konstanta aplikasi. Release audit akan
gagal bila salah satu angka diubah tanpa menjaga rantai perhitungannya.

## Sumber primer

- Hyundai IONIQ 5:
  <https://www.hyundai.com/content/dam/hyundai/id/id/images/local/hyundai-indonesia/brochure/ioniq-5/agustus-2024/Hyundai_IONIQ_5_Brochure.pdf>
- Hyundai IONIQ 6:
  <https://www.hyundai.com/content/dam/hyundai/id/id/images/local/hyundai-indonesia/brochure/ioniq-6/agustus-2024/Hyundai_IONIQ_6_Brochure.pdf>
- Chery OMODA E5:
  <https://chery.co.id/id/model/omoda/tipe/omoda-e5>
- Kia EV9:
  <https://www.kia.com/id/id/showroom/ev9/features.html>
- BMW iX1:
  <https://www.bmw.co.id/en/all-models/bmw-i/ix1/bmw-ix1.html>
- Mercedes-Benz EQB:
  <https://mercedes-benz.co.id/en/vehicles/eqb/>
- MINI Countryman:
  <https://www.mini.co.id/en_ID/home/range/all-electric-mini-countryman.html>

Tanggal akses sumber pada snapshot penelitian adalah 23 Agustus 2026. URL dan
nilai mentah yang dipakai perhitungan tersimpan di artefak JSON, bukan hanya di
dokumen naratif ini.

## Sensitivitas dan batas interpretasi

Skenario kandidat menguji 200, 300, 400, dan 500 km terhadap baseline 430 km.
Dengan SOC awal 80%, SOC minimum 20%, dan safety factor 0,9, usable range-nya:

| Maximum range | Usable range 80→20% |
|---:|---:|
| 200 km | 108 km |
| 300 km | 162 km |
| 400 km | 216 km |
| 430 km | 232,2 km |
| 500 km | 270 km |

Definisi skenario bukan hasil eksperimen. Angka feasibility, stop, edge, atau
SOC baru boleh dilaporkan setelah run live mendapat izin, melewati preflight
quota, dan disimpan sebagai laporan baru. Hasil historis 0.9.2/0.10.0 tetap
menggunakan 300 km dan CCS2-only.
