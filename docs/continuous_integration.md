# Continuous integration

Workflow `.github/workflows/ci.yml` memverifikasi setiap push, pull request, dan
eksekusi manual melalui GitHub Actions. Matrix test memakai Python 3.11, 3.12,
dan 3.13 sesuai versi yang didukung proyek.

## Pemeriksaan otomatis

Setiap job matrix Python melakukan:

1. checkout source code tanpa mempertahankan kredensial Git;
2. instalasi `requirements-dev.txt` dengan `constraints.txt` dan `pip check`;
3. seluruh test dengan batas coverage minimum 90%;
4. kompilasi modul Python; dan
5. audit manifest kandidat rilis; dan
6. pemeriksaan sintaks JavaScript.

Setelah ketiga job Python lulus, job **Container smoke test**:

1. membangun image kandidat dengan Python 3.12 dan dependency lock;
2. menjalankan container dengan `--network none` serta dummy key;
3. menunggu Docker healthcheck dengan batas maksimum 60 detik;
4. memvalidasi status, versi, jumlah node, dan checksum dataset pada health JSON
   terhadap `release_manifest.json`, lalu menjalankan audit rilis di dalam
   container;
5. memastikan proses bukan root; dan
6. menguji akses tulis lalu membersihkan berkas serta container sementara.

Fixture test menggunakan dummy API key dan ledger pada direktori sementara.
Workflow sengaja mengosongkan environment variable Google Maps untuk membuktikan
bahwa CI tidak bergantung pada `.env`, secret, billing, ataupun koneksi ke Google
Maps API. Tidak ada eksperimen live di dalam workflow.

Audit manifest memeriksa versi, dataset, ruang lingkup algoritma, seluruh
skenario penelitian, hard limit quota, dan hash dependency lock. Rinciannya tersedia pada
[`release_audit.md`](release_audit.md).

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
5. Jangan menambahkan API key sebagai solusi kegagalan CI; test harus tetap
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
