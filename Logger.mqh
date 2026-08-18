#ifndef ADAPTIVE_SURVIVAL_EA_LOGGER_MQH
#define ADAPTIVE_SURVIVAL_EA_LOGGER_MQH

#include "Config.mqh"

void LogDebug(const string event_name, const string message)
{
   if(DebugMode)
      PrintFormat("[AdaptiveSurvivalEA][%s] %s", event_name, message);
}

void LogWarning(const string event_name, const string message)
{
   PrintFormat("[AdaptiveSurvivalEA][WARNING][%s] %s", event_name, message);
}

void LogError(const string event_name, const string message)
{
   PrintFormat("[AdaptiveSurvivalEA][ERROR][%s] %s", event_name, message);
}

#endif
