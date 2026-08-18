#ifndef ADAPTIVE_SURVIVAL_EA_BROKER_ENVIRONMENT_MQH
#define ADAPTIVE_SURVIVAL_EA_BROKER_ENVIRONMENT_MQH

#include "Logger.mqh"

struct BrokerEnvironment
{
   string symbol;
   double point;
   int digits;
   double tickSize;
   double tickValue;
   double contractSize;
   double volumeMin;
   double volumeMax;
   double volumeStep;
   int stopsLevel;
   int freezeLevel;
   ENUM_SYMBOL_TRADE_MODE symbolTradeMode;

   double balance;
   double equity;
   double margin;
   double freeMargin;
   string accountCurrency;
   long leverage;
   ENUM_ACCOUNT_MARGIN_MODE marginMode;

   bool terminalTradeAllowed;
   bool mqlTradeAllowed;
   bool accountTradeAllowed;
   bool accountExpertAllowed;
   bool symbolSynchronized;
   bool sessionOpen;
   bool quoteFresh;
   bool environmentCompatible;
   bool tradeReady;
   MqlTick tick;
};

bool ReadSymbolDouble(const string symbol,
                      const ENUM_SYMBOL_INFO_DOUBLE property,
                      double &value,
                      const string propertyName)
{
   ResetLastError();
   if(SymbolInfoDouble(symbol, property, value))
      return true;

   LogError("ENVIRONMENT_READ_FAILED",
            StringFormat("%s unavailable; error=%d", propertyName, GetLastError()));
   return false;
}

bool ReadSymbolInteger(const string symbol,
                       const ENUM_SYMBOL_INFO_INTEGER property,
                       long &value,
                       const string propertyName)
{
   ResetLastError();
   if(SymbolInfoInteger(symbol, property, value))
      return true;

   LogError("ENVIRONMENT_READ_FAILED",
            StringFormat("%s unavailable; error=%d", propertyName, GetLastError()));
   return false;
}

bool MatchTradeSessionDay(const string symbol,
                          const ENUM_DAY_OF_WEEK day,
                          const int currentTimeOfDay,
                          const bool previousDay,
                          const datetime serverTime,
                          const bool logDiagnostics,
                          bool &foundSession)
{
   datetime sessionFrom = 0;
   datetime sessionTo = 0;
   for(uint index = 0; SymbolInfoSessionTrade(symbol, day, index, sessionFrom, sessionTo); index++)
   {
      foundSession = true;
      const int secondsFrom = (int)sessionFrom;
      const int secondsTo = (int)sessionTo;
      bool matched = false;

      if(secondsFrom <= secondsTo)
         matched = !previousDay && currentTimeOfDay >= secondsFrom && currentTimeOfDay < secondsTo;
      else if(previousDay)
         matched = currentTimeOfDay < secondsTo;
      else
         matched = currentTimeOfDay >= secondsFrom;

      if(logDiagnostics)
      {
         LogDebug("SESSION_DIAGNOSTIC",
                  StringFormat("server_time=%s day_of_week=%d session_index=%u from=%s(%d) to=%s(%d) current_time_of_day=%d previous_day=%s matched_session=%s",
                               TimeToString(serverTime, TIME_DATE | TIME_SECONDS), day, index,
                               TimeToString(sessionFrom, TIME_SECONDS), secondsFrom,
                               TimeToString(sessionTo, TIME_SECONDS), secondsTo,
                               currentTimeOfDay, previousDay ? "true" : "false",
                               matched ? "true" : "false"));
      }

      if(matched)
         return true;
   }

   return false;
}

bool IsCurrentTradeSessionOpen(const string symbol)
{
   const datetime serverTimeValue = TimeTradeServer();
   if(serverTimeValue <= 0)
      return false;

   MqlDateTime serverTime;
   TimeToStruct(serverTimeValue, serverTime);
   const ENUM_DAY_OF_WEEK currentDay = (ENUM_DAY_OF_WEEK)serverTime.day_of_week;
   const ENUM_DAY_OF_WEEK previousDay =
      (ENUM_DAY_OF_WEEK)((serverTime.day_of_week + 6) % 7);
   const int currentTimeOfDay =
      serverTime.hour * 3600 + serverTime.min * 60 + serverTime.sec;
   bool foundSession = false;
   static datetime lastDiagnosticMinute = 0;
   const datetime diagnosticMinute = serverTimeValue - serverTimeValue % 60;
   const bool logDiagnostics = DebugMode && diagnosticMinute != lastDiagnosticMinute;
   if(logDiagnostics)
      lastDiagnosticMinute = diagnosticMinute;

   if(MatchTradeSessionDay(symbol, currentDay, currentTimeOfDay, false,
                           serverTimeValue, logDiagnostics, foundSession))
      return true;

   if(MatchTradeSessionDay(symbol, previousDay, currentTimeOfDay, true,
                           serverTimeValue, logDiagnostics, foundSession))
      return true;

   if(DebugMode && !foundSession)
      LogWarning("SESSION_DIAGNOSTIC",
                 StringFormat("server_time=%s day_of_week=%d no_trade_sessions",
                              TimeToString(serverTimeValue, TIME_DATE | TIME_SECONDS), currentDay));
   return false;
}

bool RefreshEnvironmentStatus(BrokerEnvironment &environment)
{
   environment.terminalTradeAllowed = (bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED);
   environment.mqlTradeAllowed = (bool)MQLInfoInteger(MQL_TRADE_ALLOWED);
   environment.accountTradeAllowed = (bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED);
   environment.accountExpertAllowed = (bool)AccountInfoInteger(ACCOUNT_TRADE_EXPERT);
   environment.symbolSynchronized = SymbolIsSynchronized(environment.symbol);
   environment.sessionOpen = IsCurrentTradeSessionOpen(environment.symbol);

   ResetLastError();
   if(!SymbolInfoTick(environment.symbol, environment.tick))
   {
      LogWarning("ENVIRONMENT_NOT_READY",
                 StringFormat("Latest tick unavailable; error=%d", GetLastError()));
      environment.quoteFresh = false;
   }
   else
   {
      const datetime serverTime = TimeTradeServer();
      environment.quoteFresh = environment.tick.time > 0 && serverTime > 0 &&
                               serverTime >= environment.tick.time &&
                               serverTime - environment.tick.time <= 60;
   }

   environment.environmentCompatible =
      environment.marginMode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING &&
      environment.symbolTradeMode != SYMBOL_TRADE_MODE_DISABLED;

   environment.tradeReady =
      environment.environmentCompatible &&
      environment.terminalTradeAllowed &&
      environment.mqlTradeAllowed &&
      environment.accountTradeAllowed &&
      environment.accountExpertAllowed &&
      environment.symbolSynchronized &&
      environment.sessionOpen &&
      environment.quoteFresh;

   return environment.tradeReady;
}

bool RefreshAccountSnapshot(BrokerEnvironment &environment)
{
   environment.balance = AccountInfoDouble(ACCOUNT_BALANCE);
   environment.equity = AccountInfoDouble(ACCOUNT_EQUITY);
   environment.margin = AccountInfoDouble(ACCOUNT_MARGIN);
   environment.freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);

   if(!MathIsValidNumber(environment.balance) ||
      !MathIsValidNumber(environment.equity) ||
      !MathIsValidNumber(environment.margin) ||
      !MathIsValidNumber(environment.freeMargin) ||
      environment.balance < 0.0 || environment.equity <= 0.0 ||
      environment.margin < 0.0 || environment.freeMargin < 0.0)
   {
      LogError("ACCOUNT_SNAPSHOT_INVALID", "Live account values are invalid");
      return false;
   }

   return true;
}

bool LoadBrokerEnvironment(BrokerEnvironment &environment)
{
   environment.symbol = _Symbol;
   if(environment.symbol == "")
   {
      LogError("ENVIRONMENT_INVALID", "Chart symbol is empty");
      return false;
   }

   long integerValue = 0;
   if(!ReadSymbolDouble(environment.symbol, SYMBOL_POINT, environment.point, "SYMBOL_POINT") ||
      !ReadSymbolInteger(environment.symbol, SYMBOL_DIGITS, integerValue, "SYMBOL_DIGITS"))
      return false;
   environment.digits = (int)integerValue;

   if(!ReadSymbolDouble(environment.symbol, SYMBOL_TRADE_TICK_SIZE, environment.tickSize, "SYMBOL_TRADE_TICK_SIZE") ||
      !ReadSymbolDouble(environment.symbol, SYMBOL_TRADE_TICK_VALUE, environment.tickValue, "SYMBOL_TRADE_TICK_VALUE") ||
      !ReadSymbolDouble(environment.symbol, SYMBOL_TRADE_CONTRACT_SIZE, environment.contractSize, "SYMBOL_TRADE_CONTRACT_SIZE") ||
      !ReadSymbolDouble(environment.symbol, SYMBOL_VOLUME_MIN, environment.volumeMin, "SYMBOL_VOLUME_MIN") ||
      !ReadSymbolDouble(environment.symbol, SYMBOL_VOLUME_MAX, environment.volumeMax, "SYMBOL_VOLUME_MAX") ||
      !ReadSymbolDouble(environment.symbol, SYMBOL_VOLUME_STEP, environment.volumeStep, "SYMBOL_VOLUME_STEP") ||
      !ReadSymbolInteger(environment.symbol, SYMBOL_TRADE_STOPS_LEVEL, integerValue, "SYMBOL_TRADE_STOPS_LEVEL"))
      return false;
   environment.stopsLevel = (int)integerValue;

   if(!ReadSymbolInteger(environment.symbol, SYMBOL_TRADE_FREEZE_LEVEL, integerValue, "SYMBOL_TRADE_FREEZE_LEVEL"))
      return false;
   environment.freezeLevel = (int)integerValue;

   if(!ReadSymbolInteger(environment.symbol, SYMBOL_TRADE_MODE, integerValue, "SYMBOL_TRADE_MODE"))
      return false;
   environment.symbolTradeMode = (ENUM_SYMBOL_TRADE_MODE)integerValue;

   if(environment.point <= 0.0 || environment.digits < 0 || environment.tickSize <= 0.0 ||
      environment.tickValue <= 0.0 || environment.contractSize <= 0.0 ||
      environment.volumeMin <= 0.0 || environment.volumeMax < environment.volumeMin ||
      environment.volumeStep <= 0.0 || environment.stopsLevel < 0 || environment.freezeLevel < 0)
   {
      LogError("ENVIRONMENT_INVALID", "Critical symbol specification is invalid");
      return false;
   }

   environment.balance = AccountInfoDouble(ACCOUNT_BALANCE);
   environment.equity = AccountInfoDouble(ACCOUNT_EQUITY);
   environment.margin = AccountInfoDouble(ACCOUNT_MARGIN);
   environment.freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   environment.accountCurrency = AccountInfoString(ACCOUNT_CURRENCY);
   environment.leverage = AccountInfoInteger(ACCOUNT_LEVERAGE);
   environment.marginMode = (ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE);

   if(environment.balance < 0.0 || environment.equity < 0.0 || environment.margin < 0.0 ||
      environment.accountCurrency == "" || environment.leverage <= 0)
   {
      LogError("ENVIRONMENT_INVALID", "Critical account specification is invalid");
      return false;
   }

   RefreshEnvironmentStatus(environment);
   return true;
}

void LogBrokerEnvironment(const BrokerEnvironment &environment)
{
   LogDebug("ENVIRONMENT_SYMBOL",
            StringFormat("symbol=%s digits=%d point=%.*f tick_size=%.*f tick_value=%.8f contract=%.2f volume_min=%.8f volume_max=%.8f volume_step=%.8f stops=%d freeze=%d trade_mode=%d",
                         environment.symbol, environment.digits, environment.digits, environment.point,
                         environment.digits, environment.tickSize, environment.tickValue,
                         environment.contractSize, environment.volumeMin, environment.volumeMax,
                         environment.volumeStep, environment.stopsLevel, environment.freezeLevel,
                         environment.symbolTradeMode));
   LogDebug("ENVIRONMENT_ACCOUNT",
            StringFormat("currency=%s balance=%.2f equity=%.2f margin=%.2f free_margin=%.2f leverage=%d margin_mode=%d",
                         environment.accountCurrency, environment.balance, environment.equity,
                         environment.margin, environment.freeMargin, environment.leverage,
                         environment.marginMode));
   LogDebug("ENVIRONMENT_STATUS",
            StringFormat("compatible=%s trade_ready=%s terminal=%s mql=%s account=%s expert=%s synchronized=%s session=%s quote_fresh=%s",
                         environment.environmentCompatible ? "true" : "false",
                         environment.tradeReady ? "true" : "false",
                         environment.terminalTradeAllowed ? "true" : "false",
                         environment.mqlTradeAllowed ? "true" : "false",
                         environment.accountTradeAllowed ? "true" : "false",
                         environment.accountExpertAllowed ? "true" : "false",
                         environment.symbolSynchronized ? "true" : "false",
                         environment.sessionOpen ? "true" : "false",
                         environment.quoteFresh ? "true" : "false"));

   if(environment.marginMode != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
      LogWarning("ENVIRONMENT_INCOMPATIBLE", "Account margin mode is not hedging; trading unsupported");
   if(!environment.terminalTradeAllowed || !environment.mqlTradeAllowed ||
      !environment.accountTradeAllowed || !environment.accountExpertAllowed)
      LogWarning("ENVIRONMENT_NOT_READY", "Trade permission is currently disabled");
}

#endif
