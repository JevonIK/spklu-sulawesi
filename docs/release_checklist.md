# Checklist rilis penelitian

Checklist ini memisahkan verifikasi tanpa biaya dari tindakan live yang memakai
Google Maps API. Semua item otomatis harus lulus sebelum demo, deployment, atau
pengambilan data penelitian tambahan.

## Source code dan data

- [ ] Dataset yang digunakan adalah `dataset_spklu_sulawesi.csv` dengan 150
  baris sumber dan 149 node logis.
- [ ] SHA-256 dataset cocok dengan hash pada `docs/data_dictionary.md`.
- [ ] `dataset_metadata.json` cocok dengan hash manifest dan masih jujur menandai
  provenance `incomplete` serta lisensi `unknown` bila bukti belum tersedia.
- [ ] Penyedia asli, tanggal snapshot, metode pengumpulan, lisensi, hak
  redistribusi, dan sitasi telah dikonfirmasi sebelum dataset dipublikasikan;
  jika belum, batas publikasi dinyatakan eksplisit.
- [ ] Tidak ada `.env`, API key, ledger, atau `reports/generated/` dalam commit.
- [ ] Berkas `.env` lokal memiliki permission `600`; secret produksi disimpan di
  secret manager platform, bukan di filesystem image.
- [ ] Versi pada health endpoint sama dengan versi aplikasi yang dilaporkan.
- [ ] Definisi baseline dan sensitivitas memakai schema 2, checksum cocok,
  tervalidasi, dan ID skenario unik.
- [ ] Laporan baru memakai schema 3 dan memuat provenance yang diwajibkan.
- [ ] Hasil historis diatribusikan ke aplikasi penghasilnya: baseline 0.9.2 dan
  sensitivitas 0.10.0, bukan kandidat analisis 0.15.0.
- [ ] Hash `constraints.txt` cocok dengan manifest kandidat rilis.
- [ ] Dokumentasi tidak mengklaim adanya estimasi waktu pengisian.
- [ ] Aplikasi menerima AC Type 2, CCS2, CHAdeMO, dan GB/T; skenario penelitian
  tetap memakai CCS2.

## Verifikasi otomatis tanpa API live

```bash
source .venv/bin/activate
python -m pip check
pytest -q --cov=app --cov-report=term-missing --cov-fail-under=90
python -m compileall -q app scripts tests
node --check app/static/js/app.js
python -m flask --app run.py release-audit
```

- [ ] Seluruh test lulus.
- [ ] Coverage total minimal 90%.
- [ ] CI GitHub hijau pada Python 3.11, 3.12, dan 3.13.
- [ ] Job CI `Container smoke test` hijau tanpa jaringan eksternal.
- [ ] Artefak `quality-python-*` dan `container-smoke-evidence` dari revision
  kandidat yang sama berhasil diunduh serta diperiksa.
- [ ] Health endpoint, validasi input, security headers, dan error handling lulus.
- [ ] Payload rute mengunci `HIGH_QUALITY` dan `TRAFFIC_UNAWARE`.
- [ ] Margin lower bound geodesik 1% dan kasus jarak jalan implausibel teruji.
- [ ] Mismatch leg final dan pelanggaran SOC pada leg Compute Routes final
  ditolak; rute tersebut tidak dilaporkan feasible.
- [ ] Referensi API dan panduan pengguna sesuai dengan versi kandidat rilis.

Command `release-audit` mencakup identitas versi/source, metadata dan dataset,
dependency, konektor, ketiadaan waktu pengisian, parameter rute/graf, definisi
skenario, manifest penelitian, snapshot terpantau, provenance run historis, dan
hard limit. Item yang bergantung pada GitHub, arsip eksternal, deployment,
Google Cloud, atau bukti hukum tetap diperiksa manual. Lihat
[`release_audit.md`](release_audit.md) untuk batas pemeriksaannya.

## Konfigurasi deployment

- [ ] `SECRET_KEY` produksi acak dan minimal 32 karakter.
- [ ] Browser key dan server key terpisah serta restriction sudah aktif.
- [ ] Map ID produksi bukan `DEMO_MAP_ID`.
- [ ] Domain HTTPS dan `TRUSTED_HOSTS` sudah benar.
- [ ] Egress IP server dimasukkan ke restriction server key jika tersedia.
- [ ] Folder ledger menggunakan volume persisten jika eksperimen dijalankan di
  container.
- [ ] Root filesystem container dijalankan read-only; `/tmp` dan direktori
  ledger/laporan disediakan sebagai tmpfs atau volume tulis yang terbatas.
- [ ] Proses container bukan root, source `/app/app` tidak dapat ditulis user
  runtime, dan hanya target persisten yang memiliki ownership/permission tulis.
- [ ] Reverse proxy/gateway memiliki rate limit untuk endpoint rekomendasi; demo
  terbatas juga memakai autentikasi atau allowlist pengguna/IP.
- [ ] Ledger persisten mencatat eksperimen CLI dan rekomendasi web pada satu
  instance aplikasi.
- [ ] Hard cap web tetap 2 Compute Routes dan 625 elemen Matrix per request.

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
- [ ] Untuk setiap hasil feasible schema 3, validasi rute final berstatus
  `passed`.
- [ ] Hash SHA-256 artefak mentah dicatat.
- [ ] Laporan mentah tetap lokal dan hasil tervalidasi disalin ke dokumentasi.

## Artefak penelitian yang tersedia

- `docs/baseline_results.md`: hasil baseline enam wilayah;
- `docs/sensitivity_results.md`: analisis sensitivitas Makassar–Rantepao;
- `docs/google_maps_api_limits.md`: hard limit dan API terlarang;
- `docs/black_box_testing.md`: matriks pengujian fungsional;
- `docs/proposal_alignment.md`: keselarasan implementasi dengan proposal; dan
- `docs/data_provenance.md`: status sumber/lisensi dan tindakan sebelum publikasi.
