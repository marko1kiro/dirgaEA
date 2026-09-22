//+------------------------------------------------------------------+
//| EA_CalendarWriter.mqh                                            |
//| Menulis kalender ekonomi (CalendarValueHistory asli terminal)    |
//| ke MQL5/Files/Calendar/events.json untuk dibaca MT5 MCP Server.  |
//|                                                                  |
//| KONTRAK JSON (dibaca tool news_calendar di server.py):           |
//| {                                                                |
//|   "generated_at": "2026.09.22 06:30",                            |
//|   "source": "MQL5-CalendarValueHistory",                         |
//|   "events": [                                                    |
//|     {"time":"2026.09.23 19:30","country":"US","currency":"USD",   |
//|      "name":"FOMC ...","importance":3,"forecast":"","previous":""}|
//|   ]                                                              |
//| }                                                                |
//| importance: 1=low, 2=medium, 3=high                              |
//|                                                                  |
//| CARA PAKAI:                                                      |
//|   #include <EA_CalendarWriter.mqh>                               |
//|   // di OnTimer() tiap 3600 detik (atau OnTick bila belum ada timer): |
//|   WriteCalendarFile(7, 2);  // 7 hari ke depan, min medium        |
//|                                                                  |
//| CATATAN: di Strategy Tester, CalendarValueHistory umumnya        |
//| mengembalikan 0 (tidak ada kalender di tester) → file ditulis    |
//| dengan events:[] — itu kondisi normal, bukan error.              |
//+------------------------------------------------------------------+
#property copyright "MT5 Pro MCP"
#property version   "1.00"

//--- escape minimal untuk JSON string
string CalJsonEscape(const string s)
{
   string r = s;
   StringReplace(r, "\\", "\\\\");
   StringReplace(r, "\"", "'");
   StringReplace(r, "\r", " ");
   StringReplace(r, "\n", " ");
   return r;
}

//--- tulis file kalender; throttle max 1x per jam (waktu server)
void WriteCalendarFile(const int days_ahead = 7, const int min_importance = 2)
{
   static datetime last_write = 0;
   if(TimeCurrent() - last_write < 3600) return;
   last_write = TimeCurrent();

   string events_json = "";
   int    event_count = 0;
   ulong  seen_ids[];
   ArrayResize(seen_ids, 0);

   MqlCalendarValue values[];
   datetime from = TimeCurrent();
   datetime to   = from + (datetime)days_ahead * 86400;
   int n = CalendarValueHistory(values, from, to, NULL, NULL);

   if(n > 0)
   {
      for(int i = 0; i < n; i++)
      {
         ulong eid = values[i].event_id;
         bool seen = false;
         for(int k = 0; k < ArraySize(seen_ids); k++)
            if(seen_ids[k] == eid) { seen = true; break; }
         if(seen) continue;

         MqlCalendarEvent event;
         if(!CalendarEventById(eid, event)) continue;
         int imp = (int)event.importance; // 0=none 1=low 2=medium 3=high
         if(imp < min_importance) continue;

         MqlCalendarCountry country;
         string code = "", currency = "";
         if(CalendarCountryById(event.country_id, country))
         {
            code     = country.code;      // mis. "US"
            currency = country.currency;  // mis. "USD"
         }

         ArrayResize(seen_ids, ArraySize(seen_ids) + 1);
         seen_ids[ArraySize(seen_ids) - 1] = eid;

         if(event_count > 0) events_json += ",";
         events_json += StringFormat(
            "{\"time\":\"%s\",\"country\":\"%s\",\"currency\":\"%s\",\"name\":\"%s\",\"importance\":%d,\"forecast\":\"\",\"previous\":\"\"}",
            TimeToString(values[i].time, TIME_DATE | TIME_MINUTES),
            CalJsonEscape(code), CalJsonEscape(currency),
            CalJsonEscape(event.name), imp);
         event_count++;
      }
   }

   string json = StringFormat(
      "{\"generated_at\":\"%s\",\"source\":\"MQL5-CalendarValueHistory\",\"events\":[%s]}",
      TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES),
      events_json);

   FolderCreate("Calendar");
   int h = FileOpen("Calendar\\events.json", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h != INVALID_HANDLE)
   {
      FileWriteString(h, json);
      FileClose(h);
   }
   else
   {
      Print("[EA_CalendarWriter] gagal menulis Calendar\\events.json, error=", GetLastError());
   }
}
//+------------------------------------------------------------------+
