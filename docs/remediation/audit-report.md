# Audit Teknis dirgaEA
## AdaptiveSurvivalEA · 8 September 2026

**Repo:** [marko1kiro/dirgaEA](https://github.com/marko1kiro/dirgaEA)  
**Branch:** `main`  
**Commit yang diaudit:** `844987eea6601379fcb534fd9aac8fe98a71c241`  
**Mode:** baca-saja; tidak ada perubahan/push kode, koneksi broker, atau transaksi trading.

> **Kesimpulan: belum layak diberi persetujuan untuk akun riil.** Ada 12 temuan utama: **1 kritis, 7 tinggi, dan 4 sedang**. Beberapa kontrol yang dimaksudkan melindungi modal masih dapat gagal pada alur yang dapat ditunjukkan dari kode. Lulusnya 518 tes Python tidak membuktikan keamanan eksekusi EA native.

Penilaian ini mengenai ketepatan implementasi dan kontrol operasional—bukan penilaian bahwa strateginya pasti rugi atau pasti menguntungkan.

## 1. Dasar audit dan hasil pengujian

Repo berhasil di-clone. Pemeriksaan mencakup 19 file MQL utama, total **7.689 baris**, meliputi event EA, H1 brain/regime, tiga strategi M15, quality gate, sizing risiko, pengelolaan posisi, execution bridge, berita/sesi, serta kode tes terkait.

| Pemeriksaan | Hasil |
|---|---|
| Snapshot sumber | Commit dikunci; seluruh 19 file MQL yang ditinjau cocok dengan arsip commit lengkap |
| Tes repo saat audit | **518 passed, 0 failed**, exit 0 |
| Lingkungan tes | Python 3.12.14; pytest 9.1.1; `python -m pytest -ra -q` |
| Pemeriksaan tambahan | **9 counterexample logika berhasil direproduksi**, memakai fixture sintetis dan pemeriksaan keterkaitan dengan sumber |
| Kompilasi MetaEditor baru | **Tidak dilakukan**; compiler tidak tersedia |
| Native MQL / Strategy Tester / demo broker | **Tidak dijalankan** |
| Profitabilitas, drawdown historis, ketahanan parameter | **Belum dapat disimpulkan** |

**Makna bukti:** “terkonfirmasi dari kode” berarti jalur/rumus yang salah terlihat di sumber. Counterexample tambahan adalah simulasi logika terisolasi, **bukan** eksekusi MQL native, fill broker, atau backtest. Risiko duplikasi fill dan kerugian aktual tetap bergantung pada kondisi runtime.

Tes repo terdiri dari model/reference Python dan pemeriksaan kontrak teks sumber. Ada sumber probe native B06/B07, tetapi probe tersebut tidak dieksekusi di audit ini. Tes B10 execution hanya 3 kasus, B14 session/news 3, dan B15 execution safety 2; jalur runtime penting di bawah belum dibuktikan oleh suite tersebut. Klaim compile pada pesan commit merupakan klaim historis repo, bukan hasil kompilasi baru saya.

## 2. Daftar temuan utama

| ID | Keparahan | Temuan | Dampak utama |
|---|---|---|---|
| F01 | **Kritis** | Inisialisasi lock masih memiliki race condition | Dua instance dapat sama-sama menganggap berhak mengirim order |
| F02 | **Tinggi** | Baseline batas rugi harian salah setelah restart/pergantian hari | Proteksi daily loss dapat ter-reset atau memakai hari yang salah |
| F03 | **Tinggi** | Kalender berita tidak konsisten memblokir saat data gagal/tidak mutakhir | Entry dapat lolos saat data UNKNOWN atau mendekati berita |
| F04 | **Tinggi** | Modifikasi SL SELL divalidasi sebagai BUY | Breakeven/trailing SELL normal ditolak |
| F05 | **Tinggi** | Timeout order menghentikan rekonsiliasi tanpa memblokir entry baru | Outcome order ambigu dapat ditinggalkan |
| F06 | **Tinggi** | Klasifikasi volatilitas memakai skala yang salah | Kandidat VOL_HIGH/VOL_EXTREME tidak terjangkau melalui alur ini |
| F07 | **Tinggi** | SL dibulatkan menjauh setelah sizing risiko disetujui | Risiko request final dapat melewati hard cap |
| F08 | **Sedang** | Strategi range dan breakout belum tersambung ke alur EA | Dua modul ada, tetapi tidak pernah menghasilkan dispatch |
| F09 | **Tinggi** | Harga/waktu break–retest lama dan quality tidak dihitung ulang pada quote final | Penilaian setup bisa tidak sesuai entry sebenarnya |
| F10 | **Sedang** | Spread saat ini masuk ke baseline sebelum diperiksa | Veto lonjakan spread dapat terlalu longgar |
| F11 | **Sedang** | Penyimpanan swing berhenti pada kapasitas 256 | Struktur strategi membeku pada operasi jangka panjang |
| F12 | **Sedang** | Metadata initial SL tidak mengikuti lifecycle posisi dengan benar | Basis 1R bisa berubah; fallback SL belum melindungi posisi di broker |

Keparahan mempertimbangkan dampak pada modal dan fungsi EA. F01 khususnya membutuhkan skenario multi-instance; bukan pernyataan bahwa semua pemasangan satu instance akan mengirim order ganda.

## 3. Bukti dan perbaikan

### F01 — Lock belum menjamin satu pemilik

**Sumber:** [ExecutionBridge.mqh:299–355](https://github.com/marko1kiro/dirgaEA/blob/844987eea6601379fcb534fd9aac8fe98a71c241/ExecutionBridge.mqh#L299-L355); `AdaptiveSurvivalEA.mq5:1025–1038`.

`GlobalVariableCheck` lalu `GlobalVariableSet(..., 0)` bukan operasi create-if-absent atomik. Urutan yang sah: A dan B sama-sama membaca key belum ada; A membuat key dan memperoleh lock; B kemudian menulis nol, menimpa token A, lalu memperoleh lock juga. Jika keduanya memeriksa exposure sebelum order terlihat, keduanya dapat lanjut mengirim.

**Perbaikan:** gunakan inisialisasi dan kepemilikan yang benar-benar atomik; jangan menulis nol tanpa syarat di jalur kompetitif. Simpan owner/lease dengan protokol generasi yang konsisten. Pembacaan expiry dan CAS owner saat ini juga tidak mengikat versi lease: renewal yang terjadi di antaranya bisa terabaikan. Metode renewal sendiri belum dipanggil dalam alur aktif.

**Tes penerimaan:** interleaving dua instance harus menghasilkan maksimal satu pemilik/pengirim; renewal harus menggagalkan takeover berdasarkan expiry lama. **Counterexample P06.**

### F02 — Daily loss bukan baseline harian yang andal

**Sumber:** [AdaptiveSurvivalEA.mq5:706–831](https://github.com/marko1kiro/dirgaEA/blob/844987eea6601379fcb534fd9aac8fe98a71c241/AdaptiveSurvivalEA.mq5#L706-L831), juga `1157–1209`.

`daily_start_equity` hanya diisi ketika nilainya nol. Tidak disimpan untuk restart dan tidak diperbarui ketika hari berganti. Rumusnya menyederhana menjadi:

`totalLoss = daily_start_equity − currentEquity`

Merekonstruksi `daily_net_pnl` tidak memperbaiki baseline karena nilai tersebut saling menghapus dalam rumus. Pada pemeriksaan pertama setelah restart, baseline diisi equity saat itu: komponen daily-loss langsung menjadi nol walaupun hari tersebut sudah rugi. Guard consecutive-loss adalah kontrol terpisah, bukan penyelesaian bug ini.

Pada rollover, contoh baseline lama 10.000, equity awal hari baru 11.000, lalu turun ke 10.770: kerugian hari baru 230 atau >2%, tetapi guard membaca keuntungan 770 terhadap baseline lama.

**Cacat ledger terkait:** runtime menghitung streak per exit deal, bukan posisi yang benar-benar selesai; partial close ikut dihitung. Rekonstruksi mengabaikan `DEAL_FEE`, dan kedua jalur mengabaikan komisi entry. Ini dapat membuat streak/ledger berbeda sebelum dan sesudah restart.

**Perbaikan:** tetapkan scope account atau symbol/magic secara eksplisit; persist baseline berdasarkan akun dan tanggal broker, tangani cashflow, rollover, floating P/L, serta gagal baca history. Hitung streak dari lifecycle posisi penuh dengan seluruh komponen biaya. Guard saat ini hanya memblokir entry, **bukan** batas kerugian terjamin atau perintah likuidasi otomatis.

**Tes:** restart setelah rugi, rollover dengan floating position, partial close, biaya entry/exit, dan perubahan dana. **P05.**

### F03 — News guard dapat kembali menjadi CLEAR saat seharusnya tidak

**Sumber:** [SessionNewsEngine.mqh:25–31](https://github.com/marko1kiro/dirgaEA/blob/844987eea6601379fcb534fd9aac8fe98a71c241/SessionNewsEngine.mqh#L25-L31), `76–99`, `111–156`; caller `AdaptiveSurvivalEA.mq5:1000–1015`.

Dua masalah terpisah:

1. `AggregateState` tidak menangani `NEWS_UNKNOWN`. Kegagalan API pertama mengembalikan UNKNOWN, tetapi panggilan berikutnya menggunakan cache: `AggregateState(CLEAR, UNKNOWN)` menghasilkan **CLEAR**. Kegagalan resolve event juga melewati agregasi ini; kegagalan resolve country hanya dilewati. Jadi `NewsGuardRequired=true` tidak menjamin pemblokiran.
2. Yang di-cache selama **3.600 detik** adalah *status waktu*, bukan daftar event; query hanya mencakup **±1.800 detik**. Misalnya pada 08:00 hasil CLEAR disimpan; berita 08:45 di luar query. Pada 08:30 cache CLEAR masih digunakan, padahal berita sudah masuk jendela larangan 30 menit. Query mundur 30 menit juga tidak menutup seluruh recovery window 45 menit.

**Perbaikan:** jadikan ketidaktersediaan kalender status keselamatan yang tidak dapat hilang saat agregasi; cache data event dengan cakupan cukup, lalu hitung status terhadap waktu terkini setiap evaluasi. Refresh sebelum cakupan tidak memadai. Currency/event/country yang tidak dapat diverifikasi jangan dianggap CLEAR bila guard diwajibkan.

**Tes:** API gagal berulang termasuk cache-hit; resolve gagal; CLEAR → LOCK → SHOCK → RECOVERY → CLEAR pada waktu yang bergerak. **P03–P04.**

### F04 — SELL trailing/BE selalu masuk aturan BUY

**Sumber:** [ExecutionBridge.mqh:212–245](https://github.com/marko1kiro/dirgaEA/blob/844987eea6601379fcb534fd9aac8fe98a71c241/ExecutionBridge.mqh#L212-L245), `642–655`.

Cabang pertama `ValidateStopFreeze` menerima BUY **atau MODIFY_SL**. Cabang SELL juga menyebut MODIFY_SL tetapi tidak mungkin dicapai untuk aksi tersebut. SL SELL yang benar berada di atas Ask; aturan BUY justru mengharuskannya di bawah Bid, sehingga modifikasi normal ditolak.

**Perbaikan:** teruskan arah posisi secara eksplisit dan validasi aturan BUY/SELL secara terpisah. Jangan menyimpulkan arah dari aksi generik MODIFY_SL.

**Tes:** BUY dan SELL simetris, batas stops/freeze, serta SL salah sisi. **P02.**

### F05 — Status timeout justru keluar dari pengawasan

**Sumber:** [ExecutionBridge.mqh:415–475](https://github.com/marko1kiro/dirgaEA/blob/844987eea6601379fcb534fd9aac8fe98a71c241/ExecutionBridge.mqh#L415-L475), `535–543`; `AdaptiveSurvivalEA.mq5:1139–1146`.

Setelah timeout >30 detik, status menjadi `TIMEOUT_RECONCILE`. Namun `ReconcilePending` hanya memproses PENDING/PARTIAL; panggilan berikutnya langsung berhenti. `ExecuteIntent` juga hanya memblokir dua status itu, bukan TIMEOUT. Lease tidak di-heartbeat. Pemeriksaan exposure masih ada, tetapi bukan bukti bahwa request ambigu sebelumnya definitif tidak akan terisi.

**Perbaikan:** timeout harus tetap memblokir entry dan terus merekonsiliasi order/deal/posisi sampai hasil definitif. Jangan samakan “tidak terlihat sekarang” dengan “ditolak”. Pertahankan kepemilikan yang aman selama outcome belum pasti dan sediakan prosedur recovery restart.

**Tes:** PLACED → timeout → history terlambat → fill; tidak boleh ada request entry kedua selama ketidakpastian. **P07.**

### F06 — Rasio ATR berubah skala sebelum klasifikasi

**Sumber:** [MarketBrain.mqh:184–193](https://github.com/marko1kiro/dirgaEA/blob/844987eea6601379fcb534fd9aac8fe98a71c241/MarketBrain.mqh#L184-L193), `476–507`, `534–539`.

Engine membuat `levelScore = clamp(ratio / 2, 0, 1)`. Caller mengirim skor itu ke classifier yang membutuhkan rasio ATR mentah dengan ambang 0,7 / 1,5 / 2,0.

| Rasio ATR mentah | Input classifier aktual | Kandidat aktual | Kandidat yang dimaksud ambang |
|---:|---:|---|---|
| 1,0 | 0,5 | LOW | NORMAL |
| 1,5 | 0,75 | NORMAL | HIGH |
| 2,0 | 1,0 | NORMAL | EXTREME |
| 4,0 | 1,0 | NORMAL | EXTREME |

Karena input maksimum 1, **HIGH maupun EXTREME tidak dapat dipilih oleh classifier melalui pipeline ini**. Persistence/dwell tidak memperbaiki salah skala. Level tersebut dipakai dalam regime fusion, bukan hanya tampilan.

**Perbaikan:** teruskan rasio mentah, misalnya nilai `trace.atrRatio` yang telah dihitung, dan pertahankan skor normalisasi terpisah untuk diagnostik.

**Tes:** engine → classifier → fusion, termasuk rasio ekstrem dan dwell. Jangan hanya menguji classifier secara terpisah. **P01.**

### F07 — Risiko disetujui sebelum SL final dibulatkan

**Sumber:** [AdaptiveSurvivalEA.mq5:1054–1091](https://github.com/marko1kiro/dirgaEA/blob/844987eea6601379fcb534fd9aac8fe98a71c241/AdaptiveSurvivalEA.mq5#L1054-L1091); `ExecutionBridge.mqh:186–205,550–579`; `ExecutionSafety.mqh:158–175`.

Sizing memakai SL kandidat mentah. Saat mengirim, BUY SL di-floor dan SELL SL di-ceil ke tick grid, menjauh dari entry, tanpa menghitung ulang volume/risiko. `OrderCheck` sebelumnya memakai pembulatan nearest, sehingga request yang diperiksa juga belum tentu identik dengan yang dikirim.

**Contoh sintetis:** equity 10.000, input risk=hard cap 0,8%, entry 100, SL 99,86, tick 0,1, nilai 100 per unit harga per lot, step 0,01. Volume 5,71 memberi risiko awal sekitar **0,7994%**. SL final 99,8 menaikkan risiko harga menjadi **1,142%**, dengan asumsi batas broker dan margin lainnya mengizinkan request.

**Perbaikan:** bentuk satu request final: normalisasi SL/TP → hitung sizing dan risiko → quality/preflight/OrderCheck → kirim nilai yang sama. Pisahkan cadangan komisi/slippage; `RiskEngine` sendiri menyatakan risiko harga-ke-SL tidak termasuk biaya.

**Tes:** tick size ≠ point, harga di antara grid, volume minimum dan risk dekat hard cap. **P09.**

### F08 — Range dan breakout merupakan jalur yang belum terhubung

**Sumber:** [AdaptiveSurvivalEA.mq5:72–76](https://github.com/marko1kiro/dirgaEA/blob/844987eea6601379fcb534fd9aac8fe98a71c241/AdaptiveSurvivalEA.mq5#L72-L76), `987–1120`.

Objek B11/B12 dideklarasikan, tetapi alur M15 hanya memberi regime/bar ke B07 trend. Hanya `b07_last_candidate` mencapai quality/risk/execution. Artinya keberadaan file range/breakout belum berarti fitur tersebut operasional.

**Perbaikan:** bila tiga strategi memang dimaksudkan aktif, sambungkan melalui pemilih kandidat yang menjamin maksimal satu dispatch. Jika sengaja trend-only, dokumentasikan dan tampilkan status modul disabled, bukan memberi kesan ketiganya aktif.

**Tes:** sinyal range/breakout mencapai pemilih kandidat dan quality gate; tidak ada dispatch ganda.

### F09 — Break–retest memakai acceptance lama; metrik tidak mengikuti entry final

**Sumber:** [TrendStrategy.mqh:693–767](https://github.com/marko1kiro/dirgaEA/blob/844987eea6601379fcb534fd9aac8fe98a71c241/TrendStrategy.mqh#L693-L767), `497–538`; `AdaptiveSurvivalEA.mq5:1017–1018,1054–1074`.

Setelah bar terkini mengonfirmasi retest, evaluator mencari **bar pertama sesudah break** yang close di sisi acceptance. Bar itu bisa lebih tua daripada retest. Entry, timestamp, RR dan extension kemudian memakai bar lama.

Lebih umum, quality gate dijalankan sebelum quote final; entry lalu diganti dengan harga live untuk sizing/send, tetapi RR, extension dan spread relatif terhadap stop tidak dihitung ulang. Contoh geometris BUY: entry kandidat 100, SL 99, TP 102 berarti 2R; entry final 100,8 dengan level yang sama berarti hanya 0,67R.

**Perbaikan:** simpan bar yang benar-benar memicu retest beserta availability time. Hitung ulang metrik directional dan quality pada quote/level final; tolak target yang sudah berada pada sisi salah. Dua pemeriksaan drift saat ini membandingkan harga dari snapshot yang sama, sehingga tidak mendeteksi perubahan quote eksternal.

**Tes:** break → continuation → retest terlambat; quote berubah sebelum kirim; TP terlewati. Bedakan kontrol lokal ini dari `DeviationPoints` broker, yang tetap disetel tetapi efektivitasnya bergantung execution mode.

### F10 — Spread spike mengubah baseline pemeriksaannya sendiri

**Sumber:** [AdaptiveSurvivalEA.mq5:1047–1077](https://github.com/marko1kiro/dirgaEA/blob/844987eea6601379fcb534fd9aac8fe98a71c241/AdaptiveSurvivalEA.mq5#L1047-L1077); `ExecutionSafety.mqh:82–94,128–136`.

Sample spread ditambahkan sebelum validasi, bertentangan dengan kontrak helper. Contoh history `[5,5,5,30,30]` points dan current 30: median historis 5 memberi rasio 6, seharusnya ditolak. Setelah current dimasukkan, upper median menjadi 30 dan rasio turun ke 1. Semua angka masih di bawah ceiling default 35, jadi ceiling tidak menutup contoh ini.

Sampling juga hanya terjadi ketika kandidat sudah mencapai tahap eksekusi, bukan sekali per tick seperti komentar API.

**Perbaikan:** tetapkan cadence sampling; bandingkan terhadap history sebelum current ditambahkan, lalu append tepat sekali secara konsisten. **Tes P08.**

### F11 — Swing baru berhenti masuk setelah kapasitas penuh

**Sumber:** [TrendStrategy.mqh:311–342](https://github.com/marko1kiro/dirgaEA/blob/844987eea6601379fcb534fd9aac8fe98a71c241/TrendStrategy.mqh#L311-L342), kapasitas `30`, history bar `864–884`.

Penambahan swing hanya berjalan bila count <256. Tidak ada pembuangan swing tertua seperti pada buffer bar. Setelah kapasitas tercapai, pivot baru tidak masuk dan logika bergantung pada struktur yang semakin lama.

**Perbaikan:** buffer FIFO/ring dengan pembaruan referensi pending break/deduplikasi yang konsisten.

**Tes:** >256 pivot; kapasitas tetap terbatas tetapi timestamp swing terbaru terus maju.

### F12 — Initial SL perlu identitas dan pemulihan yang konsisten

**Sumber:** [AdaptiveSurvivalEA.mq5:867–880](https://github.com/marko1kiro/dirgaEA/blob/844987eea6601379fcb534fd9aac8fe98a71c241/AdaptiveSurvivalEA.mq5#L867-L880), `1166–1217`; `PositionManager.mqh:100–109`.

Metadata dibuat dengan position ticket, tetapi dihapus memakai position identifier. Pada setiap exit deal, termasuk partial close, cleanup dilakukan tanpa membuktikan seluruh posisi sudah selesai. Bila key terhapus sementara posisi tersisa, tick berikutnya menyimpan SL yang mungkin sudah ditrailing sebagai *initial* SL; basis 1R berubah.

Bila posisi EA ditemukan dengan SL=0, fallback hanya menghitung dan menyimpan angka ATR secara internal. Angka itu **tidak memasang stop broker**. Ini adalah celah pemulihan posisi tanpa SL, bukan bukti bahwa setiap entry normal dikirim tanpa stop.

**Perbaikan:** identitas stabil dengan namespace akun/symbol/magic; persist initial risk saat fill terkonfirmasi; cleanup setelah full close terverifikasi. Untuk posisi tanpa SL, jalankan kebijakan proteksi/exit yang eksplisit dan terkonfirmasi.

**Tes:** partial close dengan posisi sisa; restart setelah trailing; ticket berbeda dari identifier; posisi SL=0.

## 4. Catatan tambahan — tidak dihitung sebagai temuan utama

- **Range TP salah sisi, saat ini dormant:** `RangeStrategy.mqh:97–156` dapat menghasilkan kandidat BUY yang close di atas rangeHigh tetapi TP tetap rangeHigh, atau SELL simetris. `MathAbs` membuat reward tetap positif. Namun RR pada contoh sweep ini berada di bawah 1 sehingga quality gate saat ini memberikan skor RR nol; jangan menyebutnya bukti order buruk pasti lolos. Perbaiki geometri sebelum B11 disambungkan.
- **Epoch dan waktu tersedia:** B07 mereset flags tetapi dapat memakai kembali swing pra-epoch (`245–275,364–418,897–904`). Kontrak apakah struktur lama boleh dibawa perlu dipertegas. Field `h1AvailableAt` diisi waktu buka bar H1 sumber, bukan waktu hasil benar-benar tersedia; belum saya jadikan bukti entry lookahead karena caller memakai closed-bar freshness gate.
- **Urutan management:** `ManageOpenPositions()` dipanggil sebelum update H1 pada `OnTick`, berlawanan dengan komentar “AFTER H1 update”. Pada tick pertama jam baru, exit berdasarkan regime memakai hasil sebelumnya; update baru baru memengaruhi management pada tick berikutnya. Data ATR yang tidak tersedia juga menunda seluruh management, termasuk regime exit.
- **Operasional:** README hanya judul. Tambahkan setup broker/symbol/account mode, parameter risiko, mode strategi aktif, dependency tes, pemisahan native versus model tests, prosedur recovery, serta cara memverifikasi source/EX5. Jangan jadikan checklist rencana yang belum diperbarui sebagai bukti pekerjaan selesai atau belum selesai.

## 5. Bagian yang sudah baik

- Arsitektur modular memisahkan sinyal, regime, risk, quality, dan eksekusi.
- Sizing memakai `OrderCalcProfit`/`OrderCalcMargin`, bukan asumsi pip value universal; volume dibatasi grid dan cap.
- Ada pemeriksaan closed H1 freshness, simbol/magic, exposure ulang setelah lock, absolute spread ceiling, `OrderCheck`, dan retcode perdagangan.
- Pemeriksaan pivot/bar yang ditinjau menunjukkan penggunaan bar selesai dan konfirmasi kanan; tidak ditemukan bukti entry sebelum konfirmasi tersebut hanya dari pola pivot yang ditinjau.
- Suite regresi Python cukup besar sebagai fondasi. Masalahnya adalah kesenjangan antara model, wiring native, dan jalur broker—bukan bahwa semua tes tidak berguna.

## 6. Urutan perbaikan dan syarat audit ulang

1. **Pengaman modal dahulu:** F01–F05 dan F07. Tambahkan tes yang gagal pada commit ini sebelum mengubah implementasi.
2. **Benarkan keputusan sinyal:** F06 dan F09; tangani F10–F12. Jangan mengaktifkan range/breakout sebelum geometri dan pemilih kandidat aman.
3. **Verifikasi native:** compile ulang commit perbaikan di MetaEditor; simpan build/version, log error/warning, serta hash source dan EX5.
4. **Uji integrasi terisolasi:** multi-instance, restart/rollover, disconnected/delayed history, partial fill/close, calendar unavailable/cache transitions, BUY/SELL BE/trailing, tick-grid berbeda, dan operasi >256 swing. Gunakan harness/demo untuk keadaan yang tidak dapat direproduksi memadai oleh Strategy Tester.
5. **Baru validasi strategi:** real-tick backtest dengan biaya/spread realistis, out-of-sample/walk-forward, lalu forward demo broker target. Belum ada dasar dari audit ini untuk menetapkan profit factor, win rate, atau drawdown yang dapat diharapkan.

**Syarat menutup temuan:** tes regresi mereproduksi bug lama, lulus pada perbaikan, dan jalur native terkait memberikan bukti hasil yang sama. Hasil “518 passed” saja belum memenuhi syarat tersebut.

---

## Lampiran: reproduksibilitas

Arsip sumber: `dirgaEA-844987e.zip`  
SHA-256: `00883c89ed1bea5939ff588c323371034b283d5210bf8e8bb6f3940c76e4d6d3`

Berkas pendukung:
- `pytest-current.log` — output suite repo saat audit.
- `tests-review-current.md` — cakupan tes dan keterbatasan native.
- `counterexamples.json` — sembilan kasus logika, observasi, dan perilaku aman yang diharapkan.
- `dirga_audit_probes.py` — skrip counterexample; membaca arsip tanpa mengubah source.
- `source-checksums-current.sha256` — checksum 19 file MQL utama.

Reproduksi suite: ekstrak arsip lengkap, siapkan Python/pytest, jalankan `python -m pytest -ra -q` dari root repo. Reproduksi counterexample: `python3 dirga_audit_probes.py dirgaEA-844987e.zip counterexamples.json`. Script tambahan hanya memverifikasi counterexample pada sumber yang diaudit; hasilnya tidak menggantikan tes perbaikan atau eksekusi MetaTrader.
