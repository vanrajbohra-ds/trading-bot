export interface Account {
  portfolio_value: string;
  cash: string;
  buying_power: string;
  equity: string;
  last_equity: string;
}

export interface Position {
  symbol: string;
  qty: string;
  avg_entry_price: string;
  current_price: string;
  market_value: string;
  unrealized_pl: string;
  unrealized_plpc: string;
  side: string;
  asset_class?: string;
}

export interface Order {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  status: string;
  qty: string;
  filled_qty: string;
  filled_avg_price: string | null;
  filled_at: string | null;
  type: string;
  created_at: string;
}

export interface PortfolioHistory {
  timestamp: number[];
  equity: number[];
  profit_loss: number[];
  base_value: number;
}

export interface Stop {
  stop_price: number;
  target_price: number;
  entry_price: number;
  atr_used: number;
  stop_pct: number;
  target_pct: number;
  tier: string;
  entry_date: string;
}

export interface StopsData {
  [symbol: string]: Stop;
}

export interface PriceQuote {
  symbol: string;
  price: number;
  change: number;
  changePct: number;
  label: string;
}

export interface OHLCVRow {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  bbUpper: number | null;
  bbLower: number | null;
  bbMid: number | null;
  rsi: number | null;
  macd: number | null;
  macdSignal: number | null;
  macdHist: number | null;
}

export interface TechnicalSignals {
  rsi: number | null;
  macdHist: number | null;
  macd: number | null;
  macdSignal: number | null;
  volRatio: number | null;
  goldenCross: boolean | null;
  bbPband: number | null;
  bbUpper: number | null;
  bbLower: number | null;
  obvTrend: 'RISING' | 'FALLING' | 'FLAT' | null;
  sma20: number | null;
  sma50: number | null;
}

export interface FundamentalData {
  currentPrice: number | null;
  analystRecommendation: string | null;
  analystTargetPrice: number | null;
  peRatio: number | null;
  revenueGrowth: number | null;
  newsSentimentLabel: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | null;
  newsSentimentScore: number | null;
  week52High: number | null;
  week52Low: number | null;
  marketCap: number | null;
  putCallRatio: number | null;
  earningsInDays: number | null;
  isCrypto: boolean;
}

export interface NewsItem {
  dt: string;
  title: string;
  source: string;
  tag: '🟢' | '🔴' | '⚪';
}

export interface InsiderTransaction {
  name: string;
  role: string;
  shares: number;
  value: number;
  type: string;
  date: string;
}

export interface ExploreData {
  symbol: string;
  yfsymbol: string;
  isCrypto: boolean;
  currentPrice: number | null;
  chart: OHLCVRow[];
  technical: TechnicalSignals;
  fundamental: FundamentalData;
  news: NewsItem[];
  insider: InsiderTransaction[];
  error?: string;
}

export interface ScreenerQuote {
  symbol: string;
  name: string;
  price: number;
  changePct: number;
  volumeRatio: number;
  marketCap: number;
}

export interface SignalCheck {
  pass: boolean;
  checks: number;
  rsi: number | null;
  volRatio: number | null;
  macdHist: number | null;
  volOk: boolean;
  rsiOk: boolean;
  macdOk: boolean;
}

export interface ScoreSignal {
  icon: '✅' | '🟡' | '❌' | '⚠️';
  label: string;
}

export interface Score {
  score: number;
  signals: ScoreSignal[];
}
