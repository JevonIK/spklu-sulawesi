# Rasionalisasi parameter penelitian dan implementasi

Dokumen ini menjadi sumber pusat untuk menjelaskan mengapa kandidat 0.18.0
memakai parameter tertentu. Ia memisahkan bukti literatur, eksperimen internal,
dan asumsi terkontrol agar paper tidak menyebut semua default sebagai nilai
optimum ilmiah.

## Klasifikasi kekuatan bukti

| Tingkat | Makna |
|---|---|
| **A — kuat** | didukung sumber eksternal relevan dan bukti internal yang konsisten |
| **B — terbatas** | mempunyai dasar eksternal atau eksperimen internal, tetapi cakupannya belum cukup untuk generalisasi |
| **C — asumsi terkontrol** | dipilih untuk membentuk baseline yang dapat direproduksi; bukan nilai optimum |
| **Teknis** | parameter implementasi/performa yang tidak mengubah definisi hasil penelitian |

## Ringkasan

| Parameter | Nilai kandidat | Status | Klaim yang aman |
|---|---:|---|---|
| BallTree `leaf_size` | 40 implisit | Teknis | default pustaka; bukan hasil tuning |
| Safety factor `alpha` | 0,9 | B | baseline hasil sensitivitas terbatas; bukan universal optimum |
| SOC minimum / target | 20% / 80% | A/B | kebijakan reserve dan partial charging yang evidence-informed |
| SOC awal | 80% | C | kondisi awal referensi yang dapat diganti pengguna |
| Maximum range | 430 km | B | median sampel WLTP model-family; bukan median penjualan Sulawesi |
| Konektor | CCS2 + AC Type 2 | A/B | profil tepat Combo 2; kombinasi lain diperlakukan netral tanpa ranking implisit |
| Hard cap total detour | 20 km | B | policy tengah `2 ×` radius; bukan optimum unik |
| Radius koridor | 10 km | B | level tengah sensitivitas lokal; bukan radius optimum seluruh Sulawesi |

## 1. BallTree `leaf_size=40`

Kode tidak menetapkan `leaf_size` secara eksplisit:

```python
BallTree(coordinates_radians, metric="haversine")
```

Karena itu nilai 40 diwarisi dari default kelas `sklearn.neighbors.BallTree`.
[Dokumentasi resmi scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.neighbors.BallTree.html)
menjelaskan bahwa perubahan leaf size tidak mengubah hasil query, tetapi dapat
memengaruhi waktu dan memori. Dengan 146 node, ia diperlakukan sebagai parameter
teknis, bukan variabel ilmiah.

**Batas klaim:** jangan menulis bahwa 40 adalah leaf size optimal. Tulis bahwa
implementasi memakai default scikit-learn dan correctness pencarian radius tidak
bergantung pada pemilihan tersebut.

## 2. Safety factor `alpha=0,9`

Model memakai:

```text
effective_range = maximum_range × alpha
```

Literatur EV routing menunjukkan bahwa konsumsi/range dipengaruhi ketidakpastian
dan bahwa robustness harus dipertimbangkan. Jeong et al. membahas trade-off
antara energi dan risiko kegagalan dalam robust EV routing
([DOI 10.1016/j.trc.2024.104529](https://doi.org/10.1016/j.trc.2024.104529)).
Literatur tersebut mendukung kebutuhan margin, tetapi tidak menetapkan 0,9
sebagai konstanta universal.

Bukti angka tepat 0,9 berasal dari sensitivitas historis Makassar–Rantepao:

| Alpha | Usable range 80→20% pada kendaraan 300 km | Stop | Edge |
|---:|---:|---:|---:|
| 0,8 | 144 km | 3 | 70 |
| 0,9 | 162 km | 1 | 93 |
| 1,0 | 180 km | 1 | 97 |

`0,8` menambah dua stop, sedangkan `1,0` tidak menyediakan derating. Nilai 0,9
dipertahankan sebagai kompromi baseline. Eksperimen hanya satu koridor, dataset
lama, dan satu run; hasilnya tidak membuktikan optimum seluruh Sulawesi.

## 3. SOC minimum 20% dan target 80%

Kedua nilai memiliki fungsi berbeda:

- 20% adalah reserve minimum model, bukan batas fisik BMS;
- 80% adalah target maksimum yang dievaluasi setelah charging stop;
- SOC aktual pengguna tetap dapat berada sampai 100%.

Kostopoulos et al. melaporkan bahwa charging 80–100% memiliki losses hampir dua
kali area 20–80% dan menyimpulkan charging di atas 80% tidak menguntungkan dalam
konteks waktu, range, dan umur baterai
([DOI 10.1016/j.egyr.2019.12.008](https://doi.org/10.1016/j.egyr.2019.12.008)).
Review Guo et al. menjelaskan pengaruh high SOC, cut-off voltage, temperatur,
dan depth of discharge terhadap degradasi
([DOI 10.3390/en14175220](https://doi.org/10.3390/en14175220)).
Penelitian EV routing oleh Keser et al. juga mengevaluasi partial charging
20–80% sebagai salah satu strategi operasional
([DOI 10.1049/itr2.70052](https://doi.org/10.1049/itr2.70052)).

Dasar target 80% lebih kuat daripada angka reserve tepat 20%. Reserve 20% tetap
merupakan policy konservatif yang dapat berbeda menurut kendaraan, kimia
baterai, kondisi, dan BMS.

## 4. SOC awal 80%

SOC awal 80% bukan hasil optimasi. Ia dipilih sebagai kondisi awal referensi
karena:

1. konsisten dengan target charging 80%;
2. membuat seluruh skenario berangkat dari kondisi yang sama; dan
3. menghindari asumsi bahwa setiap pengguna selalu berangkat pada 100%.

Nilai ini wajib diganti pengguna dengan SOC aktual. Dalam paper, istilah yang
tepat adalah **baseline initial condition**, bukan recommended starting SOC.

## 5. `maximum_range_km=430`

Artefak `research/vehicle_range_reference.json` memilih tujuh model-family BEV
penumpang resmi Indonesia yang memiliki data WLTP dan kompatibel dengan
ekosistem Type 2/CCS2. Satu nilai representatif dihitung per model-family:

```text
417,5; 519; 430; 497; 428; 535; 433 km
median = 433 km
nearest 10 km half-up = 430 km
```

Validator menghitung ulang setiap transformasi dan release audit mengunci hash
artefak. Rincian model serta URL pabrikan tersedia di
[`vehicle_range_reference.md`](vehicle_range_reference.md).

Literatur menunjukkan bahwa range bersifat heterogen menurut kendaraan,
lingkungan, dan faktor psikologis
([Zeng et al., DOI 10.1016/j.trc.2023.104459](https://doi.org/10.1016/j.trc.2023.104459)).
Karena sampel proyek tidak dibobot penjualan dan bukan data registrasi Sulawesi,
430 km disebut **reference vehicle range**, bukan range mobil rata-rata Sulawesi.

Semua skenario baseline kandidat, connector sensitivity, dan detour sensitivity
memakai 430 km. Pada range sensitivity, 430 km tetap menjadi kontrol, sedangkan
200/300/400/500 km adalah level stress-test satu-factor-at-a-time. Oleh karena
itu, keberadaan 300 km pada `sensitivitas-range-300` tidak menjadikannya baseline
baru. Laporan historis 0.9.2/0.10.0 juga tetap mencatat 300 km sesuai konfigurasi
yang benar-benar dijalankan dan tidak boleh ditulis ulang secara retroaktif.

## 6. Konektor CCS2 + AC Type 2

Combo 2 menggunakan bagian Type 2 untuk AC dan pin tambahan untuk DC. Arsitektur
ini dijelaskan dalam
[CharIN CCS Design Guide](https://www.charin.global/media/pages/technology/ccs-specification/42a9d61e04-1626949173/design_guide_combined_charging_system_v7.pdf).
Indonesia juga mengakui Type 2 AC, konektor DC konfigurasi AA, dan combined
charging configuration FF dalam
[Permen ESDM Nomor 1 Tahun 2023](https://jdih.esdm.go.id/dokumen/download?id=Permen+ESDM+Nomor+1+Tahun+2023.pdf).

Dataset kandidat mencatat:

| Konfigurasi publik | Node unik |
|---|---:|
| CCS2 | 42 |
| AC Type 2 | 92 |
| Union CCS2 + AC Type 2 | 114 |

Kombinasi tersebut merepresentasikan kendaraan Combo 2 lebih baik daripada
CCS2-only. Untuk **pilihan tepat** `{CCS2, AC Type 2}`, optimizer mendahulukan
CCS2 dan memakai AC Type 2 sebagai fallback. Ini adalah kebijakan operasional
berbasis arsitektur Combo 2, bukan ranking universal antarkonektor dan belum
merupakan optimum empiris connector-sensitivity live.

Tidak ada dasar yang cukup untuk menggunakan urutan penyimpanan dataset sebagai
ranking AC Type 2, CCS2, CHAdeMO, dan GB/T. Regulasi menetapkan kompatibilitas
serta kategori teknologi, bukan urutan preferensi. Literatur routing dengan
teknologi pengisian heterogen juga membedakan teknologi melalui recharge rate
dan biaya, bukan nama konektor semata
([Bezzi et al., 2023](https://doi.org/10.1016/j.trc.2023.104374);
[Keskin & Çatay, 2018](https://doi.org/10.1016/j.cor.2018.06.019)). Dataset
penelitian belum memuat atribut daya per konektor yang diperlukan untuk membuat
ranking semacam itu.

Karena itu kebijakan runtime adalah:

| Pilihan pengguna | Kebijakan |
|---|---|
| Satu konektor | konektor tersebut menjadi satu-satunya pilihan kompatibel |
| Tepat CCS2 + AC Type 2 | CCS2 utama; AC Type 2 fallback |
| Kombinasi multi-konektor lain | seluruh konektor kompatibel diperlakukan setara |

Untuk kombinasi netral, optimizer memilih rute berdasarkan kelayakan SOC,
durasi perjalanan, jumlah pemberhentian, detour, penambahan SOC, dan jarak.
Apabila satu SPKLU menawarkan lebih dari satu konektor pilihan, seluruh konektor
kompatibel ditampilkan tanpa label prioritas. Kebijakan ini mencegah urutan
kanonis `CONNECTOR_ORDER` berubah menjadi asumsi ilmiah tersembunyi.

Seluruh skenario kandidat utama memakai profil tepat CCS2 + AC Type 2 agar
sesuai dengan sampel kendaraan Combo 2 dan agar 114 node publik pada union kedua
konektor dapat dinilai. CCS2-only dipertahankan hanya sebagai kontrol pada
`scenarios_connector_sensitivity.json`; selisih hasilnya terhadap profil Combo 2
mengukur dampak perluasan cakupan dan pemakaian fallback secara eksplisit.

## 7. Hard cap total detour 20 km

Baseline diturunkan secara transparan:

```text
2 × radius koridor 10 km = 20 km
```

Sensitivitas live 0.18.0 menguji 10/20/30 km pada tiga koridor. Semua sembilan
skenario feasible dan setiap cap menghasilkan itinerary yang sama dalam
koridor yang sama. Cap hanya mengubah pruning DP:

| Koridor | Transisi dipangkas untuk cap 10/20/30 km |
|---|---:|
| Pendek | 0 / 0 / 0 |
| Menengah | 716 / 156 / 0 |
| Panjang | 59 / 0 / 0 |

Hasil lengkap terdapat di
[`detour_sensitivity_results.md`](detour_sensitivity_results.md). Bukti tersebut
mendukung 20 km sebagai policy tengah yang non-binding terhadap rute terpilih,
tetapi tidak membuktikannya sebagai optimum unik.

## 8. Radius koridor 10 km

Radius menentukan station yang dianggap cukup dekat dengan rute dasar.
Sensitivitas historis Makassar–Rantepao memberi:

| Radius | Kandidat | Edge | Matrix | Itinerary |
|---:|---:|---:|---:|---|
| 5 km | 14 | 82 | 93 | LAGOTA CAFE |
| 10 km | 15 | 93 | 105 | LAGOTA CAFE |
| 15 km | 15 | 93 | 105 | LAGOTA CAFE |

Sepuluh kilometer dipilih sebagai level tengah: ia mempertahankan satu kandidat
yang hilang pada 5 km, sementara 15 km tidak menambah kandidat pada koridor
tersebut. Bukti ini hanya satu koridor CCS2/dataset lama. Literatur EV charging
menunjukkan bahwa batas jarak dan detour memengaruhi keputusan route-and-charge,
tetapi tidak menyediakan radius universal 10 km
([Zeng et al.](https://doi.org/10.1016/j.trc.2023.104459)).

**Batas klaim:** tulis “baseline corridor radius selected from a bounded local
sensitivity analysis”, bukan “optimal corridor radius for Sulawesi”.

## Kalimat metode yang direkomendasikan

> The study used an evidence-informed baseline parameterization rather than
> claiming universally optimal defaults. Library-level parameters were retained
> for reproducibility, battery and connector choices were grounded in external
> evidence and dataset compatibility, and scenario-dependent values were bounded
> through local sensitivity analyses. Limitations were reported wherever the
> available evidence did not support generalization across Sulawesi.

## Daftar sumber eksternal utama

1. scikit-learn, BallTree API: <https://scikit-learn.org/stable/modules/generated/sklearn.neighbors.BallTree.html>
2. Jeong et al. (2024), robust EV routing: <https://doi.org/10.1016/j.trc.2024.104529>
3. Kostopoulos et al. (2020), real-world EV charging: <https://doi.org/10.1016/j.egyr.2019.12.008>
4. Guo et al. (2021), lithium-ion degradation review: <https://doi.org/10.3390/en14175220>
5. Keser et al. (2025), partial charging 20–80%: <https://doi.org/10.1049/itr2.70052>
6. Zeng et al. (2024), heterogeneous driving range and en-route charging: <https://doi.org/10.1016/j.trc.2023.104459>
7. CharIN, CCS technical overview: <https://www.charin.global/faq-section/>
8. Permen ESDM Nomor 1 Tahun 2023: <https://jdih.esdm.go.id/dokumen/download?id=Permen+ESDM+Nomor+1+Tahun+2023.pdf>
