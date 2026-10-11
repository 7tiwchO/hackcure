// ============================================================
// HackCure - Hospital link, care program and subscription types
// Every field is treated defensively: the backend may omit optional ones.
// ============================================================

export type AgentMode = 'llm' | 'rules';

export interface AgentRunStep {
  name: string;
  status: 'ok' | 'skipped' | 'error';
  detail?: string | null;
}

export interface AgentRun {
  id: string;
  started_at: string;
  trigger: string;
  mode: AgentMode;
  status: 'ok' | 'partial' | 'error';
  summary?: string | null;
  steps?: AgentRunStep[] | null;
}

export type HospitalDocumentType = 'PRESCRIPTION' | 'DOCTOR_REPORT' | 'MEDICAL_RECORD';
export type HospitalSyncStatus = 'ok' | 'offline' | 'error';

export interface HospitalDocument {
  id: string;
  type: HospitalDocumentType | string;
  title: string;
  date?: string | null;
  status?: string | null;
  synced_at?: string | null;
}

export interface HospitalLinkStatus {
  linked: boolean;
  pseudonym?: string | null;
  linked_at?: string | null;
  consent_at?: string | null;
  last_sync_at?: string | null;
  last_sync_status?: HospitalSyncStatus | null;
  last_sync_error?: string | null;
  documents?: HospitalDocument[] | null;
  subscription_active?: boolean;
  last_agent_run?: AgentRun | null;
}

export interface HospitalLinkRequest {
  pseudonym: string;
  date_of_birth: string;
  consent: true;
}

export interface CareProgramValidation {
  status: 'draft' | 'applied';
  auto_applied?: boolean;
  label?: string | null;
  validated_by?: string | null;
}

export interface CareProgramNutrition {
  plan_type?: string | null;
  recommended_foods?: string[] | null;
  foods_to_avoid?: string[] | null;
  meals?: Record<string, string> | null;
  hydration_ml_daily?: number | null;
  calories_target?: number | null;
  notes?: string | null;
  rules?: string[] | null;
  confidence?: number | null;
  source?: string | null;
}

export interface CareProgramActivity {
  activity_name?: string | null;
  activity_type?: string | null;
  duration_minutes?: number | null;
  intensity?: string | null;
  frequency_per_week?: number | null;
  scheduled_days?: string[] | null;
  instructions?: string | null;
  contraindications?: string[] | null;
  confidence?: number | null;
  source?: string | null;
}

export type CareHabitCategory = 'sleep' | 'tobacco' | 'alcohol' | 'monitoring' | 'other';

export interface CareProgramHabit {
  key: string;
  category: CareHabitCategory | string;
  title: string;
  detail?: string | null;
  confidence?: number | null;
  source?: string | null;
}

export interface CareProgram {
  generated_at?: string | null;
  mode?: AgentMode;
  fallback?: boolean;
  validation?: CareProgramValidation | null;
  source?: string | null;
  nutrition?: CareProgramNutrition | null;
  activity?: CareProgramActivity | null;
  habits?: CareProgramHabit[] | null;
  medications?: {
    count?: number | null;
    next_dose?: { name: string; time: string } | null;
    source?: string | null;
  } | null;
  adherence?: {
    rate_7d?: number | null;
    missed_streak?: number | null;
    message?: string | null;
  } | null;
  warnings?: string[] | null;
}

export type SubscriptionPlan = 'monthly' | 'quarterly';

export interface Subscription {
  status: 'active' | 'expired' | 'none';
  active?: boolean;
  plan?: string | null;
  hospital_name?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  price_tnd?: number | null;
  hospital_share_pct?: number | null;
  team_share_pct?: number | null;
  demo?: boolean;
}
