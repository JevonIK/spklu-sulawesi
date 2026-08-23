# Keselarasan implementasi dengan proposal

Dokumen ini menjadi checklist agar implementasi, eksperimen, dan naskah tugas
akhir memakai ruang lingkup yang sama. Instruksi terbaru pemilik penelitian
menjadi acuan: aplikasi umum mendukung seluruh konektor pada dataset, sedangkan
eksperimen penelitian terdokumentasi memakai CCS2; kapasitas kendaraan dinyatakan
dalam jangkauan maksimum (km), unit pada koordinat sama dipertahankan sebagai
informasi tetapi menjadi satu node algoritma, dan waktu pengisian tidak dihitung.

## Pemetaan komponen

| Kebutuhan penelitian | Implementasi/bukti |
|---|---|
| Dataset enam wilayah Sulawesi | `dataset_spklu_sulawesi.csv` dan validasi `app/services/dataset.py` |
| Beberapa unit satu lokasi | `StationNode.units`; satu `node_id` dipakai graf untuk setiap koordinat identik |
| Kompatibilitas konektor | normalisasi dataset, pilihan input, dan filter kandidat; baseline/sensitivitas memakai CCS2 |
| Akses jaringan dealer | metadata jaringan per unit, pilihan jaringan tambahan, dan status rute kondisional |
| Kandidat berbasis Ball Tree | `app/services/spatial.py` |
| Rute dan jarak jalan | `app/services/google_routes.py` |
| Graf berarah | `app/services/graph.py` |
| Model jangkauan dan SOC | `app/services/energy.py` |
| Dynamic Programming state `(node, SOC)` | `app/services/optimizer.py` |
| Rekomendasi multi-stop | `app/services/recommendation.py` |
| Validasi SOC rute final | rekonsiliasi setiap leg Compute Routes final pada `app/services/recommendation.py` |
| Evaluasi enam wilayah dan sensitivitas | `experiments/`, `app/services/evaluation.py`, `docs/baseline_results.md`, dan `docs/sensitivity_results.md` |
| Provenance data/hasil | `dataset_metadata.json`, manifest penelitian, dan `notebooks/data/provenance.json` |
| Pengujian otomatis | `tests/` |

## Metrik proposal

Perangkat evaluasi mencatat feasibility rate, pelanggaran SOC, jumlah
perhentian, jarak, waktu berkendara, detour, request API, runtime, penggunaan
memori, jumlah kandidat, statistik graf, dan statistik DP. Definisi dan cara
menjalankannya terdapat di `docs/evaluation.md`.

Tidak ada metrik estimasi waktu pengisian. Waktu perjalanan yang tersedia adalah
waktu berkendara dari Google Routes API.

## Koreksi naskah proposal yang perlu dilakukan

Versi proposal yang diperiksa masih mengandung beberapa istilah dari ruang
lingkup lama. Sebelum naskah berikutnya dikumpulkan, lakukan koreksi berikut:

1. Pada ringkasan, hapus `daya pengisian` dari atribut data jika memang tidak
   tersedia dan tidak dipakai algoritma.
2. Pada bagian metode DP, hapus pertimbangan `daya pengisian` atau
   `charging power`.
3. Ubah objektif `total waktu perjalanan dan pengisian` menjadi objektif waktu
   berkendara/jarak jalan dengan tie-break jumlah perhentian dan detour sesuai
   implementasi.
4. Hapus `estimasi waktu pengisian daya` dari keluaran sistem dan flowchart.
5. Ubah metrik `total waktu perjalanan dan pengisian` menjadi `total waktu
   berkendara`.
6. Pada luaran yang diharapkan, hapus komponen `waktu pengisian`.
7. Jelaskan bahwa sistem dapat memfilter AC Type 2, CCS2, CHAdeMO, dan GB/T,
   sedangkan eksperimen baseline dan sensitivitas memakai CCS2.
8. Gunakan satuan `km` untuk jangkauan maksimum kendaraan; GB/T adalah nama
   konektor dan bukan satuan atau parameter kapasitas.
9. Hapus `jumlah kandidat SPKLU pada setiap segmen` dari daftar parameter
   sensitivitas, atau ubah menjadi analisis jumlah kandidat aktual akibat
   perubahan radius koridor. Radius search penelitian mengembalikan seluruh
   titik dalam radius dan rumusan masalah secara eksplisit tidak memakai
   fixed-K.
10. Jelaskan bahwa konektor dan akses jaringan merupakan dua filter berbeda.
    SPKLU publik selalu disertakan, sedangkan charger Hyundai, Wuling, dan
    Toyota/Lexus bersifat opsional serta menghasilkan rute kondisional jika
    benar-benar dipakai itinerary.
11. Nyatakan konfigurasi Routes secara tepat: `HIGH_QUALITY` dan
    `TRAFFIC_UNAWARE`; waktu berkendara tidak memuat lalu lintas real-time.
12. Jelaskan margin 1% sebagai toleransi lower bound geodesik untuk
    prapemangkasan, terpisah dari safety factor energi.
13. Bedakan validasi SOC hasil DP/Route Matrix dari rekonsiliasi SOC pada setiap
    leg Compute Routes final.
14. Atribusikan baseline kepada aplikasi 0.9.2 dan sensitivitas kepada 0.10.0;
    0.15.0 adalah kandidat analisis, bukan penghasil kedua run live tersebut.
15. Ungkap bahwa sumber asli, tanggal snapshot, metode pengumpulan, lisensi, dan
    hak redistribusi dataset belum dikonfirmasi; jangan menyebut data resmi,
    lengkap, terkini, atau open data tanpa bukti.
16. Untuk rute yang memuat feri, pisahkan jarak pelayaran dari jarak energi.
    Nyatakan bahwa deteksi Google bukan bukti jadwal, kapasitas, atau izin
    kendaraan dan seluruh akses feri bersifat kondisional.

Rencana pengembangan model waktu pengisian pada roadmap tahun berikutnya dapat
tetap dicantumkan apabila dinyatakan jelas sebagai pekerjaan masa depan, bukan
fitur sistem penelitian saat ini. Pembahasan waktu pengisian dalam latar belakang
juga boleh dipertahankan sebagai konteks umum selama tidak mengklaim bahwa sistem
menghitungnya.

## Batas interpretasi

- Sistem merekomendasikan kelayakan berdasarkan model jangkauan linier dan
  safety factor, bukan simulasi baterai elektrokimia.
- Data unit pada node terkonsolidasi tetap ditampilkan, tetapi tidak boleh
  dianggap sebagai beberapa lokasi alternatif oleh algoritma.
- Skenario infeasible merupakan hasil penelitian yang valid bila API berhasil
  dan graf memang tidak mempunyai rangkaian edge aman.
- Hasil live harus menyertakan tanggal dan parameter karena data jalan, layanan
  Google, dan dataset SPKLU dapat berubah.
- Status rute kondisional bukan bukti izin penggunaan charger dealer; pengguna
  tetap harus melakukan konfirmasi operasional sebelum perjalanan.
- Status feri kondisional bukan bukti kapal beroperasi atau menerima mobil;
  jadwal, kapasitas, antrean, dan aturan operator tetap harus dikonfirmasi.
- Nol pelanggaran SOC berarti konsisten dengan model linier dan data leg yang
  dipakai versi penghasil, bukan validasi konsumsi kendaraan nyata.
- Hash dataset/artefak menjamin identitas byte, bukan provenance atau izin
  redistribusi. Tindak lanjut terdapat pada
  [`data_provenance.md`](data_provenance.md).
