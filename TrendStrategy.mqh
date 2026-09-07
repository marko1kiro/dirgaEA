//+------------------------------------------------------------------+
//|                                                TrendStrategy.mqh |
//|                                  Copyright 2026, AdaptiveSurvival |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, AdaptiveSurvival"
#property link      "https://www.mql5.com"
#property strict

#include "Types.mqh"

#define B07_ZONE_LO         0.33
#define B07_ZONE_HI         0.66
#define B07_CONTR_DISP      1.5
#define B07_TGT_LOOKBACK    8
#define B07_MOM_LB          3
#define B07_M15_SEC         900
#define B07_IMP_MIN         1.0
#define B07_PB_MIN          0.30
#define B07_PB_MAX          1.5
#define B07_BRK_PEN         0.10
#define B07_RET_TOL         0.20
#define B07_RET_MAX         8
#define B07_STOP_BUF        0.10
#define B07_MIN_STOP        0.5
#define B07_MAX_STOP        3.0
#define B07_MAX_EXT         2.5
#define B07_MOM_MIN_D       0.8

#define B07_MAX_SWINGS      256
#define B07_MAX_BREAKS      128
#define B07_MAX_BARS        512

struct B07_Bar
{
   datetime t;
   double   o;
   double   h;
   double   l;
   double   c;
   datetime avail;
};

struct B07_Swing
{
   datetime bt; // bar time
   datetime ct; // confirm time
   double   p;  // price
   int      k;  // kind: 1 = high, -1 = low
};

class CTrendStrategy
{
private:
   string                  m_symbol;
   ulong                   m_epochId;
   datetime                m_epochStartAvail;
   ENUM_TRADE_DIRECTION    m_epochDir;

   B07_Swing               m_swings[B07_MAX_SWINGS];
   int                     m_swingsCount;

   // Impulse / Pullback state
   datetime                m_iot; // impulse origin time
   double                  m_iop; // impulse origin price
   datetime                m_iet; // impulse end time
   double                  m_iep; // impulse end price
   double                  m_ila; // impulse length atr
   datetime                m_pbt; // pullback pivot time
   double                  m_pbp; // pullback pivot price
   double                  m_pbd; // pullback depth atr
   bool                    m_iprimed;

   // Break / Retest state
   TrendBreakItem          m_pendingBreak;
   bool                    m_hasPendingBreak;
   TrendBreakItem          m_breaks[B07_MAX_BREAKS];
   int                     m_breaksCount;

   // Bar history
   B07_Bar                 m_bars[B07_MAX_BARS];
   int                     m_barsCount;
   datetime                m_lastBarTime;
   datetime                m_lastAvail;
   string                  m_lastCandidateIdentity;

   // H1 state mirror
   RegimeResult            m_h1Regime;
   bool                    m_hasH1Regime;

   // Helper methods
   bool                    IsTrend(ENUM_REGIME_STATE r) const;
   ENUM_TRADE_DIRECTION    RegimeToDir(ENUM_REGIME_STATE r) const;
   double                  SwingLengthAtr(const B07_Swing &a, const B07_Swing &b, double atr) const;
   bool                    IsImpulse(const B07_Swing &a, const B07_Swing &b, ENUM_TRADE_DIRECTION d) const;
   int                     CountBarsBetween(datetime s, datetime e) const;

   void                    CheckEpoch(const RegimeResult &newH1);
   void                    DetectPivots();
   void                    UpdateLegs(double atr, ENUM_TRADE_DIRECTION d);
   void                    AddBreak(const B07_Swing &sw, bool bull, const B07_Bar &bar);
   void                    AdvanceBreakAges();
   void                    CheckRetest(const B07_Bar &bar, double atr);
   bool                    CheckContradiction(const B07_Bar &bar, ENUM_TRADE_DIRECTION d, double atr, double inv);
   double                  GetTargetPrice(double ent, ENUM_TRADE_DIRECTION d, datetime afterTime);

   bool                    EvaluatePullback(TradeCandidate &cand, double atr, datetime now);
   bool                    EvaluateBreakRetest(TradeCandidate &cand, double atr, datetime now);
   bool                    EvaluateMomentum(TradeCandidate &cand, double atr, datetime now);
   string                  FormatCandidateIdentity(const TradeCandidate &cand) const;

   ulong                   Fnv1a64(const uchar &data[]) const;

public:
                           CTrendStrategy(string symbol = "EURUSDm");
                          ~CTrendStrategy();

   void                    Reset();
   void                    SetH1Regime(const RegimeResult &h1);
   bool                    FeedM15Bar(datetime t, double o, double h, double l, double c, datetime avail, double atr, TradeCandidate &outCandidate);
   string                  GetB07D1Hash(const TradeCandidate &cand);
};

//+------------------------------------------------------------------+
//| Constructor                                                      |
//+------------------------------------------------------------------+
CTrendStrategy::CTrendStrategy(string symbol = "EURUSDm")
{
   m_symbol = symbol;
   Reset();
}

//+------------------------------------------------------------------+
//| Destructor                                                       |
//+------------------------------------------------------------------+
CTrendStrategy::~CTrendStrategy()
{
}

//+------------------------------------------------------------------+
//| Reset internal state                                             |
//+------------------------------------------------------------------+
void CTrendStrategy::Reset()
{
   m_epochId = 0;
   m_epochStartAvail = 0;
   m_epochDir = TRADE_DIR_NONE;

   m_swingsCount = 0;
   m_iot = 0;
   m_iop = 0;
   m_iet = 0;
   m_iep = 0;
   m_ila = 0;
   m_pbt = 0;
   m_pbp = 0;
   m_pbd = 0;
   m_iprimed = false;

   m_hasPendingBreak = false;
   m_breaksCount = 0;
   m_barsCount = 0;
   m_lastBarTime = 0;
   m_lastAvail = 0;
   m_lastCandidateIdentity = "";

   m_hasH1Regime = false;
   ZeroMemory(m_h1Regime);
}

//+------------------------------------------------------------------+
//| Helper: Check if regime is trend                                 |
//+------------------------------------------------------------------+
bool CTrendStrategy::IsTrend(ENUM_REGIME_STATE r) const
{
   return (r == REGIME_TREND_BULL || r == REGIME_TREND_BEAR);
}

//+------------------------------------------------------------------+
//| Helper: Regime to Trade Direction                                |
//+------------------------------------------------------------------+
ENUM_TRADE_DIRECTION CTrendStrategy::RegimeToDir(ENUM_REGIME_STATE r) const
{
   if (r == REGIME_TREND_BULL) return TRADE_DIR_BUY;
   if (r == REGIME_TREND_BEAR) return TRADE_DIR_SELL;
   return TRADE_DIR_NONE;
}

//+------------------------------------------------------------------+
//| Helper: Swing length in ATR                                      |
//+------------------------------------------------------------------+
double CTrendStrategy::SwingLengthAtr(const B07_Swing &a, const B07_Swing &b, double atr) const
{
   if (atr <= 0) return 0.0;
   return MathAbs(b.p - a.p) / atr;
}

//+------------------------------------------------------------------+
//| Helper: Is impulse swing pair                                    |
//+------------------------------------------------------------------+
bool CTrendStrategy::IsImpulse(const B07_Swing &a, const B07_Swing &b, ENUM_TRADE_DIRECTION d) const
{
   if (d == TRADE_DIR_BUY)
   {
      return (b.k == 1 && a.k == -1 && b.p > a.p);
   }
   if (d == TRADE_DIR_SELL)
   {
      return (b.k == -1 && a.k == 1 && b.p < a.p);
   }
   return false;
}

//+------------------------------------------------------------------+
//| Helper: Count completed bars in interval                         |
//+------------------------------------------------------------------+
int CTrendStrategy::CountBarsBetween(datetime s, datetime e) const
{
   int cnt = 0;
   for (int i = 0; i < m_barsCount; i++)
   {
      if (s < m_bars[i].avail && m_bars[i].avail <= e)
         cnt++;
   }
   return cnt;
}

//+------------------------------------------------------------------+
//| Set H1 Regime and trigger epoch check                            |
//+------------------------------------------------------------------+
void CTrendStrategy::SetH1Regime(const RegimeResult &h1)
{
   if (m_hasH1Regime)
   {
      CheckEpoch(h1);
   }
   m_h1Regime = h1;
   m_hasH1Regime = true;
}

//+------------------------------------------------------------------+
//| Check and advance epoch state                                    |
//+------------------------------------------------------------------+
void CTrendStrategy::CheckEpoch(const RegimeResult &newH1)
{
   bool ot = IsTrend(m_h1Regime.regime);
   bool nt = IsTrend(newH1.regime);
   bool adv = false;

   if (!ot && nt)
   {
      adv = true;
   }
   else if (ot && nt)
   {
      ENUM_TRADE_DIRECTION od = RegimeToDir(m_h1Regime.regime);
      ENUM_TRADE_DIRECTION nd = RegimeToDir(newH1.regime);
      if (od != nd && od != TRADE_DIR_NONE && nd != TRADE_DIR_NONE)
         adv = true;
   }
   else if (ot && !nt)
   {
      adv = true;
   }

   if (adv)
   {
      m_epochId++;
      m_epochStartAvail = newH1.latestClosedH1;
      m_epochDir = RegimeToDir(newH1.regime);
      m_hasPendingBreak = false;
      m_iprimed = false;
   }
}

//+------------------------------------------------------------------+
//| Detect 5-bar pivots across history                               |
//+------------------------------------------------------------------+
void CTrendStrategy::DetectPivots()
{
   int n = 1 + m_barsCount;
   if (n < 5) return;

   for (int i = 2; i < n - 2; i++)
   {
      double hi, lo;
      datetime bt, ct;

      hi = (i == 0) ? 0 : m_bars[i - 1].h;
      lo = (i == 0) ? 0 : m_bars[i - 1].l;
      bt = (i == 0) ? (m_bars[0].t - B07_M15_SEC) : m_bars[i - 1].t;

      if (i == 0) continue; // forming bar excluded

      double h_prev2 = (i - 2 == 0) ? 0 : m_bars[i - 3].h;
      double h_prev1 = (i - 1 == 0) ? 0 : m_bars[i - 2].h;
      double h_next1 = m_bars[i].h;
      double h_next2 = m_bars[i + 1].h;

      double l_prev2 = (i - 2 == 0) ? 0 : m_bars[i - 3].l;
      double l_prev1 = (i - 1 == 0) ? 0 : m_bars[i - 2].l;
      double l_next1 = m_bars[i].l;
      double l_next2 = m_bars[i + 1].l;

      bool is_hi = (hi > h_prev1 && hi > h_prev2 && hi > h_next1 && hi > h_next2);
      bool is_lo = (lo < l_prev1 && lo < l_prev2 && lo < l_next1 && lo < l_next2);

      ct = m_bars[i + 1].avail;

      if (is_hi)
      {
         bool exists = false;
         for (int s = 0; s < m_swingsCount; s++)
         {
            if (m_swings[s].bt == bt) { exists = true; break; }
         }
         if (!exists && m_swingsCount < B07_MAX_SWINGS)
         {
            m_swings[m_swingsCount].bt = bt;
            m_swings[m_swingsCount].ct = ct;
            m_swings[m_swingsCount].p = hi;
            m_swings[m_swingsCount].k = 1;
            m_swingsCount++;
         }
      }

      if (is_lo)
      {
         bool exists = false;
         for (int s = 0; s < m_swingsCount; s++)
         {
            if (m_swings[s].bt == bt) { exists = true; break; }
         }
         if (!exists && m_swingsCount < B07_MAX_SWINGS)
         {
            m_swings[m_swingsCount].bt = bt;
            m_swings[m_swingsCount].ct = ct;
            m_swings[m_swingsCount].p = lo;
            m_swings[m_swingsCount].k = -1;
            m_swingsCount++;
         }
      }
   }

   // Sort swings by ct
   for (int i = 0; i < m_swingsCount - 1; i++)
   {
      for (int j = i + 1; j < m_swingsCount; j++)
      {
         if (m_swings[j].ct < m_swings[i].ct)
         {
            B07_Swing temp = m_swings[i];
            m_swings[i] = m_swings[j];
            m_swings[j] = temp;
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Update Impulse and Pullback legs                                 |
//+------------------------------------------------------------------+
void CTrendStrategy::UpdateLegs(double atr, ENUM_TRADE_DIRECTION d)
{
   m_iprimed = false;
   if (m_swingsCount < 2 || atr <= 0) return;

   for (int i = m_swingsCount - 1; i > 0; i--)
   {
      B07_Swing a = m_swings[i - 1];
      B07_Swing b = m_swings[i];

      if (IsImpulse(a, b, d) && SwingLengthAtr(a, b, atr) >= B07_IMP_MIN)
      {
         m_iot = a.ct;
         m_iop = a.p;
         m_iet = b.ct;
         m_iep = b.p;
         m_ila = SwingLengthAtr(a, b, atr);
         m_iprimed = true;

         m_pbt = 0;
         m_pbp = 0;
         m_pbd = 0;

         for (int j = m_swingsCount - 1; j >= 0; j--)
         {
            B07_Swing s = m_swings[j];
            if (s.ct <= b.ct) break;

            if (d == TRADE_DIR_BUY && s.k == -1)
            {
               double dep = MathAbs(b.p - s.p) / atr;
               if (dep >= B07_PB_MIN && dep <= B07_PB_MAX)
               {
                  m_pbt = s.ct;
                  m_pbp = s.p;
                  m_pbd = dep;
                  break;
               }
            }
            else if (d == TRADE_DIR_SELL && s.k == 1)
            {
               double dep = MathAbs(s.p - b.p) / atr;
               if (dep >= B07_PB_MIN && dep <= B07_PB_MAX)
               {
                  m_pbt = s.ct;
                  m_pbp = s.p;
                  m_pbd = dep;
                  break;
               }
            }
         }
         return;
      }
   }
   m_iprimed = false;
}

//+------------------------------------------------------------------+
//| Add Break structure                                              |
//+------------------------------------------------------------------+
void CTrendStrategy::AddBreak(const B07_Swing &sw, bool bull, const B07_Bar &bar)
{
   for (int i = 0; i < m_breaksCount; i++)
   {
      if (m_breaks[i].barTime == sw.bt) return;
   }

   TrendBreakItem nw;
   nw.barTime = sw.bt;
   nw.price = sw.p;
   nw.bullish = bull;
   nw.availableAt = bar.avail;
   nw.age = 1;
   nw.consumed = false;
   nw.expired = false;

   if (m_hasPendingBreak && !m_pendingBreak.consumed && !m_pendingBreak.expired)
   {
      if (m_pendingBreak.bullish == bull)
      {
         bool sup = (bull && nw.price > m_pendingBreak.price) || (!bull && nw.price < m_pendingBreak.price);
         if (sup)
         {
            m_pendingBreak.expired = true;
            for (int i = 0; i < m_breaksCount; i++)
            {
               if (m_breaks[i].barTime == m_pendingBreak.barTime)
                  m_breaks[i].expired = true;
            }
            m_pendingBreak = nw;
         }
         return;
      }
   }

   m_pendingBreak = nw;
   m_hasPendingBreak = true;
   if (m_breaksCount < B07_MAX_BREAKS)
   {
      m_breaks[m_breaksCount++] = nw;
   }
}

//+------------------------------------------------------------------+
//| Advance break ages and expire old ones                           |
//+------------------------------------------------------------------+
void CTrendStrategy::AdvanceBreakAges()
{
   for (int i = 0; i < m_breaksCount; i++)
   {
      if (!m_breaks[i].consumed && !m_breaks[i].expired)
      {
         m_breaks[i].age++;
         if (m_breaks[i].age > B07_RET_MAX)
            m_breaks[i].expired = true;
      }
   }
   if (m_hasPendingBreak)
   {
      if (!m_pendingBreak.consumed && !m_pendingBreak.expired)
      {
         m_pendingBreak.age++;
         if (m_pendingBreak.age > B07_RET_MAX)
            m_pendingBreak.expired = true;
      }
      if (m_pendingBreak.expired)
         m_hasPendingBreak = false;
   }
}

//+------------------------------------------------------------------+
//| Check Break Retest condition                                     |
//+------------------------------------------------------------------+
void CTrendStrategy::CheckRetest(const B07_Bar &bar, double atr)
{
   if (!m_hasPendingBreak || m_pendingBreak.consumed || m_pendingBreak.expired || atr <= 0)
      return;
   if (bar.avail <= m_pendingBreak.availableAt) return;
   if (m_pendingBreak.age > B07_RET_MAX) return;

   double tol = B07_RET_TOL * atr;
   if (m_pendingBreak.bullish)
   {
      if (bar.l < m_pendingBreak.price - tol)
      {
         m_pendingBreak.expired = true;
         for (int i = 0; i < m_breaksCount; i++)
            if (m_breaks[i].barTime == m_pendingBreak.barTime) m_breaks[i].expired = true;
         m_hasPendingBreak = false;
         return;
      }
      if (bar.l <= m_pendingBreak.price + tol && bar.c > m_pendingBreak.price)
      {
         m_pendingBreak.consumed = true;
         for (int i = 0; i < m_breaksCount; i++)
            if (m_breaks[i].barTime == m_pendingBreak.barTime) m_breaks[i].consumed = true;
      }
   }
   else
   {
      if (bar.h > m_pendingBreak.price + tol)
      {
         m_pendingBreak.expired = true;
         for (int i = 0; i < m_breaksCount; i++)
            if (m_breaks[i].barTime == m_pendingBreak.barTime) m_breaks[i].expired = true;
         m_hasPendingBreak = false;
         return;
      }
      if (bar.h >= m_pendingBreak.price - tol && bar.c < m_pendingBreak.price)
      {
         m_pendingBreak.consumed = true;
         for (int i = 0; i < m_breaksCount; i++)
            if (m_breaks[i].barTime == m_pendingBreak.barTime) m_breaks[i].consumed = true;
      }
   }
}

//+------------------------------------------------------------------+
//| Check contradiction bar                                          |
//+------------------------------------------------------------------+
bool CTrendStrategy::CheckContradiction(const B07_Bar &bar, ENUM_TRADE_DIRECTION d, double atr, double inv)
{
   if (atr <= 0) return false;
   if (d == TRADE_DIR_BUY && bar.c < inv) return true;
   if (d == TRADE_DIR_SELL && bar.c > inv) return true;

   double body = MathAbs(bar.c - bar.o) / atr;
   if (d == TRADE_DIR_BUY && bar.c < bar.o && body >= B07_CONTR_DISP) return true;
   if (d == TRADE_DIR_SELL && bar.c > bar.o && body >= B07_CONTR_DISP) return true;

   return false;
}

//+------------------------------------------------------------------+
//| Target lookup (chronological lookback)                           |
//+------------------------------------------------------------------+
double CTrendStrategy::GetTargetPrice(double ent, ENUM_TRADE_DIRECTION d, datetime afterTime)
{
   bool found = false;
   double bestPrice = ent;
   int cnt = 0;

   for (int i = m_swingsCount - 1; i >= 0; i--)
   {
      if (m_swings[i].ct > afterTime) continue;
      cnt++;
      if (cnt > B07_TGT_LOOKBACK) break;

      if (d == TRADE_DIR_BUY && m_swings[i].k == 1 && m_swings[i].p > ent)
      {
         if (!found || m_swings[i].p < bestPrice)
         {
            bestPrice = m_swings[i].p;
            found = true;
         }
      }
      else if (d == TRADE_DIR_SELL && m_swings[i].k == -1 && m_swings[i].p < ent)
      {
         if (!found || m_swings[i].p > bestPrice)
         {
            bestPrice = m_swings[i].p;
            found = true;
         }
      }
   }

   return bestPrice;
}

//+------------------------------------------------------------------+
//| Evaluate Pullback setup                                          |
//+------------------------------------------------------------------+
bool CTrendStrategy::EvaluatePullback(TradeCandidate &cand, double atr, datetime now)
{
   if (!m_iprimed || atr <= 0) return false;
   ENUM_TRADE_DIRECTION d = RegimeToDir(m_h1Regime.regime);
   if (d == TRADE_DIR_NONE) return false;

   // Find C
   bool foundC = false;
   B07_Swing c;
   for (int i = m_swingsCount - 1; i >= 0; i--)
   {
      if (m_swings[i].ct <= m_iet) break;
      if (m_swings[i].ct < m_epochStartAvail) continue;
      if (d == TRADE_DIR_BUY && m_swings[i].k == -1) { c = m_swings[i]; foundC = true; break; }
      if (d == TRADE_DIR_SELL && m_swings[i].k == 1) { c = m_swings[i]; foundC = true; break; }
   }
   if (!foundC) return false;

   // Value zone
   double ap = m_iop, bp = m_iep;
   double zlo = ap + B07_ZONE_LO * (bp - ap);
   double zhi = ap + B07_ZONE_HI * (bp - ap);

   if (d == TRADE_DIR_BUY)
   {
      if (!(zlo <= c.p && c.p <= zhi)) return false;
      if (c.p < ap) return false;
   }
   else
   {
      if (!(zhi <= c.p && c.p <= zlo)) return false;
      if (c.p > ap) return false;
   }

   // Trigger: reclaim midpoint
   double mid = (bp + c.p) / 2.0;
   bool foundTrigger = false;
   B07_Bar tri;
   for (int i = 0; i < m_barsCount; i++)
   {
      if (m_bars[i].avail <= c.ct) continue;
      if (m_bars[i].avail > now) continue;
      if (d == TRADE_DIR_BUY && m_bars[i].c > mid) { tri = m_bars[i]; foundTrigger = true; break; }
      if (d == TRADE_DIR_SELL && m_bars[i].c < mid) { tri = m_bars[i]; foundTrigger = true; break; }
   }
   if (!foundTrigger) return false;

   double ent = tri.c;
   double inv = c.p;
   double stp = (d == TRADE_DIR_BUY) ? (inv - B07_STOP_BUF * atr) : (inv + B07_STOP_BUF * atr);
   double sd = MathAbs(ent - stp);
   double sda = (atr > 0) ? (sd / atr) : 0.0;

   if (sda < B07_MIN_STOP || sda > B07_MAX_STOP) return false;
   double ext = (atr > 0) ? (MathAbs(ent - c.p) / atr) : 0.0;
   if (ext >= B07_MAX_EXT) return false;

   double tp = GetTargetPrice(ent, d, now);
   double rd = MathAbs(tp - ent);
   double rr = (sd > 0) ? (rd / sd) : 0.0;
   int age = CountBarsBetween(c.ct, tri.avail);

   cand.valid = true;
   cand.symbol = m_symbol;
   cand.direction = d;
   cand.setupFamily = SETUP_FAMILY_PULLBACK;
   cand.sourceRegime = m_h1Regime.regime;
   cand.sourceRegimeQuality = m_h1Regime.quality;
   cand.h1AvailableAt = m_h1Regime.latestClosedH1;
   cand.h1SourceBarTime = m_h1Regime.latestClosedH1;
   cand.m15BarTime = tri.t;
   cand.m15AvailableAt = tri.avail;
   cand.entryPrice = ent;
   cand.invalidationPrice = inv;
   cand.initialStopPrice = stp;
   cand.stopDistance = sd;
   cand.stopDistanceAtr = sda;
   cand.targetPrice = tp;
   cand.rewardDistance = rd;
   cand.rewardRiskRatio = rr;
   cand.pullbackDepth = m_pbd;
   cand.triggerDisplacement = 0.0;
   cand.retestDistanceAtr = 0.0;
   cand.extensionAtr = ext;
   cand.structuralReferenceTime = c.ct;
   cand.setupAgeBars = age;
   cand.qualificationReason = "pullback";
   cand.disqualificationReason = "";

   return true;
}

//+------------------------------------------------------------------+
//| Evaluate Break-Retest setup                                      |
//+------------------------------------------------------------------+
bool CTrendStrategy::EvaluateBreakRetest(TradeCandidate &cand, double atr, datetime now)
{
   if (!m_hasPendingBreak || !m_pendingBreak.consumed || m_pendingBreak.expired || atr <= 0)
      return false;
   if (m_pendingBreak.age > B07_RET_MAX) return false;

   ENUM_TRADE_DIRECTION d = RegimeToDir(m_h1Regime.regime);
   if (d == TRADE_DIR_NONE) return false;

   // Acceptance bar
   bool foundAcc = false;
   B07_Bar acc;
   for (int i = 0; i < m_barsCount; i++)
   {
      if (m_bars[i].avail <= m_pendingBreak.availableAt) continue;
      if (m_bars[i].avail > now) continue;
      if (d == TRADE_DIR_BUY && m_bars[i].c > m_pendingBreak.price) { acc = m_bars[i]; foundAcc = true; break; }
      if (d == TRADE_DIR_SELL && m_bars[i].c < m_pendingBreak.price) { acc = m_bars[i]; foundAcc = true; break; }
   }
   if (!foundAcc) return false;

   double ent = acc.c;
   double tl = m_pendingBreak.price;
   double th = m_pendingBreak.price;

   for (int i = 0; i < m_barsCount; i++)
   {
      if (m_bars[i].avail <= m_pendingBreak.availableAt) continue;
      if (d == TRADE_DIR_BUY) tl = MathMin(tl, m_bars[i].l);
      else th = MathMax(th, m_bars[i].h);
   }

   double inv = (d == TRADE_DIR_BUY) ? tl : th;
   double stp = (d == TRADE_DIR_BUY) ? (inv - B07_STOP_BUF * atr) : (inv + B07_STOP_BUF * atr);
   double sd = MathAbs(ent - stp);
   double sda = (atr > 0) ? (sd / atr) : 0.0;

   if (sda < B07_MIN_STOP || sda > B07_MAX_STOP) return false;
   double ext = (atr > 0) ? (MathAbs(ent - m_pendingBreak.price) / atr) : 0.0;
   if (ext >= B07_MAX_EXT) return false;

   double rtd = (atr > 0) ? (MathAbs(m_pendingBreak.price - inv) / atr) : 0.0;
   double tp = GetTargetPrice(ent, d, now);
   double rd = MathAbs(tp - ent);
   double rr = (sd > 0) ? (rd / sd) : 0.0;

   cand.valid = true;
   cand.symbol = m_symbol;
   cand.direction = d;
   cand.setupFamily = SETUP_FAMILY_BREAK_RETEST;
   cand.sourceRegime = m_h1Regime.regime;
   cand.sourceRegimeQuality = m_h1Regime.quality;
   cand.h1AvailableAt = m_h1Regime.latestClosedH1;
   cand.h1SourceBarTime = m_h1Regime.latestClosedH1;
   cand.m15BarTime = acc.t;
   cand.m15AvailableAt = acc.avail;
   cand.entryPrice = ent;
   cand.invalidationPrice = inv;
   cand.initialStopPrice = stp;
   cand.stopDistance = sd;
   cand.stopDistanceAtr = sda;
   cand.targetPrice = tp;
   cand.rewardDistance = rd;
   cand.rewardRiskRatio = rr;
   cand.pullbackDepth = 0.0;
   cand.triggerDisplacement = 0.0;
   cand.retestDistanceAtr = rtd;
   cand.extensionAtr = ext;
   cand.structuralReferenceTime = m_pendingBreak.barTime;
   cand.setupAgeBars = m_pendingBreak.age;
   cand.qualificationReason = "break_retest";
   cand.disqualificationReason = "";

   return true;
}

//+------------------------------------------------------------------+
//| Evaluate Momentum Continuation setup                             |
//+------------------------------------------------------------------+
bool CTrendStrategy::EvaluateMomentum(TradeCandidate &cand, double atr, datetime now)
{
   if (atr <= 0 || m_barsCount < B07_MOM_LB + 1) return false;
   ENUM_TRADE_DIRECTION d = RegimeToDir(m_h1Regime.regime);
   if (d == TRADE_DIR_NONE) return false;

   double cn = m_bars[m_barsCount - 1].c;
   double co = m_bars[m_barsCount - 1 - (B07_MOM_LB - 1)].c;
   double disp = (d == TRADE_DIR_BUY) ? ((cn - co) / atr) : ((co - cn) / atr);

   if (disp < B07_MOM_MIN_D) return false;

   // Leg base swing
   bool foundLb = false;
   B07_Swing lb;
   for (int i = m_swingsCount - 1; i >= 0; i--)
   {
      if (m_swings[i].ct > now) continue;
      if (m_swings[i].ct < m_epochStartAvail) continue;
      if (d == TRADE_DIR_BUY && m_swings[i].k == -1) { lb = m_swings[i]; foundLb = true; break; }
      if (d == TRADE_DIR_SELL && m_swings[i].k == 1) { lb = m_swings[i]; foundLb = true; break; }
   }
   if (!foundLb) return false;

   B07_Bar tri = m_bars[m_barsCount - 1];
   double ext = MathAbs(tri.c - lb.p) / atr;
   if (ext >= B07_MAX_EXT) return false;
   if (tri.avail < m_epochStartAvail) return false;

   double ent = tri.c;
   double inv = lb.p;
   double stp = (d == TRADE_DIR_BUY) ? (inv - B07_STOP_BUF * atr) : (inv + B07_STOP_BUF * atr);
   double sd = MathAbs(ent - stp);
   double sda = (atr > 0) ? (sd / atr) : 0.0;

   if (sda < B07_MIN_STOP || sda > B07_MAX_STOP) return false;

   double tp = GetTargetPrice(ent, d, now);
   double rd = MathAbs(tp - ent);
   double rr = (sd > 0) ? (rd / sd) : 0.0;

   cand.valid = true;
   cand.symbol = m_symbol;
   cand.direction = d;
   cand.setupFamily = SETUP_FAMILY_MOMENTUM;
   cand.sourceRegime = m_h1Regime.regime;
   cand.sourceRegimeQuality = m_h1Regime.quality;
   cand.h1AvailableAt = m_h1Regime.latestClosedH1;
   cand.h1SourceBarTime = m_h1Regime.latestClosedH1;
   cand.m15BarTime = tri.t;
   cand.m15AvailableAt = tri.avail;
   cand.entryPrice = ent;
   cand.invalidationPrice = inv;
   cand.initialStopPrice = stp;
   cand.stopDistance = sd;
   cand.stopDistanceAtr = sda;
   cand.targetPrice = tp;
   cand.rewardDistance = rd;
   cand.rewardRiskRatio = rr;
   cand.pullbackDepth = 0.0;
   cand.triggerDisplacement = disp;
   cand.retestDistanceAtr = 0.0;
   cand.extensionAtr = ext;
   cand.structuralReferenceTime = lb.ct;
   cand.setupAgeBars = 1;
   cand.qualificationReason = "momentum";
   cand.disqualificationReason = "";

   return true;
}

//+------------------------------------------------------------------+
//| Candidate Identity String                                        |
//+------------------------------------------------------------------+
string CTrendStrategy::FormatCandidateIdentity(const TradeCandidate &cand) const
{
   return StringFormat("%s|%d|%d|%d", cand.symbol, (int)cand.m15AvailableAt, (int)cand.setupFamily, (int)cand.structuralReferenceTime);
}

//+------------------------------------------------------------------+
//| Feed completed M15 Bar and evaluate candidates                   |
//+------------------------------------------------------------------+
bool CTrendStrategy::FeedM15Bar(datetime t, double o, double h, double l, double c, datetime avail, double atr, TradeCandidate &outCandidate)
{
   ZeroMemory(outCandidate);

   if (t == m_lastBarTime) return false;
   m_lastBarTime = t;
   m_lastAvail = avail;

   if (m_barsCount < B07_MAX_BARS)
   {
      m_bars[m_barsCount].t = t;
      m_bars[m_barsCount].o = o;
      m_bars[m_barsCount].h = h;
      m_bars[m_barsCount].l = l;
      m_bars[m_barsCount].c = c;
      m_bars[m_barsCount].avail = avail;
      m_barsCount++;
   }
   else
   {
      for (int i = 0; i < B07_MAX_BARS - 1; i++)
         m_bars[i] = m_bars[i + 1];
      m_bars[B07_MAX_BARS - 1].t = t;
      m_bars[B07_MAX_BARS - 1].o = o;
      m_bars[B07_MAX_BARS - 1].h = h;
      m_bars[B07_MAX_BARS - 1].l = l;
      m_bars[B07_MAX_BARS - 1].c = c;
      m_bars[B07_MAX_BARS - 1].avail = avail;
   }

   AdvanceBreakAges();
   DetectPivots();

   if (m_hasH1Regime && IsTrend(m_h1Regime.regime))
   {
      ENUM_TRADE_DIRECTION d = RegimeToDir(m_h1Regime.regime);
      UpdateLegs(atr, d);

      if (m_barsCount > 0)
      {
         B07_Bar lastB = m_bars[m_barsCount - 1];
         for (int i = 0; i < m_swingsCount; i++)
         {
            if (m_swings[i].ct > avail) continue;
            if (d == TRADE_DIR_BUY && m_swings[i].k == 1 && lastB.c > m_swings[i].p + B07_BRK_PEN * atr)
               AddBreak(m_swings[i], true, lastB);
            else if (d == TRADE_DIR_SELL && m_swings[i].k == -1 && lastB.c < m_swings[i].p - B07_BRK_PEN * atr)
               AddBreak(m_swings[i], false, lastB);
         }
      }

      B07_Bar curB = m_bars[m_barsCount - 1];
      CheckRetest(curB, atr);

      if (m_iprimed)
      {
         double inv = (m_pbp > 0) ? m_pbp : m_iop;
         if (CheckContradiction(curB, d, atr, inv))
            return false;
      }
   }

   // Evaluation
   if (!m_hasH1Regime || !IsTrend(m_h1Regime.regime) || !m_h1Regime.valid)
      return false;

   datetime now = m_lastAvail;
   TradeCandidate cand;

   if (EvaluatePullback(cand, atr, now))
   {
      string ident = FormatCandidateIdentity(cand);
      if (ident == m_lastCandidateIdentity) return false;
      m_lastCandidateIdentity = ident;
      outCandidate = cand;
      return true;
   }

   if (EvaluateBreakRetest(cand, atr, now))
   {
      string ident = FormatCandidateIdentity(cand);
      if (ident == m_lastCandidateIdentity) return false;
      m_lastCandidateIdentity = ident;
      outCandidate = cand;
      return true;
   }

   if (EvaluateMomentum(cand, atr, now))
   {
      string ident = FormatCandidateIdentity(cand);
      if (ident == m_lastCandidateIdentity) return false;
      m_lastCandidateIdentity = ident;
      outCandidate = cand;
      return true;
   }

   return false;
}

//+------------------------------------------------------------------+
//| 64-bit FNV-1a Hash                                               |
//+------------------------------------------------------------------+
ulong CTrendStrategy::Fnv1a64(const uchar &data[]) const
{
   ulong h = 0xCBF29CE484222325;
   int n = ArraySize(data);
   for (int i = 0; i < n; i++)
   {
      h ^= data[i];
      h = h * 0x100000001B3;
   }
   return h;
}

//+------------------------------------------------------------------+
//| Generate B07D1 Diagnostic String                                 |
//+------------------------------------------------------------------+
string CTrendStrategy::GetB07D1Hash(const TradeCandidate &c)
{
   string parts = "";

   int h1reg = (m_hasH1Regime) ? (int)m_h1Regime.regime : 2;
   int h1val = (m_hasH1Regime && m_h1Regime.valid) ? 1 : 0;
   int h1qual = (m_hasH1Regime) ? (int)m_h1Regime.quality : 1;
   datetime h1src = (m_hasH1Regime) ? m_h1Regime.latestClosedH1 : 0;
   datetime h1avail = (m_hasH1Regime) ? m_h1Regime.latestClosedH1 : 0;

   parts += StringFormat("h1src=%d;h1avail=%d;h1regime=%d;h1valid=%d;h1quality=%d;",
                         (int)h1src, (int)h1avail, h1reg, h1val, h1qual);

   parts += StringFormat("epoch=%d;epochStartAvail=%d;epochDir=%d;",
                         (int)m_epochId, (int)m_epochStartAvail, (int)m_epochDir);

   parts += StringFormat("m15barOpen=%d;m15avail=%d;", (int)m_lastBarTime, (int)m_lastAvail);

   if (c.valid)
   {
      parts += StringFormat("family=%d;dir=%d;candValid=1;", (int)c.setupFamily, (int)c.direction);
      parts += StringFormat("entry=%G;inv=%G;stop=%G;target=%G;", c.entryPrice, c.invalidationPrice, c.initialStopPrice, c.targetPrice);
      parts += StringFormat("extension=%G;displacement=%G;", c.extensionAtr, c.triggerDisplacement);
      parts += StringFormat("structRef=%d;setupAge=%d;", (int)c.structuralReferenceTime, c.setupAgeBars);
   }
   else
   {
      parts += "family=0;dir=0;candValid=0;entry=0;inv=0;stop=0;target=0;extension=0;displacement=0;structRef=0;setupAge=0;";
   }

   string sw = "";
   for (int i = 0; i < m_swingsCount; i++)
   {
      if (i > 0) sw += ",";
      sw += StringFormat("%d|%d|%G|%d", m_swings[i].k, (int)m_swings[i].bt, m_swings[i].p, (int)m_swings[i].ct);
   }
   parts += StringFormat("swings=%s;", sw);

   parts += StringFormat("impulse=%s;%d;%G;%d;%G;%G;", (m_iprimed ? "1" : "0"), (int)m_iot, m_iop, (int)m_iet, m_iep, m_ila);
   parts += StringFormat("pullback=%d;%G;%G;", (int)m_pbt, m_pbp, m_pbd);

   string br = "";
   for (int i = 0; i < m_breaksCount; i++)
   {
      if (i > 0) br += ",";
      br += StringFormat("%d|%G|%d|%d|%d|%d|%d", (int)m_breaks[i].barTime, m_breaks[i].price, (m_breaks[i].bullish ? 1 : 0), (int)m_breaks[i].availableAt, m_breaks[i].age, (m_breaks[i].consumed ? 1 : 0), (m_breaks[i].expired ? 1 : 0));
   }
   parts += StringFormat("breaks=%s;", br);

   if (m_hasPendingBreak && !m_pendingBreak.expired)
   {
      parts += StringFormat("pendRetest=1;%d;%G;%d;%d;", (int)m_pendingBreak.barTime, m_pendingBreak.price, (int)m_pendingBreak.availableAt, m_pendingBreak.age);
   }
   else
   {
      parts += "pendRetest=0;";
   }

   string con = "";
   bool firstCon = true;
   for (int i = 0; i < m_breaksCount; i++)
   {
      if (m_breaks[i].consumed || m_breaks[i].expired)
      {
         if (!firstCon) con += ",";
         con += StringFormat("%d", (int)m_breaks[i].barTime);
         firstCon = false;
      }
   }
   parts += StringFormat("consumed=%s;", con);
   parts += StringFormat("lastIdentity=%s", m_lastCandidateIdentity);

   uchar data[];
   StringToCharArray(parts, data, 0, StringLen(parts));
   ulong hash = Fnv1a64(data);

   return StringFormat("B07D1:%016llX", hash);
}
