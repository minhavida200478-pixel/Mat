// Shared types for the prediction panel and its sub-components.
export type ProbPoint = { date: string; dayOffset: number; probability: number };
export type HealthFlag = { code: string; severity: string; message: string; value: any };
export type TrendInsight = {
  type: string;
  direction: string;
  change_days: number;
  message: string;
};
export type ReliabilityIndex = {
  score: number;
  classification: string;
  factors?: Record<string, number>;
};
export type IntervalBand = { start: string; end: string; half_width_days: number };
export type PredictionIntervals = {
  p50?: IntervalBand;
  p75?: IntervalBand;
  p90?: IntervalBand;
  p95?: IntervalBand;
  source?: string;
};
export type DataSufficiency = { level: number; label: string; max_confidence: number };
export type Prediction = {
  predictedDate: string | null;
  earliestDate: string | null;
  latestDate: string | null;
  confidence: number;
  regularity: string;
  cycleLengthPrediction: number;
  probabilityDistribution: ProbPoint[];
  fertileWindowStart: string | null;
  fertileWindowEnd: string | null;
  ovulationDate: string | null;
  healthFlags: HealthFlag[];
  trendInsights: TrendInsight[];
  reliabilityIndex?: ReliabilityIndex;
  predictionIntervals?: PredictionIntervals;
  dataSufficiency?: DataSufficiency;
  profile: {
    cycle_count: number;
    cycle_standard_deviation: number;
    data_quality_score: number;
    prediction_accuracy_score: number | null;
  };
};
