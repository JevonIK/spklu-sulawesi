# Dependency dan reproducible build

Proyek memakai dua lapis spesifikasi dependency:

- `requirements.txt` dan `requirements-dev.txt` menyatakan rentang kompatibilitas
  dependency langsung; dan
- `constraints.txt` mengunci versi dependency langsung serta transitif yang
  digunakan kandidat rilis 0.14.0.

Gunakan keduanya saat membuat environment pengembangan:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt -c constraints.txt
python -m pip check
```

Docker dan GitHub Actions juga memasang dependency dengan constraint yang sama.
Dockerfile menerima build argument `PYTHON_VERSION`; default kandidat produksi
tetap Python 3.12.

## Kompatibilitas Python

Satu hasil `pip freeze` dari Python 3.12 tidak boleh langsung dijadikan lock
lintas-versi. Contohnya, NumPy 2.5.2 yang sempat dipilih resolver lokal hanya
mendukung Python 3.12 ke atas. Kandidat rilis menggunakan NumPy 2.3.5 dan SciPy
1.16.3 yang mendukung Python 3.11, 3.12, dan 3.13. pandas 3.0.5 serta
scikit-learn 1.9.0 juga mendukung Python mulai 3.11.

Metadata kompatibilitas dapat diperiksa pada halaman resmi PyPI untuk
[NumPy 2.3.5](https://pypi.org/project/numpy/2.3.5/),
[SciPy 1.16.3](https://pypi.org/project/scipy/1.16.3/),
[pandas 3.0.5](https://pypi.org/project/pandas/3.0.5/), dan
[scikit-learn 1.9.0](https://pypi.org/project/scikit-learn/1.9.0/).

Instalasi container telah diverifikasi pada Python 3.11, 3.12, dan 3.13 dengan
NumPy 2.3.5 serta SciPy 1.16.3. Audit rilis sebelumnya di ketiga image lulus;
versi 0.14.0 mempertahankan audit sebanyak 24 check.

## Memperbarui dependency

Pembaruan lock harus dilakukan sebagai perubahan tersendiri:

1. tinjau release note dan requirement Python setiap paket yang diubah;
2. ubah versi pada `constraints.txt` tanpa memperlebar hard limit Google Maps;
3. buat environment bersih dan jalankan `pip check` serta seluruh test;
4. verifikasi instalasi pada Python 3.11, 3.12, dan 3.13;
5. hitung ulang SHA-256 `constraints.txt`;
6. perbarui `dependencies.sha256` pada `release_manifest.json`;
7. jalankan `release-audit`; dan
8. bangun ulang image serta lakukan smoke test offline.

Audit rilis sengaja gagal bila berkas constraint hilang atau hash-nya berbeda.
Jangan mengganti hash manifest hanya untuk membuat CI hijau tanpa meninjau versi
yang berubah dan menjalankan kembali matrix test.
