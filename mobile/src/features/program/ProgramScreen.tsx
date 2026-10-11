import React, { useCallback, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { useTheme } from '../../theme';
import { useRTL } from '../../i18n/RTLContext';
import { programApi } from '../../services/api/program';
import { hospitalLinkApi } from '../../services/api/hospitalLink';
import { fetchWithOfflineCache } from '../../utils/offlineCache';
import { formatDate, formatDateTime, formatTime } from '../../utils/dateUtils';
import { AgentRun, CareProgram } from '../../types';
import { ScreenContainer } from '../../components/layout/ScreenContainer';
import { Header } from '../../components/layout/Header';
import { Card } from '../../components/ui/Card';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { CardSkeleton } from '../../components/ui/LoadingSkeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { ListItem } from '../../components/ui/ListItem';
import { SourceConfidence, toPercent } from './SourceConfidence';

const MEAL_KEYS: Record<string, string> = {
  breakfast: 'nutrition.breakfast', petit_dejeuner: 'nutrition.breakfast',
  lunch: 'nutrition.lunch', dejeuner: 'nutrition.lunch',
  dinner: 'nutrition.dinner', diner: 'nutrition.dinner',
  snacks: 'nutrition.snacks', snack: 'nutrition.snacks', collation: 'nutrition.snacks',
};

const INTENSITY_KEYS: Record<string, string> = {
  light: 'sport.light', low: 'sport.light', legere: 'sport.light',
  moderate: 'sport.moderate', medium: 'sport.moderate', moderee: 'sport.moderate',
  vigorous: 'sport.vigorous', high: 'sport.vigorous', soutenue: 'sport.vigorous',
};

const DAY_KEYS: Record<string, string> = {
  monday: 'monday', mon: 'monday', lundi: 'monday',
  tuesday: 'tuesday', tue: 'tuesday', mardi: 'tuesday',
  wednesday: 'wednesday', wed: 'wednesday', mercredi: 'wednesday',
  thursday: 'thursday', thu: 'thursday', jeudi: 'thursday',
  friday: 'friday', fri: 'friday', vendredi: 'friday',
  saturday: 'saturday', sat: 'saturday', samedi: 'saturday',
  sunday: 'sunday', sun: 'sunday', dimanche: 'sunday',
};

const HABIT_CATEGORIES = ['sleep', 'tobacco', 'alcohol', 'monitoring', 'other'] as const;
type HabitCategory = typeof HABIT_CATEGORIES[number];

const HABIT_ICONS: Record<HabitCategory, keyof typeof Ionicons.glyphMap> = {
  sleep: 'moon-outline',
  tobacco: 'ban-outline',
  alcohol: 'wine-outline',
  monitoring: 'pulse-outline',
  other: 'leaf-outline',
};

const normalizeKey = (value: string) => value.trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[\s-]+/g, '_');

const hasItems = <T,>(value?: T[] | null): value is T[] => Array.isArray(value) && value.length > 0;

export const ProgramScreen: React.FC = () => {
  const router = useRouter();
  const { colors, typography, spacing, radii } = useTheme();
  const { flexDirection, textAlign, isRTL } = useRTL();
  const { t } = useTranslation();
  const [journalOpen, setJournalOpen] = useState(false);

  const programQuery = useQuery({
    queryKey: ['care-program'],
    queryFn: () => fetchWithOfflineCache<CareProgram | null>('care-program', programApi.getProgram),
    retry: 1,
  });

  const linkQuery = useQuery({
    queryKey: ['hospital-link'],
    queryFn: () => fetchWithOfflineCache('hospital-link', hospitalLinkApi.getStatus),
    retry: 1,
  });

  const runsQuery = useQuery({
    queryKey: ['agent-runs'],
    queryFn: () => fetchWithOfflineCache<AgentRun[]>('agent-runs', () => programApi.getAgentRuns(10)),
    enabled: journalOpen,
    retry: 1,
  });

  const refetchProgram = programQuery.refetch;
  const refetchLink = linkQuery.refetch;
  const refetchAll = useCallback(() => {
    void refetchProgram();
    void refetchLink();
  }, [refetchProgram, refetchLink]);

  useFocusEffect(refetchAll);

  const program = programQuery.data?.data ?? null;
  const link = linkQuery.data?.data;
  const fromCache = !!programQuery.data?.fromCache;
  const refreshing = programQuery.isRefetching || linkQuery.isRefetching;

  const title = t('program.title');

  if ((programQuery.isLoading || (linkQuery.isLoading && !program)) && !program) {
    return (
      <ScreenContainer>
        <Header title={title} showBack />
        <CardSkeleton />
        <CardSkeleton />
        <CardSkeleton />
      </ScreenContainer>
    );
  }

  if (!program) {
    if (link && !link.linked) {
      return (
        <ScreenContainer onRefresh={refetchAll} refreshing={refreshing}>
          <Header title={title} showBack />
          <EmptyState
            icon="link-outline"
            title={t('program.notLinkedTitle')}
            description={t('program.notLinkedBody')}
            actionTitle={t('program.linkAction')}
            onAction={() => router.push('/hospital-link')}
          />
        </ScreenContainer>
      );
    }
    if (programQuery.isError) {
      return (
        <ScreenContainer onRefresh={refetchAll} refreshing={refreshing}>
          <Header title={title} showBack />
          <ErrorState title={t('program.loadError')} onRetry={refetchAll} />
        </ScreenContainer>
      );
    }
    return (
      <ScreenContainer onRefresh={refetchAll} refreshing={refreshing}>
        <Header title={title} showBack />
        <EmptyState
          icon="hourglass-outline"
          title={t('program.notGeneratedTitle')}
          description={t('program.notGeneratedBody')}
          actionTitle={link?.linked ? t('program.syncAction') : t('program.linkAction')}
          onAction={() => router.push('/hospital-link')}
        />
      </ScreenContainer>
    );
  }

  const validation = program.validation;
  const validationBadge = validation?.status === 'applied'
    ? validation.auto_applied
      ? { label: t('program.validationAuto'), color: colors.info, icon: 'flask-outline' as const }
      : { label: t('program.validationDoctor'), color: colors.success, icon: 'shield-checkmark-outline' as const }
    : { label: t('program.validationDraft'), color: colors.warning, icon: 'time-outline' as const };

  const nutrition = program.nutrition;
  const activity = program.activity;
  const habits = hasItems(program.habits) ? program.habits : [];
  const medications = program.medications;
  const adherence = program.adherence;
  const adherencePercent = toPercent(adherence?.rate_7d);
  const warnings = hasItems(program.warnings) ? program.warnings : [];
  const runs = hasItems(runsQuery.data?.data) ? runsQuery.data.data : [];

  const sectionTitle = (icon: keyof typeof Ionicons.glyphMap, label: string, color: string) => (
    <View style={[styles.sectionTitle, { flexDirection, marginTop: spacing.lg, marginBottom: spacing.sm }]}>
      <Ionicons name={icon} size={20} color={color} style={styles.sectionIcon} />
      <Text style={[typography.h4, { color: colors.textPrimary, textAlign, flex: 1 }]}>{label}</Text>
    </View>
  );

  const field = (label: string, value?: string | null) => (!value ? null : (
    <View style={styles.field}>
      <Text style={[typography.tiny, { color: colors.textMuted, textAlign }]}>{label}</Text>
      <Text style={[typography.body, { color: colors.textPrimary, textAlign, marginTop: 2 }]}>{value}</Text>
    </View>
  ));

  const bulletList = (label: string, items: string[] | null | undefined, color: string, icon: keyof typeof Ionicons.glyphMap) => (!hasItems(items) ? null : (
    <View style={styles.field}>
      <Text style={[typography.captionBold, { color, textAlign, marginBottom: 4 }]}>{label}</Text>
      {items.map((item, index) => (
        <View key={`${index}-${item}`} style={[styles.bulletRow, { flexDirection }]}>
          <Ionicons name={icon} size={14} color={color} style={styles.bulletIcon} />
          <Text style={[typography.body, { color: colors.textPrimary, textAlign, flex: 1 }]}>{item}</Text>
        </View>
      ))}
    </View>
  ));

  const mealLabel = (key: string) => {
    const known = MEAL_KEYS[normalizeKey(key)];
    return known ? t(known) : key;
  };
  const intensityLabel = (value?: string | null) => {
    if (!value) return null;
    const known = INTENSITY_KEYS[normalizeKey(value)];
    return known ? t(known) : value;
  };
  const dayLabel = (value: string) => {
    const known = DAY_KEYS[normalizeKey(value)];
    return known ? t(`program.weekdays.${known}`) : value;
  };
  const categoryOf = (value: string): HabitCategory => (
    (HABIT_CATEGORIES as readonly string[]).includes(value) ? (value as HabitCategory) : 'other'
  );

  const runTone = (status?: string) => (status === 'ok' ? colors.success : status === 'error' ? colors.error : colors.warning);
  const stepLabel = (status?: string) => (status === 'ok' ? t('program.stepOk') : status === 'error' ? t('program.stepError') : t('program.stepSkipped'));
  const runLabel = (status?: string) => (status === 'ok' ? t('program.runOk') : status === 'error' ? t('program.runError') : t('program.runPartial'));
  const modeLabel = (mode?: string) => (mode === 'llm' ? t('program.modeLlm') : t('program.modeRules'));

  return (
    <ScreenContainer onRefresh={refetchAll} refreshing={refreshing}>
      <Header title={title} showBack />

      {/* Validation state + provenance */}
      <Card style={styles.headerCard}>
        <StatusBadge
          label={validationBadge.label}
          color={validationBadge.color}
          icon={<Ionicons name={validationBadge.icon} size={14} color={validationBadge.color} />}
          style={styles.validationBadge}
          textStyle={styles.validationBadgeText}
        />
        {validation?.status === 'applied' && !validation.auto_applied && !!validation.validated_by && (
          <Text style={[typography.caption, { color: colors.textSecondary, textAlign, marginTop: 6 }]}>
            {t('program.validatedBy', { name: validation.validated_by })}
          </Text>
        )}
        {!!program.generated_at && (
          <Text style={[typography.caption, { color: colors.textSecondary, textAlign, marginTop: 6 }]}>
            {t('program.generatedAt', { date: formatDateTime(program.generated_at) })}
          </Text>
        )}
        {!!program.source && (
          <Text style={[typography.tiny, { color: colors.textMuted, textAlign, marginTop: 4 }]}>
            {t('program.sourceLabel')}{' : '}{program.source}
          </Text>
        )}
      </Card>

      {!!program.fallback && (
        <View style={[styles.notice, { backgroundColor: colors.infoLight, borderRadius: radii.lg, flexDirection, marginTop: spacing.sm }]}>
          <Ionicons name="information-circle-outline" size={18} color={colors.info} style={styles.noticeIcon} />
          <Text style={[typography.caption, { color: colors.textPrimary, textAlign, flex: 1 }]}>
            {t('program.fallbackNotice')}
          </Text>
        </View>
      )}

      {fromCache && (
        <View style={[styles.notice, { backgroundColor: colors.warningLight, borderRadius: radii.lg, flexDirection, marginTop: spacing.sm }]}>
          <Ionicons name="cloud-offline-outline" size={18} color={colors.warning} style={styles.noticeIcon} />
          <Text style={[typography.caption, { color: colors.textPrimary, textAlign, flex: 1 }]}>
            {t('hospitalLink.offlineHint')}
          </Text>
        </View>
      )}

      {warnings.length > 0 && (
        <Card variant="outlined" style={{ marginTop: spacing.sm, borderColor: colors.warning }}>
          {bulletList(t('program.warningsTitle'), warnings, colors.warning, 'alert-circle-outline')}
        </Card>
      )}

      {/* Nutrition */}
      {sectionTitle('nutrition-outline', t('program.nutritionTitle'), colors.secondary)}
      <Card>
        {nutrition ? (
          <>
            {field(t('program.planType'), nutrition.plan_type)}
            {bulletList(t('program.recommended'), nutrition.recommended_foods, colors.success, 'checkmark-circle-outline')}
            {bulletList(t('program.avoid'), nutrition.foods_to_avoid, colors.error, 'close-circle-outline')}
            {!!nutrition.meals && Object.keys(nutrition.meals).length > 0 && (
              <View style={styles.field}>
                <Text style={[typography.captionBold, { color: colors.textSecondary, textAlign, marginBottom: 4 }]}>
                  {t('program.meals')}
                </Text>
                {Object.entries(nutrition.meals).map(([key, value]) => (
                  <View key={key} style={styles.mealRow}>
                    <Text style={[typography.captionBold, { color: colors.textPrimary, textAlign }]}>{mealLabel(key)}</Text>
                    <Text style={[typography.body, { color: colors.textSecondary, textAlign }]}>{String(value ?? '')}</Text>
                  </View>
                ))}
              </View>
            )}
            {typeof nutrition.hydration_ml_daily === 'number' && field(t('program.hydration'), t('program.hydrationValue', { value: nutrition.hydration_ml_daily }))}
            {typeof nutrition.calories_target === 'number' && field(t('program.calories'), t('program.caloriesValue', { value: nutrition.calories_target }))}
            {bulletList(t('program.rules'), nutrition.rules, colors.textSecondary, 'ellipse-outline')}
            {field(t('program.notes'), nutrition.notes)}
            <SourceConfidence source={nutrition.source} confidence={nutrition.confidence} />
          </>
        ) : (
          <Text style={[typography.body, { color: colors.textSecondary, textAlign }]}>{t('program.noNutrition')}</Text>
        )}
      </Card>

      {/* Physical activity */}
      {sectionTitle('walk-outline', t('program.activityTitle'), colors.primary)}
      <Card>
        {activity ? (
          <>
            {!!activity.activity_name && (
              <Text style={[typography.subtitle, { color: colors.textPrimary, textAlign, fontWeight: '700' }]}>
                {activity.activity_name}
              </Text>
            )}
            {typeof activity.duration_minutes === 'number' && field(t('program.duration'), t('program.durationValue', { value: activity.duration_minutes }))}
            {field(t('program.intensity'), intensityLabel(activity.intensity))}
            {typeof activity.frequency_per_week === 'number' && field(t('program.frequency'), t('program.frequencyValue', { value: activity.frequency_per_week }))}
            {hasItems(activity.scheduled_days) && field(t('program.scheduledDays'), activity.scheduled_days.map(dayLabel).join(isRTL ? '، ' : ', '))}
            {field(t('program.instructions'), activity.instructions)}
            {bulletList(t('program.contraindications'), activity.contraindications, colors.error, 'close-circle-outline')}
            <SourceConfidence source={activity.source} confidence={activity.confidence} />
          </>
        ) : (
          <Text style={[typography.body, { color: colors.textSecondary, textAlign }]}>{t('program.noActivity')}</Text>
        )}
      </Card>

      {/* Lifestyle habits */}
      {sectionTitle('leaf-outline', t('program.habitsTitle'), colors.accent)}
      {habits.length === 0 ? (
        <Card>
          <Text style={[typography.body, { color: colors.textSecondary, textAlign }]}>{t('program.noHabits')}</Text>
        </Card>
      ) : habits.map((habit, index) => {
        const category = categoryOf(String(habit.category ?? 'other'));
        return (
          <Card key={habit.key || `habit-${index}`} style={styles.habitCard}>
            <View style={[styles.habitHeader, { flexDirection }]}>
              <View style={[styles.habitIcon, { backgroundColor: colors.primaryLight, borderRadius: radii.md }]}>
                <Ionicons name={HABIT_ICONS[category]} size={18} color={colors.primary} />
              </View>
              <View style={styles.habitText}>
                <Text style={[typography.tiny, { color: colors.textMuted, textAlign }]}>
                  {t(`program.categories.${category}`)}
                </Text>
                <Text style={[typography.bodyBold, { color: colors.textPrimary, textAlign }]}>{habit.title}</Text>
              </View>
            </View>
            {!!habit.detail && (
              <Text style={[typography.body, { color: colors.textSecondary, textAlign, marginTop: 6 }]}>{habit.detail}</Text>
            )}
            <SourceConfidence source={habit.source} confidence={habit.confidence} />
          </Card>
        );
      })}

      {/* Medications: the schedule only ever comes from the prescription */}
      {sectionTitle('medkit-outline', t('program.medicationsTitle'), colors.primary)}
      <Card onPress={() => router.push('/(tabs)/treatment')}>
        <View style={[styles.habitHeader, { flexDirection }]}>
          <View style={styles.habitText}>
            <Text style={[typography.bodyBold, { color: colors.textPrimary, textAlign }]}>
              {t('program.medicationsCount', { value: medications?.count ?? 0 })}
            </Text>
            <Text style={[typography.body, { color: colors.textSecondary, textAlign, marginTop: 2 }]}>
              {medications?.next_dose?.name
                ? t('program.nextDose', { name: medications.next_dose.name, time: formatTime(medications.next_dose.time) })
                : t('program.noNextDose')}
            </Text>
          </View>
          <Ionicons name={isRTL ? 'chevron-back' : 'chevron-forward'} size={20} color={colors.textMuted} />
        </View>
        <View style={[styles.notice, { backgroundColor: colors.primaryLight, borderRadius: radii.md, flexDirection, marginTop: spacing.md }]}>
          <Ionicons name="shield-checkmark-outline" size={16} color={colors.primary} style={styles.noticeIcon} />
          <Text style={[typography.caption, { color: colors.primaryDark, textAlign, flex: 1 }]}>
            {t('program.scheduleFromPrescription')}
          </Text>
        </View>
        {!!medications?.source && <SourceConfidence source={medications.source} />}
      </Card>

      {/* Adherence */}
      {!!adherence && (adherencePercent !== null || !!adherence.message) && (
        <Card style={{ marginTop: spacing.sm }}>
          <View style={[styles.habitHeader, { flexDirection }]}>
            <Ionicons name="stats-chart-outline" size={18} color={colors.secondary} style={styles.sectionIcon} />
            <View style={styles.habitText}>
              <Text style={[typography.captionBold, { color: colors.textSecondary, textAlign }]}>
                {t('program.adherenceTitle')}
                {adherencePercent !== null ? `${' · '}${t('program.adherenceRate', { rate: adherencePercent })}` : ''}
              </Text>
              {!!adherence.message && (
                <Text style={[typography.body, { color: colors.textPrimary, textAlign, marginTop: 2 }]}>{adherence.message}</Text>
              )}
              {(adherence.missed_streak ?? 0) > 0 && (
                <Text style={[typography.caption, { color: colors.warning, textAlign, marginTop: 2 }]}>
                  {t('program.missedStreak', { value: adherence.missed_streak })}
                </Text>
              )}
            </View>
          </View>
        </Card>
      )}

      {/* Agent journal */}
      <View style={{ marginTop: spacing.lg }}>
        <ListItem
          title={t('program.journalLink')}
          subtitle={t('program.journalSubtitle')}
          leftIcon={<Ionicons name="receipt-outline" size={22} color={colors.accent} />}
          rightElement={<Ionicons name={journalOpen ? 'chevron-up' : 'chevron-down'} size={20} color={colors.textMuted} />}
          onPress={() => setJournalOpen((open) => !open)}
        />
        {journalOpen && (
          <View style={{ marginTop: spacing.xs }}>
            {runsQuery.isLoading && <ActivityIndicator color={colors.primary} style={{ marginVertical: spacing.md }} />}
            {runsQuery.isError && runs.length === 0 && (
              <TouchableOpacity accessibilityRole="button" onPress={() => { void runsQuery.refetch(); }} style={{ padding: spacing.md }}>
                <Text style={[typography.caption, { color: colors.textSecondary, textAlign }]}>
                  {t('program.journalError')}{' '}
                  <Text style={{ color: colors.primary, fontWeight: '700' }}>{t('common.retry')}</Text>
                </Text>
              </TouchableOpacity>
            )}
            {!runsQuery.isLoading && !runsQuery.isError && runs.length === 0 && (
              <Text style={[typography.caption, { color: colors.textSecondary, textAlign, padding: spacing.md }]}>
                {t('program.journalEmpty')}
              </Text>
            )}
            {runs.map((run, index) => (
              <Card key={run.id || `run-${index}`} variant="outlined" style={styles.runCard}>
                <View style={[styles.runHeader, { flexDirection }]}>
                  <Text style={[typography.captionBold, { color: colors.textPrimary, textAlign, flex: 1 }]}>
                    {formatDateTime(run.started_at)}
                  </Text>
                  <StatusBadge label={runLabel(run.status)} color={runTone(run.status)} size="sm" />
                </View>
                <Text style={[typography.tiny, { color: colors.textMuted, textAlign, marginTop: 4 }]}>
                  {t('program.triggerLabel')}{' : '}{run.trigger}{' · '}{t('program.modeLabel')}{' : '}{modeLabel(run.mode)}
                </Text>
                {!!run.summary && (
                  <Text style={[typography.caption, { color: colors.textSecondary, textAlign, marginTop: 4 }]}>{run.summary}</Text>
                )}
                {hasItems(run.steps) && run.steps.map((step, stepIndex) => (
                  <View key={`${stepIndex}-${step.name}`} style={[styles.stepRow, { flexDirection }]}>
                    <Ionicons
                      name={step.status === 'ok' ? 'checkmark-circle' : step.status === 'error' ? 'close-circle' : 'remove-circle-outline'}
                      size={14}
                      color={step.status === 'ok' ? colors.success : step.status === 'error' ? colors.error : colors.textMuted}
                      style={styles.bulletIcon}
                    />
                    <Text style={[typography.tiny, { color: colors.textSecondary, textAlign, flex: 1 }]}>
                      <Text style={{ fontWeight: '700', color: colors.textPrimary }}>{step.name}</Text>
                      {' · '}{stepLabel(step.status)}{step.detail ? `${' — '}${step.detail}` : ''}
                    </Text>
                  </View>
                ))}
              </Card>
            ))}
          </View>
        )}
      </View>

      {!!link?.last_sync_at && (
        <Text style={[typography.tiny, { color: colors.textMuted, textAlign: 'center', marginTop: spacing.base }]}>
          {t('program.lastSync', { date: formatDate(link.last_sync_at) })}
        </Text>
      )}
    </ScreenContainer>
  );
};

const styles = StyleSheet.create({
  headerCard: {
    marginVertical: 6,
  },
  validationBadge: {
    alignSelf: 'stretch',
    justifyContent: 'flex-start',
    paddingVertical: 6,
  },
  validationBadgeText: {
    flexShrink: 1,
  },
  notice: {
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  noticeIcon: {
    marginHorizontal: 6,
  },
  sectionTitle: {
    alignItems: 'center',
  },
  sectionIcon: {
    marginHorizontal: 6,
  },
  field: {
    marginVertical: 6,
  },
  bulletRow: {
    alignItems: 'flex-start',
    marginVertical: 2,
  },
  bulletIcon: {
    marginHorizontal: 6,
    marginTop: 3,
  },
  mealRow: {
    marginVertical: 4,
  },
  habitCard: {
    marginVertical: 4,
  },
  habitHeader: {
    alignItems: 'center',
  },
  habitIcon: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 4,
  },
  habitText: {
    flex: 1,
    paddingHorizontal: 6,
  },
  runCard: {
    marginVertical: 4,
  },
  runHeader: {
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  stepRow: {
    alignItems: 'flex-start',
    marginTop: 4,
  },
});
