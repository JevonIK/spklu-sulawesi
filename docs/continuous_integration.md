# Continuous integration

Workflow `.github/workflows/ci.yml` memverifikasi setiap push, pull request, dan
eksekusi manual melalui GitHub Actions. Matrix test memakai Python 3.11, 3.12,
dan 3.13 sesuai versi yang didukung proyek.

## Pemeriksaan otomatis

Setiap job matrix Python melakukan:

1. checkout source code tanpa mempertahankan kredensial Git;
2. instalasi `requirements-dev.txt` dengan `constraints.txt` dan `pip check`;
3. seluruh test dengan batas coverage minimum 90%;
4. kompilasi modul Python;
5. validasi seluruh artefak JSON penelitian;
6. audit manifest kandidat rilis;
7. pemeriksaan sintaks JavaScript; dan
8. pengunggahan `coverage.xml` serta `release-audit.json` meskipun job gagal.

Setelah ketiga job Python lulus, job **Container smoke test**:

1. membangun image kandidat dengan Python 3.12 dan dependency lock;
2. menjalankan container dengan `--network none`, root filesystem read-only,
   semua Linux capability dilepas, `no-new-privileges`, tmpfs terbatas, dan dummy
   key;
3. menunggu Docker healthcheck dengan batas maksimum 60 detik;
4. memvalidasi status, versi, jumlah node, dan checksum dataset pada health JSON
   terhadap `release_manifest.json`, lalu menjalankan audit rilis di dalam
   container;
5. memastikan proses bukan root, dependency konsisten, dan source `/app/app`
   tidak dapat ditulis oleh user runtime;
6. menguji akses tulis hanya pada `/app/reports/generated`; dan
7. mengunggah health/audit JSON sebagai bukti sebelum membersihkan container.

Dockerfile menyalin source sebagai milik root. User `spklu` hanya memperoleh
direktori tulis untuk ledger/laporan. Pada CI, root filesystem dibuat read-only;
`/tmp` dan `/app/reports/generated` disediakan melalui tmpfs. Mount laporan
memakai `mode=1777` agar user non-root tetap dapat menulis setelah ownership
direktori image tertutup oleh mount, dengan sticky bit untuk membatasi
penghapusan lintas-user. Deployment yang memerlukan ledger persisten harus
mengganti tmpfs laporan dengan volume yang
ownership-nya sesuai, tanpa menjadikan source writable.

Fixture test menggunakan dummy API key dan ledger pada direktori sementara.
Workflow sengaja mengosongkan environment variable Google Maps untuk membuktikan
bahwa CI tidak bergantung pada `.env`, secret, billing, ataupun koneksi ke Google
Maps API. Tidak ada eksperimen live di dalam workflow.

Audit manifest memeriksa versi/hash source `application-runtime-v2`—termasuk
dependency langsung, aturan konteks Docker, contoh konfigurasi, dan workflow
CI—serta metadata/dataset, ruang lingkup algoritma, konstanta Routes, margin
geodesik, seluruh skenario penelitian, provenance snapshot historis, hard limit
quota, dan hash dependency lock.
Rinciannya tersedia pada
[`release_audit.md`](release_audit.md).

## Artefak bukti

Setiap job Python mengunggah artefak `quality-python-<versi>` yang memuat
`coverage.xml` dan `release-audit.json`. Job container mengunggah
`container-smoke-evidence` yang memuat `container-health.json` dan
`container-release-audit.json`. Retensi workflow adalah 14 hari.

Karena upload memakai `if: always()`, artefak dapat tetap muncul dari job gagal
dan beberapa file dapat tidak ada. Pemeriksa wajib memastikan status job hijau,
revision/commit sesuai kandidat, `failed_count` audit nol, versi health sama
dengan manifest, serta coverage memenuhi ambang. Nama artefak saja bukan bukti
kelulusan dan artefak CI bukan pengganti arsip laporan live penelitian.

Workflow menggunakan major release `actions/checkout@v6` dan
`actions/setup-python@v6`. Versi tersebut mengikuti dokumentasi resmi repository
[checkout](https://github.com/actions/checkout) dan
[setup-python](https://github.com/actions/setup-python).

## Pemeriksaan hasil di GitHub

1. Buka tab **Actions** pada repository.
2. Pilih workflow **Validasi aplikasi**.
3. Pastikan job Python 3.11, Python 3.12, Python 3.13, dan
   **Container smoke test** berwarna hijau.
4. Buka setiap job jika ada kegagalan dan baca langkah pertama yang merah.
5. Unduh artefak keempat job, cocokkan revision, lalu periksa JSON/XML-nya.
6. Jangan menambahkan API key sebagai solusi kegagalan CI; test harus tetap
   berjalan tanpa secret.

## Branch protection yang disarankan

Setelah workflow pertama berhasil:

1. buka **Settings → Branches** atau **Rules → Rulesets**;
2. buat aturan untuk branch utama (`main` atau nama branch utama repository);
3. aktifkan kewajiban status checks sebelum merge;
4. pilih check `Python 3.11`, `Python 3.12`, `Python 3.13`, dan
   `Container smoke test`; dan
5. jangan aktifkan deployment otomatis yang memakai billing sebelum environment
   produksi serta approval manual tersedia.

Branch protection merupakan pengaturan repository GitHub dan tidak dapat
ditetapkan hanya melalui source code lokal.
