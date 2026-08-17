# Audit kandidat rilis offline

Audit rilis mengubah bagian checklist yang dapat diverifikasi mesin menjadi satu
perintah deterministik. Pemeriksaan hanya membaca source, dataset, konfigurasi,
dan skenario lokal; tidak ada Maps, Places, Compute Routes, atau Route Matrix
yang dipanggil.

```bash
source .venv/bin/activate
python -m flask --app run.py release-audit
```

Perintah keluar dengan status `0` jika seluruh check lulus dan status nonzero
jika ada perbedaan. Output JSON memuat ID check, nilai yang diharapkan, nilai
aktual, serta ringkasan jumlah check lulus/gagal sehingga dapat diarsipkan atau
dibaca oleh CI.

## Sumber kebenaran

`release_manifest.json` mengunci identitas kandidat rilis berikut:

- versi aplikasi dan versi Python yang didukung;
- keberadaan serta SHA-256 `constraints.txt`;
- path, jumlah baris, jumlah node logis, dan SHA-256 dataset;
- empat konektor aplikasi, konektor eksperimen CCS2, dan ketiadaan estimasi
  waktu pengisian;
- path serta jumlah skenario baseline/sensitivitas; dan
- hard limit harian, per menit, serta per request untuk Google Routes.

Audit memuat definisi eksperimen melalui validator yang sama dengan command
`experiment-run`. Selain jumlah skenario, semua konektor skenario penelitian
harus dinormalisasi menjadi CCS2 dan ID skenario harus unik lintas berkas.

Manifest hanya boleh diubah ketika perubahan source memang disengaja. Jika
dataset berubah, validasi dataset terlebih dahulu dan perbarui jumlah/hash
berdasarkan berkas baru. Jangan mengubah hash manifest hanya untuk membuat audit
hijau tanpa meninjau perubahan datanya.

## Batas audit

Audit offline tidak menggantikan pemeriksaan berikut:

- memastikan `.env`, ledger, dan laporan mentah tidak masuk commit;
- memastikan tiga job GitHub Actions benar-benar hijau;
- memeriksa restriction API key, domain HTTPS, volume persisten, dan gateway;
- mencocokkan pemakaian dengan Google Cloud Console; atau
- melakukan smoke test UI yang secara eksplisit diizinkan.

Item tersebut tetap terdapat dalam `release_checklist.md` karena bergantung pada
GitHub, lingkungan deployment, Google Cloud, atau persetujuan pengguna.

## Integrasi CI

Workflow menjalankan `release-audit` pada Python 3.11, 3.12, dan 3.13 setelah
test serta kompilasi. API key tetap dikosongkan. Dengan demikian perubahan
dataset, skenario, versi, atau hard limit yang tidak disertai pembaruan manifest
akan menghentikan CI sebelum kandidat rilis digunakan.
