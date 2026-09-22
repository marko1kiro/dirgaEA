//+------------------------------------------------------------------+
//| EA_StatusReporter.mqh                                            |
//| Protokol dukungan proaktif EA <-> MT5 MCP Server                 |
//|                                                                  |
//| CARA PAKAI (nanti saat coding EA dilanjut):                      |
//|   1. Copy file ini ke MQL5/Include/                              |
//|   2. Di EA utama:  #include <EA_StatusReporter.mqh>               |
//|   3. Di OnTick() (atau tiap 60 detik via timer):                 |
//|        ReportEAStatus("AdaptiveSurvivalEA", InpMagic);            |
//|        PollEACommand("AdaptiveSurvivalEA");                       |
//|                                                                  |
//| File yang dipakai:                                               |
//|   MQL5/Files/EA_Status/<nama>.json  (ditulis EA, dibaca MCP)     |
//|   MQL5/Files/EA_Cmd/<nama>.json     (ditulis MCP, dibaca EA)     |
//+------------------------------------------------------------------+
#property copyright "MT5 Pro MCP"
#property version   "1.00"

//--- panggil tiap tick (ringan: tulis max 1x per 5 detik) atau tiap timer 60 dtk
void ReportEAStatus(const string ea_name, const long magic,
                    const string state,          // RUNNING | BLOCKED | PAUSED | ERROR
                    const string blocked_reasons,// dipisah ';' , kosong bila tidak ada
                    const string last_error,
                    const string build_sha,
                    const double daily_pnl = 0.0,
                    const int daily_trades = 0)
{
   static datetime last_write = 0;
   if(TimeCurrent() - last_write < 5) return;
   last_write = TimeCurrent();

   // NOTE: daily_pnl/daily_trades optional trailing params — wired from the
   // EA ledger (daily_net_pnl / daily_trade_count) by the caller when available.
   // JSON key names/format unchanged.

   int positions = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk > 0 && PositionGetInteger(POSITION_MAGIC) == magic) positions++;
   }

   string json = StringFormat(
      "{\n"
      "  \"ea\": \"%s\",\n"
      "  \"time\": \"%s\",\n"
      "  \"state\": \"%s\",\n"
      "  \"blocked_reasons\": \"%s\",\n"
      "  \"account\": {\"balance\": %.2f, \"equity\": %.2f, \"currency\": \"%s\"},\n"
      "  \"daily\": {\"pnl\": %.2f, \"trades\": %d},\n"
      "  \"positions\": %d,\n"
      "  \"last_error\": \"%s\",\n"
      "  \"build\": \"%s\"\n"
      "}",
      ea_name,
      TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
      state, blocked_reasons,
      AccountInfoDouble(ACCOUNT_BALANCE), AccountInfoDouble(ACCOUNT_EQUITY),
      AccountInfoString(ACCOUNT_CURRENCY),
      daily_pnl, daily_trades,
      positions,
      last_error, build_sha);

   string dir = "EA_Status";
   FolderCreate(dir); // pastikan folder ada (diabaikan bila sudah ada)
   // FileOpen dengan FILE_COMMON tidak dipakai; path relatif ke MQL5/Files
   int h = FileOpen(dir + "\\" + ea_name + ".json", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h != INVALID_HANDLE)
   {
      FileWriteString(h, json);
      FileClose(h);
   }
}

//--- panggil tiap tick; mengeksekusi perintah dari MCP bila ada yang baru
//--- return: "" bila tidak ada perintah baru, atau nama command yang dieksekusi
string PollEACommand(const string ea_name)
{
   string path = "EA_Cmd\\" + ea_name + ".json";
   if(!FileIsExist(path)) return "";

   int h = FileOpen(path, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE) return "";
   string content = "";
   while(!FileIsEnding(h)) content += FileReadString(h);
   FileClose(h);

   // parse minimal tanpa JSON lib: cari "command":"X" dan "acknowledged":false
   if(StringFind(content, "\"acknowledged\": false") < 0 &&
      StringFind(content, "\"acknowledged\":false") < 0)
      return ""; // sudah di-acknowledge sebelumnya

   string cmd = "";
   int p1 = StringFind(content, "\"command\"");
   if(p1 >= 0)
   {
      int q1 = StringFind(content, "\"", p1 + 11);
      int q2 = StringFind(content, "\"", q1 + 1);
      if(q1 > 0 && q2 > q1) cmd = StringSubstr(content, q1 + 1, q2 - q1 - 1);
   }
   if(cmd == "") return "";

   // tandai acknowledged agar tidak dieksekusi dua kali
   string acked = content;
   StringReplace(acked, "\"acknowledged\": false", "\"acknowledged\": true");
   StringReplace(acked, "\"acknowledged\":false", "\"acknowledged\":true");
   int hw = FileOpen(path, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(hw != INVALID_HANDLE) { FileWriteString(hw, acked); FileClose(hw); }

   // NOTE: eksekusi PAUSE/RESUME/FLATTEN_ALL/RELOAD_INPUTS diimplementasikan
   // di EA utama (set flag global / tutup posisi). File ini hanya polling.
   Print("[EA_Cmd] perintah diterima: ", cmd);
   return cmd;
}
//+------------------------------------------------------------------+
