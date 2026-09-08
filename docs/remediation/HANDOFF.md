# Prompt Handoff — dirgaEA Forensic Audit Remediation

> Salin seluruh dokumen ini sebagai instruksi awal untuk agent Tasklet berikutnya. Dokumen yang sama disimpan pada branch WIP agar konteks tidak bergantung pada akun Tasklet sebelumnya.

## Peran dan mandat

Anda melanjutkan remediation keamanan/kebenaran untuk EA MQL5 **`marko1kiro/dirgaEA`**. Jangan mengulang audit dari nol, jangan mengubah `main` secara langsung, dan jangan merge tanpa persetujuan eksplisit pemilik repo. Fokusnya adalah menuntaskan 12 temuan audit dengan tes regresi, mempertahankan perilaku fail-closed, dan menghasilkan draft PR yang dapat direview.

## Repository dan titik kesinambungan yang wajib dipakai

- Repo: `https://github.com/marko1kiro/dirgaEA.git`
- Baseline audit/upstream: branch `main`, commit **`844987eea6601379fcb534fd9aac8fe98a71c241`**.
- Branch kelanjutan: **`fix/forensic-audit-remediation`**.
- Branch itu adalah WIP yang sengaja dibekukan pada titik terakhir. Clone/fetch branch tersebut; jangan membuat implementasi baru dari `main` dan jangan membuang perubahan WIP.
- Dokumen desain dan audit yang dibutuhkan telah ditambahkan ke `docs/remediation/` pada branch ini.

Contoh awal:

```bash
git clone https://github.com/marko1kiro/dirgaEA.git
cd dirgaEA
git fetch origin fix/forensic-audit-remediation
git checkout fix/forensic-audit-remediation
git status
git diff 844987eea6601379fcb534fd9aac8fe98a71c241...HEAD --stat
```

Sebelum mengedit, catat SHA HEAD branch aktual dan pastikan ancestry-nya berasal dari baseline di atas. Jika SHA/isi berbeda dari dokumen ini, hentikan dan rekonsiliasi dengan pemilik; jangan menebak.

## Status aktual yang diwariskan

Pekerjaan implementasi sebelumnya terhenti setelah sekitar 10,5 menit. **Hanya `ExecutionBridge.mqh` yang sempat diganti**, dari 696 menjadi 422 baris. Tidak ada file sumber lain atau tes baru yang selesai. Perubahan itu adalah kerangka awal untuk:

- lock terminal-global satu nilai dengan generasi CAS;
- journal pending submission persisten;
- state timeout/recovery yang memblokir entry;
- `FinalMarketOrder` dan raw `MqlTradeRequest`;
- direction-aware SL validation;
- raw position management request.

**Branch WIP belum compile-ready.** Jangan menyatakan patch selesai atau aman. Konflik API yang diketahui dan harus ditangani lebih dulu:

1. `ExecutionBridge.mqh` memakai `FinalMarketOrder`, tetapi struct tersebut belum ada di `Types.mqh`.
2. File itu memakai `EXEC_LIFECYCLE_RECOVERY_BLOCKED`, tetapi enum belum ditambah di `Types.mqh`.
3. File itu membaca `PositionManageIntent.direction`, tetapi field tersebut belum ada di `Types.mqh` dan belum diisi `PositionManager.mqh`.
4. `AdaptiveSurvivalEA.mq5` masih memanggil API lama `PrepareMarketOrder(...)` dan `ExecuteIntent(...)`, sedangkan penggantinya pada WIP adalah `BuildFinalMarketOrder(...)` dan `SendFinalMarketOrder(...)`.
5. `ExecutionSafety.mqh` masih menerima `OrderIntent`, membangun ulang request, dan melakukan pembulatan sendiri; ia belum menerima dan memeriksa request final yang sama.
6. `SavePendingJournalWriting()` menggunakan `if(!GlobalVariablesFlush())`; cek signature native MQL5 karena `GlobalVariablesFlush()` dapat bertipe `void` pada target compiler. Perbaiki bila perlu—jangan menebak hasil compile.
7. Immediate `TRADE_RETCODE_DONE` pada `SendFinalMarketOrder` belum langsung membersihkan journal; pastikan rekonsiliasi dan persistensi initial SL mempunyai terminal evidence yang benar.
8. Recovery untuk journal tanpa ticket/correlation unik, persisted initial-SL, dan protection policy untuk posisi `SL==0` belum selesai.
9. `ValidateStopFreeze(..., isModification, ...)` saat ini tidak memakai parameter `isModification`; tinjau kontrak broker/freeze dan jangan klaim semantik yang tidak diimplementasikan.
10. `BuildFinalMarketOrder` belum terhubung ke final-candidate repricing/quality pipeline di EA.

Tes Python baseline sebelum perubahan adalah **518 passed** pada Python 3.12/pytest 9.1.1. Percobaan tes WIP dihentikan oleh batas 110 detik saat sekitar 41%; itu **bukan** hasil lulus/gagal lengkap. Tidak tersedia MetaEditor/MetaTrader di environment sebelumnya, sehingga belum ada compile native, Strategy Tester, broker demo, atau probe terminal-global.

## Temuan yang harus ditutup

1. **F01 Kritis — lock bootstrap/lease race.** Gunakan satu global versioned generation dan hanya CAS untuk mutasi; heartbeat/takeover harus generation-safe. Journal unresolved harus bertahan restart. Terminal-global hanya melindungi satu terminal, bukan lintas VPS.
2. **F02 Tinggi — daily-loss baseline/ledger.** Persist account+broker-day baseline, tangani rollover/restart/cashflow/history failure secara fail-closed, dan hitung streak berdasarkan lifecycle posisi penuh termasuk biaya; partial close tidak boleh dianggap posisi selesai.
3. **F03 Tinggi — news UNKNOWN/cache horizon.** UNKNOWN harus absorbing/fail-closed ketika guard wajib. Cache event+coverage, bukan status waktu; evaluasi ulang state terhadap waktu kini; query/filter currency harus benar.
4. **F04 Tinggi — SELL SL modify masuk aturan BUY.** Tambah arah eksplisit pada intent, verifikasi ticket/symbol/magic/type, normalisasi dan validasi BUY/SELL simetris, kirim raw `TRADE_ACTION_SLTP` dengan `position` ticket.
5. **F05 Tinggi — timeout berhenti direkonsiliasi.** Timeout/recovery tetap unresolved dan memblokir entry, heartbeat/reconcile terus berjalan sampai ada terminal evidence atau prosedur operator eksplisit.
6. **F06 Tinggi — skala klasifikasi volatilitas salah.** Tambah `VolatilityResult.atrRatio`; classifier harus menerima raw ATR/baseline ratio. `levelScore` tetap hanya normalized diagnostic.
7. **F07 Tinggi — risiko dihitung sebelum SL final.** Bentuk satu final normalized request, hitung risk dari request itu, quality/preflight/`OrderCheck` request yang sama, lalu `OrderSend` request yang sama. Jangan ada rekonstruksi/pembulatan kedua.
8. **F08 Sedang — range/breakout tidak terhubung.** Feed B07 sekali sebagai pemilik swing; B11/B12 membaca snapshot yang sama. Arbiter regime-aware menghasilkan maksimum satu kandidat/dispatch.
9. **F09 Tinggi — stale break-retest dan live repricing.** Simpan OHLC/time bar trigger retest nyata; jangan scan acceptance lama. Reprice ke final quote dan hitung ulang geometry, RR, extension, quality. Tolak target/SL salah sisi.
10. **F10 Sedang — spread mencemari median sendiri.** Validasi current spread terhadap history terlebih dulu; append sekali di epilog tiap valid `OnTick`, bukan hanya ketika ada kandidat.
11. **F11 Sedang — swing membeku setelah 256.** Implement FIFO nyata dan incremental single-pivot detection dengan dua right bars; jangan full-rescan yang memasukkan kembali pivot lama. Bersihkan state epoch yang tidak boleh carry over.
12. **F12 Sedang — initial SL identity/recovery.** Key berdasarkan account/symbol/magic/`POSITION_IDENTIFIER`; simpan dari accepted plan/fill; jangan hapus saat partial close; jangan merekonstruksi dari trailing SL. Posisi EA dengan `SL==0` harus mencoba broker protection lalu fail-closed close/retry dan memblokir entry sampai aman.

Scope terkait yang wajib ikut karena diperlukan agar wiring aman: geometri target range salah sisi, epoch carryover, H1 source-vs-availability provenance, serta urutan update H1 sebelum position management dan M15 candidate selection.

## Urutan implementasi yang disarankan

### 1. Stabilkan API dan pulihkan compile-consistency statis

- Periksa diff WIP `ExecutionBridge.mqh` terhadap baseline.
- Tambah/ubah tipe minimal di `Types.mqh`: `FinalMarketOrder`, explicit direction, recovery lifecycle, `atrRatio`, retest trigger evidence, extension/provenance fields.
- Update seluruh declaration/call site secara atomik: `ExecutionBridge`, `ExecutionSafety`, `PositionManager`, dan `AdaptiveSurvivalEA`.
- Jangan mempertahankan API lama hanya supaya source-regex lama lulus jika semantiknya sudah obsolete; update reference tests secara jujur.

### 2. Tuntaskan execution/risk/position safety

- Pastikan CAS absent-key dan `GlobalVariableTime` diuji native sebelum real-account approval.
- Journal: write state first, detail fields, flush, unresolved before send; unknown/corrupt/missing history selalu blocked.
- `OrderCheck` dan `OrderSend` harus menerima object request yang sama.
- Implement initial-stop store dan SL=0 broker recovery/close policy.
- Ubah spread guard menjadi historical-only plus one-per-tick epilogue.

### 3. Guards

- Implement daily-risk persistence/ledger dengan test restart, rollover, cashflow, partial/full lifecycle, fees/commission, history unavailable.
- Refactor news cache menjadi event-time cache dengan coverage bounds dan absorbing UNKNOWN.

### 4. Strategy dan orchestration

- Raw ATR ratio plumbing.
- B07 incremental swing FIFO dan epoch reset/cutoff.
- Record exact break-retest trigger bar.
- Wire B07/B11/B12 with deterministic regime-family arbiter and max-one dispatch.
- Fix range wrong-side target geometry before enabling B11.
- Final candidate builder after immutable quote: directional normalized stop/target, RR/extension recomputation, then quality, risk, safety, send.
- Process fresh H1 before position management; stale/failed H1 suppresses regime flip only, not BE/trailing protection.

### 5. Regression evidence

Add behavioral Python models plus source-contract tests for all findings. At minimum:

- F01 two-actor absent bootstrap, heartbeat-vs-takeover, stale owner failure, restart journal/late fill.
- F02 restart after loss, broker-day rollover, deposits/withdrawals, entry+exit costs, partial close.
- F03 repeated API failure/cache hit, resolve failures, moving CLEAR→LOCK→SHOCK→RECOVERY→CLEAR timeline.
- F04 BUY/SELL boundary and selected ticket direction.
- F05 timeout remains blocked and later reconciles.
- F06 canonical raw ratios and dwell through full pipeline/replay parity.
- F07 tick-size≠point and equality of risk/check/send fields.
- F08 active-regime arbiter, same snapshot, 0-or-1 dispatch.
- F09 retest bar provenance, later non-reemit, live quote worsened RR, target passed rejection.
- F10 history `[5,5,5,30,30]` with current `30` must median `5` and reject before append.
- F11 >276 pivots, bounded 256, newest retained, no reinsertion; fifth bar confirms center pivot.
- F12 partial close retains key, final close deletes, identifier≠ticket, restart after trailing, SL=0 protection/close.

Run the complete suite and preserve exact command, Python/pytest versions, pass/fail counts, and log. Also run compile-oriented static checks, but label them static only.

## Native verification gate

Do not call the remediation complete for real trading until all of the following exist:

- MetaEditor compile of patched source with zero errors; report warnings honestly.
- Terminal build/version and source commit SHA in evidence.
- Two-chart fresh-key CAS probe proving one winner and `GlobalVariableTime` heartbeat semantics.
- Native request/`OrderCheck` probe, especially symbol where tick size differs from point.
- Strategy Tester/demo tests for delayed transactions/history, partial fill/close, position identifier behavior, calendar unavailable/cache transitions, BUY/SELL protective actions, and long-running swing FIFO.

Absence of GitHub Actions is not a passing CI result. If no runner is available, report native verification as pending.

## Deliverable dan GitHub discipline

- Commit in logical groups on `fix/forensic-audit-remediation`.
- Push only that branch.
- Keep/open a **draft PR** into `main`; never merge without explicit instruction.
- PR summary must map changed files/tests to F01–F12.
- State clearly which gates are proven by Python/static evidence and which remain native/demo verification.
- Before handoff completion, provide: branch HEAD SHA, PR URL, changed-file list, full test totals, unresolved items, and exact next action.

## Definition of done

“Done” means each bug has a regression test that fails on baseline and passes on patch; source wiring uses the fixed path; full Python suite passes; static API consistency passes; native compile/probes are either supplied or explicitly still blocking real-account approval; and no unresolved journal/protection state can permit a new order. Merely making old 518 tests pass, adding comments, or satisfying regex assertions is insufficient.
