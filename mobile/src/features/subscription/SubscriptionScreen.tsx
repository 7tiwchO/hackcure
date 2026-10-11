import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTheme } from '../../theme';
import { useRTL } from '../../i18n/RTLContext';
import { subscriptionApi } from '../../services/api/subscription';
import { CachedResult, fetchWithOfflineCache, writeOfflineCache } from '../../utils/offlineCache';
import { formatDate } from '../../utils/dateUtils';
import { Subscription, SubscriptionPlan } from '../../types';
import { ScreenContainer } from '../../components/layout/ScreenContainer';
import { Header } from '../../components/layout/Header';
import { Card } from '../../components/ui/Card';
import { PrimaryButton } from '../../components/ui/PrimaryButton';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { CardSkeleton } from '../../components/ui/LoadingSkeleton';
import { ErrorState } from '../../components/ui/ErrorState';

const CACHE_NAME = 'subscription';
const QUERY_KEY = ['subscription'];
const PLANS: SubscriptionPlan[] = ['monthly', 'quarterly'];

export const SubscriptionScreen: React.FC = () => {
  const queryClient = useQueryClient();
  const { colors, typography, spacing, radii } = useTheme();
  const { flexDirection, textAlign } = useRTL();
  const { t } = useTranslation();
  const [plan, setPlan] = useState<SubscriptionPlan>('monthly');
  const [activateError, setActivateError] = useState<string | null>(null);

  const { data: result, isLoading, isError, refetch, isRefetching } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => fetchWithOfflineCache<Subscription>(CACHE_NAME, subscriptionApi.get),
    retry: 1,
  });

  const activateMutation = useMutation({
    mutationFn: subscriptionApi.activate,
    onSuccess: (subscription) => {
      setActivateError(null);
      queryClient.setQueryData<CachedResult<Subscription>>(QUERY_KEY, { data: subscription, fromCache: false, cachedAt: null });
      void writeOfflineCache(CACHE_NAME, subscription);
      queryClient.invalidateQueries({ queryKey: ['hospital-link'] });
    },
    onError: (error) => {
      const offline = !(error as { response?: unknown } | null)?.response;
      setActivateError(offline ? t('common.serverUnavailable') : t('subscription.activateError'));
    },
  });

  const title = t('subscription.title');

  if (isLoading && !result) {
    return (
      <ScreenContainer>
        <Header title={title} showBack />
        <CardSkeleton />
      </ScreenContainer>
    );
  }

  if (isError && !result) {
    return (
      <ScreenContainer onRefresh={refetch} refreshing={isRefetching}>
        <Header title={title} showBack />
        <ErrorState title={t('subscription.loadError')} onRetry={refetch} />
      </ScreenContainer>
    );
  }

  const subscription = result?.data;
  const fromCache = !!result?.fromCache;
  const isActive = subscription?.active ?? subscription?.status === 'active';
  const status = isActive ? 'active' : subscription?.status === 'expired' ? 'expired' : 'none';

  const badge = status === 'active'
    ? { label: t('subscription.statusActive'), color: colors.success, icon: 'checkmark-circle-outline' as const }
    : status === 'expired'
      ? { label: t('subscription.statusExpired'), color: colors.warning, icon: 'time-outline' as const }
      : { label: t('subscription.statusNone'), color: colors.textMuted, icon: 'remove-circle-outline' as const };

  const planLabel = (value?: string | null) => {
    if (value === 'monthly') return t('subscription.planMonthly');
    if (value === 'quarterly') return t('subscription.planQuarterly');
    return value || '—';
  };

  const hospitalShare = subscription?.hospital_share_pct;
  const teamShare = subscription?.team_share_pct;
  const hasShares = typeof hospitalShare === 'number' && typeof teamShare === 'number';

  const infoRow = (label: string, value: string) => (
    <View style={[styles.infoRow, { flexDirection }]}>
      <Text style={[typography.caption, { color: colors.textMuted, textAlign }]}>{label}</Text>
      <Text style={[typography.captionBold, { color: colors.textPrimary, textAlign, flexShrink: 1 }]}>{value}</Text>
    </View>
  );

  return (
    <ScreenContainer onRefresh={refetch} refreshing={isRefetching}>
      <Header title={title} showBack />

      {fromCache && (
        <View style={[styles.notice, { backgroundColor: colors.warningLight, borderRadius: radii.lg, flexDirection, marginBottom: spacing.sm }]}>
          <Ionicons name="cloud-offline-outline" size={18} color={colors.warning} style={styles.icon} />
          <Text style={[typography.caption, { color: colors.textPrimary, textAlign, flex: 1 }]}>
            {t('hospitalLink.offlineHint')}
          </Text>
        </View>
      )}

      <Card style={styles.card}>
        <View style={[styles.badgeRow, { flexDirection }]}>
          <StatusBadge
            label={badge.label}
            color={badge.color}
            icon={<Ionicons name={badge.icon} size={14} color={badge.color} />}
          />
          {!!subscription?.demo && (
            <StatusBadge label={t('subscription.demoBadge')} color={colors.info} size="sm" />
          )}
        </View>

        {status !== 'none' && (
          <View style={{ marginTop: spacing.md }}>
            {infoRow(t('subscription.plan'), planLabel(subscription?.plan))}
            {infoRow(t('subscription.hospital'), subscription?.hospital_name || '—')}
            {infoRow(t('subscription.startDate'), subscription?.start_date ? formatDate(subscription.start_date) : '—')}
            {infoRow(t('subscription.endDate'), subscription?.end_date ? formatDate(subscription.end_date) : '—')}
            {infoRow(
              t('subscription.price'),
              typeof subscription?.price_tnd === 'number' ? t('subscription.priceValue', { price: subscription.price_tnd }) : '—',
            )}
          </View>
        )}

        {status === 'none' && (
          <>
            <Text style={[typography.body, { color: colors.textSecondary, textAlign, marginTop: spacing.md }]}>
              {t('subscription.inactiveBody')}
            </Text>
            {!!subscription?.hospital_name && (
              <View style={{ marginTop: spacing.sm }}>
                {infoRow(t('subscription.hospital'), subscription.hospital_name)}
              </View>
            )}
          </>
        )}
      </Card>

      {hasShares && (
        <Card variant="outlined" style={[styles.card, { marginTop: spacing.sm }]}>
          <View style={[styles.shareHeader, { flexDirection }]}>
            <Ionicons name="pie-chart-outline" size={18} color={colors.secondary} style={styles.icon} />
            <Text style={[typography.captionBold, { color: colors.textSecondary, textAlign, flex: 1 }]}>
              {t('subscription.revenueShareTitle')}
            </Text>
          </View>
          <Text style={[typography.body, { color: colors.textPrimary, textAlign, marginTop: 6 }]}>
            {t('subscription.revenueShare', { hospital: hospitalShare, team: teamShare })}
          </Text>
          <View style={[styles.shareBar, { backgroundColor: colors.accent, borderRadius: radii.full, flexDirection, marginTop: spacing.sm }]}>
            <View style={{ flex: Math.max(0, hospitalShare), backgroundColor: colors.secondary }} />
            <View style={{ flex: Math.max(0, teamShare) }} />
          </View>
        </Card>
      )}

      {!isActive && (
        <Card style={[styles.card, { marginTop: spacing.sm }]}>
          <Text style={[typography.captionBold, { color: colors.textSecondary, textAlign, marginBottom: spacing.sm }]}>
            {t('subscription.choosePlan')}
          </Text>
          <View style={[styles.planRow, { flexDirection }]}>
            {PLANS.map((option) => {
              const selected = option === plan;
              return (
                <TouchableOpacity
                  key={option}
                  activeOpacity={0.7}
                  accessibilityRole="radio"
                  accessibilityState={{ selected }}
                  onPress={() => setPlan(option)}
                  style={[styles.planChip, {
                    backgroundColor: selected ? colors.primaryLight : colors.card,
                    borderColor: selected ? colors.primary : colors.cardBorder,
                    borderRadius: radii.lg,
                  }]}
                >
                  <Text style={[typography.captionBold, { color: selected ? colors.primary : colors.textPrimary }]}>
                    {planLabel(option)}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
          {!!activateError && (
            <Text accessibilityRole="alert" style={[typography.caption, { color: colors.error, textAlign, marginTop: spacing.sm }]}>
              {activateError}
            </Text>
          )}
          <PrimaryButton
            title={t('subscription.activate')}
            onPress={() => activateMutation.mutate(plan)}
            loading={activateMutation.isPending}
            style={{ marginTop: spacing.base }}
          />
        </Card>
      )}

      <Text style={[typography.tiny, { color: colors.textMuted, textAlign: 'center', marginTop: spacing.base }]}>
        {t('subscription.noPayment')}
      </Text>
    </ScreenContainer>
  );
};

const styles = StyleSheet.create({
  card: {
    marginVertical: 6,
  },
  notice: {
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  icon: {
    marginHorizontal: 6,
  },
  badgeRow: {
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: 8,
  },
  infoRow: {
    justifyContent: 'space-between',
    alignItems: 'center',
    marginVertical: 4,
    gap: 12,
  },
  shareHeader: {
    alignItems: 'center',
  },
  shareBar: {
    height: 8,
    overflow: 'hidden',
  },
  planRow: {
    gap: 10,
  },
  planChip: {
    flex: 1,
    minHeight: 44,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
});
