/** Human-readable labels for the raw feature keys, source types and coverage
 * components. The registry keys are snake_case machine identifiers; these give the UI
 * proper, consistently-cased names so nothing reads as a shouting enum or a bare key.
 * Anything unmapped falls back to a Title-Cased version of the key, so a new feature
 * still renders sensibly. */

const FEATURE_LABELS: Record<string, string> = {
  history_depth_days: "History depth",
  median_monthly_inflow_paise: "Median monthly inflow",
  p25_monthly_inflow_paise: "Low-month inflow (25th pct)",
  monthly_inflow_cv: "Monthly inflow variability",
  inflow_trend_ratio: "Inflow trend",
  inflow_source_count: "Distinct income sources",
  income_months_observed: "Months of income seen",
  total_inflow_6m_paise: "Total inflow (6 mo)",
  salary_income_share: "Salary share of income",
  gig_income_share: "Gig share of income",
  business_income_share: "Business share of income",
  monthly_emi_paise: "Monthly EMI",
  essential_expense_paise: "Essential expenses",
  debt_service_ratio: "Debt-service ratio",
  essential_expense_ratio: "Essential-expense ratio",
  mean_balance_paise: "Mean balance",
  min_balance_paise: "Minimum balance",
  balance_min_to_mean_ratio: "Balance stability",
  expense_cover_months: "Expense cover",
  utility_payment_ratio: "Utility payment rate",
  utility_ontime_streak_months: "Utility on-time streak",
  telecom_continuity_months: "Telecom continuity",
  source_diversity: "Source diversity",
  other_share: "Uncategorised spend share",
  txn_density_per_month: "Transactions per month",
  unclassified_inflow_share: "Unclassified inflow share",
  vector_classified_share: "Vector-classified share",
  bureau_score: "Bureau score",
  bureau_active_loans: "Bureau active loans",
  bureau_delinquencies_12m: "Bureau delinquencies (12 mo)",
};

const SOURCE_TYPE_LABELS: Record<string, string> = {
  BANK: "Bank",
  UPI: "UPI",
  UTILITY: "Utility",
  TELECOM: "Telecom",
  BUREAU: "Credit bureau",
  DECLARED_DOCUMENT: "Declared document",
};

const COVERAGE_COMPONENT_LABELS: Record<string, string> = {
  tier: "Source tier",
  verification: "Verification",
  history_depth: "History depth",
  freshness: "Freshness",
  diversity: "Source diversity",
  completeness: "Feature completeness",
};

/** Title-case a snake_case/lower key as a last-resort label. */
function titleCase(key: string): string {
  const cleaned = key.replace(/_paise$/, "").replace(/_/g, " ").trim();
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

export function featureLabel(key: string): string {
  return FEATURE_LABELS[key] ?? titleCase(key);
}

export function sourceTypeLabel(type: string): string {
  return SOURCE_TYPE_LABELS[type] ?? titleCase(type);
}

export function coverageComponentLabel(name: string): string {
  return COVERAGE_COMPONENT_LABELS[name] ?? titleCase(name);
}
