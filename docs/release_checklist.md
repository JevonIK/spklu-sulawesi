# Checklist rilis penelitian

Checklist ini memisahkan verifikasi tanpa biaya dari tindakan live yang memakai
Google Maps API. Semua item otomatis harus lulus sebelum demo, deployment, atau
pengambilan data penelitian tambahan.

## Source code dan data

- [ ] Dataset yang digunakan adalah `dataset_spklu_sulawesi.csv` dengan 150
  baris sumber dan 149 node logis.
- [ ] SHA-256 dataset cocok dengan hash pada `docs/data_dictionary.md`.
- [ ] Tidak ada `.env`, API key, ledger, atau `reports/generated/` dalam commit.
- [ ] Versi pada health endpoint sama dengan versi aplikasi yang dilaporkan.
- [ ] Definisi baseline dan sensitivitas tervalidasi serta ID skenario unik.
- [ ] Dokumentasi tidak mengklaim adanya estimasi waktu pengisian.
- [ ] Konektor sistem tetap CCS2; tipe konektor lain hanya informasi dataset.

## Verifikasi otomatis tanpa API live

```bash
source .venv/bin/activate
python -m pip check
pytest -q --cov=app --cov-report=term-missing --cov-fail-under=90
python -m compileall -q app tests
node --check app/static/js/app.js
```

- [ ] Seluruh test lulus.
- [ ] Coverage total minimal 90%.
- [ ] CI GitHub hijau pada Python 3.11, 3.12, dan 3.13.
- [ ] Health endpoint, validasi input, security headers, dan error handling lulus.
- [ ] Referensi API dan panduan pengguna sesuai dengan versi kandidat rilis.

## Konfigurasi deployment

- [ ] `SECRET_KEY` produksi acak dan minimal 32 karakter.
- [ ] Browser key dan server key terpisah serta restriction sudah aktif.
- [ ] Map ID produksi bukan `DEMO_MAP_ID`.
- [ ] Domain HTTPS dan `TRUSTED_HOSTS` sudah benar.
- [ ] Egress IP server dimasukkan ke restriction server key jika tersedia.
- [ ] Folder ledger menggunakan volume persisten jika eksperimen dijalankan di
  container.
- [ ] Reverse proxy/gateway memiliki rate limit untuk endpoint rekomendasi.

## Sebelum tindakan live

- [ ] Pengguna memberi izin eksplisit untuk jenis test yang akan dilakukan.
- [ ] Pemakaian terkini diperiksa pada Google Cloud Console dan ledger lokal.
- [ ] Estimasi serta hard cap Compute Routes dan elemen Matrix dicatat.
- [ ] Estimasi Places Autocomplete, Get Place, dan map load dicatat untuk test UI.
- [ ] Request berurutan atau pacing telah dikonfigurasi.
- [ ] Tidak ada API yang dilarang pada `google_maps_api_limits.md`.
- [ ] Label laporan baru dan tidak menimpa artefak sebelumnya.

## Setelah tindakan live

- [ ] Jumlah attempt Compute Routes, request/elemen Matrix, Places, Get Place,
  dan map load dilaporkan.
- [ ] Error atau rerun manual dijelaskan dan dihitung secara kumulatif.
- [ ] `aggregate.error_count` nol sebelum hasil digunakan sebagai kesimpulan.
- [ ] Tidak ada pelanggaran SOC pada itinerary feasible.
- [ ] Hash SHA-256 artefak mentah dicatat.
- [ ] Laporan mentah tetap lokal dan hasil tervalidasi disalin ke dokumentasi.

## Artefak penelitian yang tersedia

- `docs/baseline_results.md`: hasil baseline enam wilayah;
- `docs/sensitivity_results.md`: analisis sensitivitas Makassar–Rantepao;
- `docs/google_maps_api_limits.md`: hard limit dan API terlarang;
- `docs/black_box_testing.md`: matriks pengujian fungsional; dan
- `docs/proposal_alignment.md`: keselarasan implementasi dengan proposal.
