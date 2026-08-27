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

`release_manifest.json` schema 5 mengunci identitas kandidat rilis berikut:

- versi aplikasi, hash source scope `application-runtime-v2`, dan versi Python
  yang didukung;
- keberadaan serta SHA-256 `constraints.txt`;
- path, jumlah baris, jumlah node logis, SHA-256 dataset, serta checksum
  `dataset_metadata.json`;
- empat konektor aplikasi, konfigurasi penelitian Combo 2, prioritas CCS2,
  fallback AC Type 2, baseline 430 km, artefak sumber range, dan definisi metrik
  temporal Google Routes;
- hard cap total detour 20 km, pengali radius 2, dan level sensitivitas
  10/20/30 km;
- `DRIVE`, `TRAFFIC_UNAWARE`, `HIGH_QUALITY`, dan margin lower bound geodesik 1%;
- manuver feri yang didukung, ketiadaan konsumsi SOC selama pelayaran, dan
  status akses kendaraan yang tidak dijamin;
- path, jumlah, konfigurasi konektor, dan checksum definisi skenario
  baseline/sensitivitas;
- checksum manifest penelitian yang menghubungkan snapshot ke run historis; dan
- hard limit harian, per menit, serta per request untuk Google Routes.

Audit memuat definisi eksperimen schema 4 melalui validator yang sama dengan
command `experiment-run`. Selain jumlah skenario dan checksum, konfigurasi
konektor setiap berkas harus sama dengan manifest dan ID skenario harus unik
lintas berkas. Laporan baru yang dihasilkan command memakai schema 5. Audit juga
menghitung ulang median dan pembulatan pada referensi kendaraan sehingga 430 km
tidak dapat diganti menjadi magic number tanpa mematahkan audit.

Scope `application-runtime-v2` mencakup berkas `.py`, `.html`, `.js`, `.css`,
dan `.svg` di bawah `app/`, ditambah `Dockerfile`, `.dockerignore`,
`.env.example`, `.github/workflows/ci.yml`, `gunicorn.conf.py`,
`requirements.txt`, `run.py`, dan `wsgi.py`. Seluruh berkas akar tersebut wajib
ada. Dengan demikian perubahan frontend, dependency langsung, konteks image,
contoh konfigurasi, workflow CI, atau entrypoint deployment ikut mengubah
identitas source, bukan hanya modul Python backend.

Audit yang sama dijalankan di dalam image. Karena itu `.dockerignore` tetap
mengecualikan seluruh `.env` rahasia, tetapi memasukkan kembali `.env.example`;
workflow `.github/workflows/ci.yml` juga ikut dalam konteks kandidat. Dummy atau
nilai contoh tidak boleh diganti dengan key nyata pada berkas yang dilacak.
Folder `docs/` dikecualikan dari image kecuali `docs/parameter_rationale.md`,
karena berkas itu dikunci sebagai artefak metodologi di manifest penelitian dan
wajib tersedia ketika audit dijalankan di dalam container.

Manifest penelitian schema 1 memisahkan versi analisis 0.18.0 dari versi
penghasil data live: baseline 0.9.2 dan sensitivitas 0.10.0, keduanya laporan
schema 2 dengan definisi skenario schema 1 tertanam. Ia mencatat artefak snapshot,
checksum, jumlah baris, transformasi pembentuk snapshot, lokasi/hash laporan
sumber, status arsip, dan keterbatasan.
Jika laporan sumber berstatus lokal/tidak dilacak, audit memverifikasi checksum
serta metadata ketika berkas tersedia, tetapi tidak menganggap clone repository
sebagai salinan lengkap arsip mentah.

Manifest hanya boleh diubah ketika perubahan source memang disengaja. Jika
dataset berubah, validasi dataset terlebih dahulu dan perbarui jumlah/hash
berdasarkan berkas baru. Jangan mengubah hash manifest hanya untuk membuat audit
hijau tanpa meninjau perubahan datanya.

## Batas audit

Audit offline tidak menggantikan pemeriksaan berikut:

- memastikan `.env`, ledger, dan laporan mentah tidak masuk commit;
- memastikan empat job Python dan satu job container GitHub Actions benar-benar
  hijau;
- memastikan artefak CI yang diunduh berasal dari revision kandidat yang sama;
- memeriksa restriction API key, domain HTTPS, volume persisten, dan gateway;
- mencocokkan pemakaian dengan Google Cloud Console;
- melakukan smoke test UI yang secara eksplisit diizinkan;
- menggantikan dokumentasi provenance, periode pengumpulan, atribusi, lisensi,
  atau konfirmasi hak redistribusi dataset; serta
- memvalidasi model SOC terhadap konsumsi kendaraan dunia nyata.

Item tersebut tetap terdapat dalam `release_checklist.md` karena bergantung pada
GitHub, lingkungan deployment, Google Cloud, atau persetujuan pengguna.

## Integrasi CI

Workflow menjalankan `release-audit` pada Python 3.11, 3.12, 3.13, dan 3.14 setelah
test serta kompilasi. API key tetap dikosongkan. Output `release-audit.json` dan
`coverage.xml` diunggah per versi Python selama 14 hari. Job container mengunggah
`container-health.json` dan `container-release-audit.json`, juga selama 14 hari.
Dengan demikian perubahan source, metadata/dataset, skenario, versi, parameter
algoritma, provenance penelitian, dependency, atau hard limit yang tidak
disertai pembaruan manifest akan menghentikan CI sebelum kandidat rilis digunakan.

Artefak yang diunggah ketika job gagal dapat tidak lengkap; status workflow dan
isi JSON tetap harus diperiksa, bukan hanya keberadaan nama artefaknya.
