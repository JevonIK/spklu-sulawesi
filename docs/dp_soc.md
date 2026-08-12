# Dynamic Programming dengan State SOC

Optimizer menggunakan state `(node, SOC)` pada graf berarah yang telah dibentuk.
SOC didiskretkan secara konservatif: nilai kontinu dibulatkan turun ke grid yang
berjangkar pada SOC minimum. Dengan demikian, pembulatan tidak membuat kendaraan
terlihat mempunyai energi lebih besar daripada estimasi sebenarnya.

## Model energi

Jangkauan efektif kendaraan adalah:

```text
Reffective = Rmax × alpha
```

Usable range pada SOC tertentu adalah:

```text
Rusable = ((SOC - SOCmin) / 100) × Rmax × alpha
```

Konsumsi SOC sebuah edge dengan jarak jalan `d` adalah:

```text
SOCconsumption = (d / (Rmax × alpha)) × 100
```

Edge hanya feasible jika SOC saat tiba tetap berada pada atau di atas SOC minimum.
Safety factor `alpha` berada pada rentang lebih dari 0 sampai 1 dan menjadi margin
ketidakpastian konsumsi energi.

## Transisi DP

- Origin memakai SOC awal pengguna dan tidak melakukan pengisian.
- Pada SPKLU, optimizer mengevaluasi tingkat pengisian diskret yang lebih tinggi
  daripada SOC kedatangan sampai batas target SOC.
- Destination tidak mempunyai transisi keluar.
- SPKLU yang masuk itinerary selalu melakukan pengisian; node SPKLU tidak dipakai
  sebagai waypoint tanpa aktivitas pengisian.

Informasi predecessor disimpan pada setiap state terbaik untuk merekonstruksi
urutan leg, lokasi pengisian, SOC tiba, dan SOC berangkat.

## Fungsi objektif

Kelayakan SOC merupakan constraint wajib. Solusi feasible dibandingkan secara
leksikografis berdasarkan:

1. total waktu berkendara;
2. jumlah pemberhentian pengisian;
3. total detour;
4. jumlah SOC yang ditambahkan sebagai tie-breaker agar pengisian tidak berlebih;
5. total jarak jalan sebagai tie-breaker terakhir.

Jika data durasi belum tersedia pada graf, seluruh optimasi menggunakan total
jarak jalan sebagai objective utama. Mode objective selalu dicantumkan pada hasil,
sehingga eksperimen tidak mencampur satuan waktu dan jarak secara tersembunyi.

Estimasi waktu pengisian, kapasitas baterai, dan daya charger tidak digunakan.

## Verifikasi akhir

Setelah predecessor direkonstruksi, seluruh leg disimulasikan ulang memakai SOC
kontinu. Hasil ditolak jika simulasi menemukan SOC di bawah batas minimum. Laporan
mencakup konsumsi tiap leg, SOC tiba/berangkat, jumlah pengisian, jarak, waktu
berkendara bila tersedia, detour, final SOC, serta SOC minimum yang teramati.

