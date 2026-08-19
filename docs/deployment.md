# Deployment produksi

Aplikasi produksi dijalankan melalui Gunicorn, bukan development server Flask.
Artefak deployment terdiri atas `wsgi.py`, `gunicorn.conf.py`, `Dockerfile`, dan
`.dockerignore`. Container berjalan sebagai user non-root.

## Konfigurasi wajib

Ketika `APP_ENV=production`, aplikasi berhenti saat startup apabila konfigurasi
berikut belum aman atau belum lengkap:

| Variable | Ketentuan |
|---|---|
| `SECRET_KEY` | acak, minimal 32 karakter, dan bukan nilai development |
| `FLASK_DEBUG` | `false` |
| `GOOGLE_MAPS_BROWSER_API_KEY` | key khusus browser |
| `GOOGLE_MAPS_SERVER_API_KEY` | key khusus backend Routes API |
| `GOOGLE_MAPS_MAP_ID` | Map ID milik proyek, bukan `DEMO_MAP_ID` |
| `TRUSTED_HOSTS` | hostname publik, plus `127.0.0.1` untuk Docker healthcheck |
| `PUBLIC_CONTACT_EMAIL` | email pengelola untuk halaman privasi/ketentuan |

Contoh membuat secret tanpa menampilkannya dalam riwayat source code:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Simpan secret melalui fasilitas secret/environment variable platform hosting.
Jangan memasukkannya ke Docker image, source code, tangkapan layar, atau GitHub.

## Menjalankan Gunicorn secara lokal

Instal dependency dan gunakan environment development agar tidak memerlukan
hostname produksi:

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt -c constraints.txt
APP_ENV=development PORT=8000 gunicorn --config gunicorn.conf.py wsgi:app
```

Periksa `http://127.0.0.1:8000/api/health`. Gunicorn memakai dua sync worker
secara default. Sesuaikan `WEB_CONCURRENCY` berdasarkan memori dan beban hasil
pengukuran, bukan hanya jumlah CPU. Timeout 120 detik memberi ruang untuk batch
validasi Google Routes pada rekomendasi yang panjang.

## Membangun dan menjalankan container

Sebelum membangun image, jalankan audit kandidat rilis tanpa API live:

```bash
python -m flask --app run.py release-audit
```

```bash
docker build -t spklu-sulawesi:0.14.0 .
docker run --rm -p 8080:8080 \
  --env-file .env.production \
  spklu-sulawesi:0.14.0
```

Base Python dapat diuji secara eksplisit dengan
`--build-arg PYTHON_VERSION=3.11` atau `3.13`. Image produksi kandidat tetap
memakai default Python 3.12. Seluruh instalasi memakai `constraints.txt` yang
hash-nya dikunci oleh manifest rilis.

Build kandidat rilis dapat memakai suffix sementara, misalnya
`spklu-sulawesi:0.14.0-rc1`. Jangan push image ke registry sebelum CI hijau,
secret produksi siap, dan target registry disetujui.

Jangan memakai `.env` development sebagai `.env.production`. Pastikan file
produksi tidak dilacak Git. Healthcheck container mengakses
`http://127.0.0.1:8080/api/health`, sehingga `127.0.0.1` harus terdapat pada
`TRUSTED_HOSTS`.

## Reverse proxy dan HTTPS

- Terminasi TLS/HTTPS dilakukan oleh platform hosting atau reverse proxy.
- `USE_PROXY_FIX=true` hanya jika tepat satu proxy tepercaya berada di depan
  Gunicorn. Konfigurasi ini mempercayai satu nilai `X-Forwarded-*`; jangan
  mengaktifkannya apabila Gunicorn dapat diakses langsung dari internet.
- Batasi akses langsung ke port Gunicorn ketika memakai reverse proxy.
- Pastikan request HTTPS menghasilkan header HSTS dan hostname publik terdapat
  pada `TRUSTED_HOSTS`.

## Menyiapkan Google Maps Platform

Gunakan satu Google Cloud project dengan billing dan quota yang dapat dipantau,
lalu buat dua key yang berbeda.

### Key browser

1. Aktifkan Maps JavaScript API dan Places API pada Google Cloud Console.
2. Buka **APIs & Services → Credentials → Create credentials → API key**.
3. Beri nama, misalnya `spklu-sulawesi-browser`.
4. Pada **Application restrictions**, pilih **Websites**.
5. Tambahkan referrer lokal hanya untuk pengembangan, misalnya
   `http://localhost:5000/*` dan `http://127.0.0.1:5000/*`.
6. Setelah domain tersedia, tambahkan `https://domain-anda.example/*` dan hapus
   referrer yang tidak diperlukan pada key produksi.
7. Pada **API restrictions**, batasi hanya ke Maps JavaScript API dan Places API.
8. Masukkan nilainya sebagai `GOOGLE_MAPS_BROWSER_API_KEY`.

### Key server

1. Buat API key kedua bernama `spklu-sulawesi-server`.
2. Pada **API restrictions**, batasi hanya ke Routes API.
3. Jika hosting menyediakan egress IP statis, pilih pembatasan IP dan tambahkan
   hanya IP keluar server tersebut.
4. Jika egress IP dinamis, jangan meletakkan key di browser. Simpan sebagai
   secret backend dan lindungi endpoint aplikasi menggunakan pembatasan trafik
   platform/reverse proxy.
5. Masukkan nilainya sebagai `GOOGLE_MAPS_SERVER_API_KEY`.

### Map ID dan quota

1. Buka **Google Maps Platform → Map Management** dan buat Map ID untuk Web.
2. Masukkan Map ID sebagai `GOOGLE_MAPS_MAP_ID`.
3. Atur quota harian/per-menit untuk Routes API sesuai anggaran penelitian.
4. Aktifkan budget alert. Budget alert memberi peringatan; quota adalah kontrol
   yang benar-benar membatasi jumlah penggunaan.
5. Uji key setelah restriction diterapkan dan pantau request yang ditolak.

Daftar hard limit Compute Routes, Route Matrix, Places, Get Place, map load, dan
layanan yang dilarang terdokumentasi pada
[`google_maps_api_limits.md`](google_maps_api_limits.md). Samakan nilainya dengan
quota Google Cloud sebelum deployment atau smoke test live.

### Ledger quota Routes API

Samakan `GOOGLE_COMPUTE_ROUTES_DAILY_LIMIT` dan
`GOOGLE_ROUTE_MATRIX_DAILY_ELEMENT_LIMIT` dengan batas harian project. Pertahankan
`GOOGLE_QUOTA_TIMEZONE=America/Los_Angeles` karena kuota per hari Google reset
pada tengah malam Pacific Time.

Path default ledger adalah
`reports/generated/google-routes-quota.json`. Jika eksperimen CLI dijalankan di
container atau endpoint web dipublikasikan, mount folder tersebut ke volume
persisten; container sementara akan kehilangan riwayat ketika dihapus. Jalankan
satu instance aplikasi pada filesystem lokal. File lock tidak mengoordinasikan
beberapa replica atau filesystem jaringan.

Ledger mengamankan eksperimen CLI dan endpoint web. Setiap rekomendasi
mereservasi maksimal 2 Compute Routes dan 625 elemen Matrix, kemudian mencatat
attempt aktual. Ia tidak menghitung request dari project atau program lain yang
memakai API key sama. Quota Google Cloud dan pembatasan trafik gateway tetap
wajib sebagai pengaman biaya utama.

## Checklist sebelum publik

1. Semua pengujian otomatis lulus dan eksperimen live terpisah dari smoke test.
2. Domain, HTTPS, `TRUSTED_HOSTS`, privacy, terms, dan email kontak sudah benar.
3. Browser key tidak dapat dipakai dari domain lain; server key tidak muncul di
   HTML, JavaScript, log, atau respons API.
4. Quota Google, limit trafik platform, concurrency, timeout, CPU, dan memori
   telah ditetapkan berdasarkan anggaran dan hasil evaluasi.
5. Endpoint `/api/health` dipantau tanpa memanggil layanan Google eksternal.
6. Dataset yang ter-deploy sama dengan versi yang dilaporkan dalam penelitian.
7. Deployment rollback menggunakan image/tag versi sebelumnya sudah disiapkan.

Eksperimen CLI dan endpoint web memiliki hard limit terpisah untuk panggilan
Compute Routes dan elemen Route Matrix, pemeriksaan kapasitas menit aktif, serta
ledger harian dengan reservasi atomik. Batas per menit disamakan dengan batas
harian sehingga tidak memaksa jeda, tetapi kontrol ini tidak menggantikan quota
Google dan limit trafik gateway.

## Kontrol keamanan aplikasi

Aplikasi membatasi request body menjadi 64 KiB, menggunakan host validation,
cookie aman pada produksi, CSP nonce yang kompatibel dengan Google Maps,
HSTS, anti-clickjacking, MIME sniffing protection, permissions policy, dan
respons error API yang tidak membocorkan exception internal. Endpoint API juga
mengirim `Cache-Control: no-store`.

Rate limiting sebaiknya dilakukan pada gateway/reverse proxy dan quota Google.
Limiter memori di dalam Flask tidak dipakai karena hitungannya akan berbeda pada
setiap worker Gunicorn dan tidak memberi perlindungan biaya yang dapat diandalkan.
