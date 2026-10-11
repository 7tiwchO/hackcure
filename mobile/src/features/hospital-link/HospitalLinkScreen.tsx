import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTheme } from '../../theme';
import { useRTL } from '../../i18n/RTLContext';
import { hospitalLinkApi } from '../../services/api/hospitalLink';
import { CachedResult, clearOfflineCache, fetchWithOfflineCache, writeOfflineCache } from '../../utils/offlineCache';
import { formatDate, formatDateTime } from '../../utils/dateUtils';
import { HospitalLinkStatus } from '../../types';
import { ScreenContainer } from '../../components/layout/ScreenContainer';
import { Header } from '../../components/layout/Header';
import { Card } from '../../components/ui/Card';
import { TextInput } from '../../components/ui/TextInput';
import { PrimaryButton } from '../../components/ui/PrimaryButton';
import { SecondaryButton } from '../../components/ui/SecondaryButton';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { CardSkeleton } from '../../components/ui/LoadingSkeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { ConfirmationDialog } from '../../components/ui/ConfirmationDialog';

const CACHE_NAME = 'hospital-link';
const QUERY_KEY = ['hospital-link'];
const STAY_ID_PATTERN = /^PAT-\d{4,}$/;

const statusOf = (error: unknown) => (error as { response?: { status?: number } } | null)?.response?.status;

const isValidBirthDate = (value: string) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  if (!Number.isFinite(parsed.getTime())) return false;
  // Rejects impossible dates such as 2024-02-31 and dates in the future.
  return parsed.toISOString().slice(0, 10) === value && parsed.getTime() <= Date.now();
};

export const HospitalLinkScreen: React.FC = () => {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { colors, typography, spacing, radii } = useTheme();
  const { flexDirection, textAlign } = useRTL();
  const { t } = useTranslation();

  const [stayId, setStayId] = useState('');
  const [birthDate, setBirthDate] = useState('');
  const [consent, setConsent] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [needsSubscription, setNeedsSubscription] = useState(false);
  const [syncOffline, setSyncOffline] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [withdrawVisible, setWithdrawVisible] = useState(false);

  const { data: result, isLoading, isError, refetch, isRefetching } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => fetchWithOfflineCache<HospitalLinkStatus>(CACHE_NAME, hospitalLinkApi.getStatus),
    retry: 1,
  });

  const applyStatus = (status: HospitalLinkStatus) => {
    queryClient.setQueryData<CachedResult<HospitalLinkStatus>>(QUERY_KEY, { data: status, fromCache: false, cachedAt: null });
    void writeOfflineCache(CACHE_NAME, status);
    queryClient.invalidateQueries({ queryKey: ['care-program'] });
    queryClient.invalidateQueries({ queryKey: ['agent-runs'] });
  };

  const linkMutation = useMutation({
    mutationFn: hospitalLinkApi.link,
    onSuccess: (status) => {
      setFormError(null);
      setNeedsSubscription(false);
      setSyncOffline(false);
      applyStatus(status);
      // Medication reminders may have been regenerated from the synchronised prescription.
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['todayDoses'] });
    },
    onError: (error) => {
      const status = statusOf(error);
      setNeedsSubscription(status === 402);
      if (status === 402) setFormError(t('hospitalLink.subscriptionRequired'));
      else if (status === 404) setFormError(t('hospitalLink.notFound'));
      else if (status === 503) setFormError(t('hospitalLink.unreachable'));
      else if (status === 400 || status === 422) setFormError(t('hospitalLink.badRequest'));
      else if (status === undefined) setFormError(t('common.serverUnavailable'));
      else setFormError(t('common.error'));
    },
  });

  const syncMutation = useMutation({
    mutationFn: hospitalLinkApi.sync,
    onSuccess: (status) => {
      setActionError(null);
      setSyncOffline(false);
      setNeedsSubscription(false);
      applyStatus(status);
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['todayDoses'] });
    },
    onError: (error) => {
      const status = statusOf(error);
      if (status === undefined || status === 503) {
        // Nothing is lost: the last synchronised state stays on screen.
        setSyncOffline(true);
        setActionError(null);
      } else if (status === 402) {
        setNeedsSubscription(true);
        setActionError(t('hospitalLink.subscriptionRequired'));
      } else {
        setActionError(t('hospitalLink.syncFailed'));
      }
    },
  });

  const unlinkMutation = useMutation({
    mutationFn: hospitalLinkApi.unlink,
    onSuccess: async () => {
      setWithdrawVisible(false);
      setActionError(null);
      setSyncOffline(false);
      setStayId('');
      setBirthDate('');
      setConsent(false);
      setSubmitted(false);
      await clearOfflineCache(CACHE_NAME, 'care-program', 'agent-runs');
      queryClient.removeQueries({ queryKey: ['care-program'] });
      queryClient.removeQueries({ queryKey: ['agent-runs'] });
      await queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
    onError: (error) => {
      setWithdrawVisible(false);
      setActionError(statusOf(error) === undefined ? t('common.serverUnavailable') : t('hospitalLink.withdrawFailed'));
    },
  });

  const normalizedStayId = stayId.trim().toUpperCase();
  const stayIdError = submitted && !STAY_ID_PATTERN.test(normalizedStayId) ? t('hospitalLink.stayIdInvalid') : undefined;
  const birthDateError = submitted && !isValidBirthDate(birthDate.trim()) ? t('hospitalLink.dobInvalid') : undefined;
  const consentError = submitted && !consent;

  const handleSubmit = () => {
    setSubmitted(true);
    setFormError(null);
    if (!STAY_ID_PATTERN.test(normalizedStayId) || !isValidBirthDate(birthDate.trim()) || !consent) return;
    linkMutation.mutate({ pseudonym: normalizedStayId, date_of_birth: birthDate.trim(), consent: true });
  };

  const title = t('hospitalLink.title');

  if (isLoading && !result) {
    return (
      <ScreenContainer>
        <Header title={title} showBack />
        <CardSkeleton />
        <CardSkeleton />
      </ScreenContainer>
    );
  }

  if (isError && !result) {
    return (
      <ScreenContainer onRefresh={refetch} refreshing={isRefetching}>
        <Header title={title} showBack />
        <ErrorState title={t('hospitalLink.loadError')} onRetry={refetch} />
      </ScreenContainer>
    );
  }

  const link = result?.data;
  const fromCache = !!result?.fromCache;
  const linked = !!link?.linked;
  const documents = Array.isArray(link?.documents) ? link.documents : [];
  const subscriptionInactive = needsSubscription || link?.subscription_active === false;

  const effectiveStatus = fromCache || syncOffline ? 'offline' : link?.last_sync_status ?? null;
  const statusBadge = effectiveStatus === 'ok'
    ? { label: t('hospitalLink.statusOk'), color: colors.success, icon: 'checkmark-circle-outline' as const }
    : effectiveStatus === 'offline'
      ? { label: t('hospitalLink.statusOffline'), color: colors.warning, icon: 'cloud-offline-outline' as const }
      : effectiveStatus === 'error'
        ? { label: t('hospitalLink.statusError'), color: colors.error, icon: 'alert-circle-outline' as const }
        : { label: t('hospitalLink.statusUnknown'), color: colors.textMuted, icon: 'time-outline' as const };

  const documentLabel = (type?: string) => {
    if (type === 'PRESCRIPTION') return t('hospitalLink.docPrescription');
    if (type === 'DOCTOR_REPORT') return t('hospitalLink.docDoctorReport');
    if (type === 'MEDICAL_RECORD') return t('hospitalLink.docMedicalRecord');
    return t('hospitalLink.docOther');
  };
  const documentIcon = (type?: string): keyof typeof Ionicons.glyphMap => (
    type === 'PRESCRIPTION' ? 'medkit-outline' : type === 'DOCTOR_REPORT' ? 'document-text-outline' : 'folder-open-outline'
  );

  const sharedLine = (icon: keyof typeof Ionicons.glyphMap, text: string, color: string) => (
    <View style={[styles.sharedRow, { flexDirection }]}>
      <Ionicons name={icon} size={16} color={color} style={styles.rowIcon} />
      <Text style={[typography.caption, { color: colors.textSecondary, textAlign, flex: 1 }]}>{text}</Text>
    </View>
  );

  const infoRow = (label: string, value: string) => (
    <View style={[styles.infoRow, { flexDirection }]}>
      <Text style={[typography.caption, { color: colors.textMuted, textAlign }]}>{label}</Text>
      <Text style={[typography.captionBold, { color: colors.textPrimary, textAlign, flexShrink: 1 }]}>{value}</Text>
    </View>
  );

  const subscriptionNotice = subscriptionInactive && (
    <Card variant="outlined" style={{ marginTop: spacing.sm, borderColor: colors.warning, backgroundColor: colors.warningLight }}>
      <View style={[styles.sharedRow, { flexDirection }]}>
        <Ionicons name="card-outline" size={18} color={colors.warning} style={styles.rowIcon} />
        <Text style={[typography.caption, { color: colors.textPrimary, textAlign, flex: 1 }]}>
          {t('hospitalLink.subscriptionRequired')}
        </Text>
      </View>
      <SecondaryButton
        title={t('hospitalLink.goToSubscription')}
        onPress={() => router.push('/subscription')}
        style={{ marginTop: spacing.sm }}
      />
    </Card>
  );

  return (
    <ScreenContainer onRefresh={refetch} refreshing={isRefetching}>
      <Header title={title} showBack />

      {/* What is shared */}
      <Card style={styles.card}>
        <Text style={[typography.h4, { color: colors.textPrimary, textAlign }]}>{t('hospitalLink.introTitle')}</Text>
        <Text style={[typography.body, { color: colors.textSecondary, textAlign, marginTop: 6, marginBottom: 6 }]}>
          {t('hospitalLink.introBody')}
        </Text>
        {sharedLine('finger-print-outline', t('hospitalLink.sharedPseudonym'), colors.primary)}
        {sharedLine('eye-off-outline', t('hospitalLink.sharedNoName'), colors.success)}
        {sharedLine('hand-left-outline', t('hospitalLink.sharedWithdraw'), colors.secondary)}
      </Card>

      {fromCache && (
        <View style={[styles.notice, { backgroundColor: colors.warningLight, borderRadius: radii.lg, flexDirection, marginTop: spacing.sm }]}>
          <Ionicons name="cloud-offline-outline" size={18} color={colors.warning} style={styles.rowIcon} />
          <Text style={[typography.caption, { color: colors.textPrimary, textAlign, flex: 1 }]}>
            {t('hospitalLink.offlineHint')}
          </Text>
        </View>
      )}

      {subscriptionNotice}

      {!linked ? (
        <Card style={[styles.card, { marginTop: spacing.sm }]}>
          <TextInput
            label={t('hospitalLink.stayId')}
            placeholder={t('hospitalLink.stayIdPlaceholder')}
            value={stayId}
            onChangeText={(value) => setStayId(value.toUpperCase())}
            autoCapitalize="characters"
            autoCorrect={false}
            maxLength={12}
            error={stayIdError}
            leftIcon={<Ionicons name="finger-print-outline" size={18} color={colors.textMuted} />}
          />
          <Text style={[typography.tiny, { color: colors.textMuted, textAlign, marginBottom: 4 }]}>
            {t('hospitalLink.stayIdHint')}
          </Text>
          <TextInput
            label={t('hospitalLink.birthDate')}
            placeholder={t('hospitalLink.birthDatePlaceholder')}
            value={birthDate}
            onChangeText={setBirthDate}
            keyboardType="numbers-and-punctuation"
            autoCorrect={false}
            maxLength={10}
            error={birthDateError}
            leftIcon={<Ionicons name="calendar-outline" size={18} color={colors.textMuted} />}
          />

          <TouchableOpacity
            activeOpacity={0.7}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: consent }}
            onPress={() => setConsent((value) => !value)}
            style={[styles.consentRow, { flexDirection, marginTop: spacing.sm }]}
          >
            <Ionicons
              name={consent ? 'checkbox' : 'square-outline'}
              size={24}
              color={consent ? colors.primary : consentError ? colors.error : colors.textMuted}
              style={styles.rowIcon}
            />
            <Text style={[typography.caption, { color: colors.textPrimary, textAlign, flex: 1 }]}>
              {t('hospitalLink.consentLabel')}
            </Text>
          </TouchableOpacity>
          {consentError && (
            <Text style={[typography.tiny, { color: colors.error, textAlign, marginTop: 4 }]}>
              {t('hospitalLink.consentRequired')}
            </Text>
          )}

          {!!formError && (
            <Text accessibilityRole="alert" style={[typography.caption, { color: colors.error, textAlign, marginTop: spacing.md }]}>
              {formError}
            </Text>
          )}

          <PrimaryButton
            title={t('hospitalLink.submit')}
            onPress={handleSubmit}
            loading={linkMutation.isPending}
            icon={<Ionicons name="link-outline" size={18} color="#FFFFFF" />}
            style={{ marginTop: spacing.base }}
          />
        </Card>
      ) : (
        <>
          <Card style={[styles.card, { marginTop: spacing.sm }]}>
            <View style={[styles.linkedHeader, { flexDirection }]}>
              <Text style={[typography.h4, { color: colors.textPrimary, textAlign, flex: 1 }]}>
                {t('hospitalLink.linkedTitle')}
              </Text>
              <Ionicons name="link" size={20} color={colors.success} />
            </View>
            {infoRow(t('hospitalLink.pseudonym'), link?.pseudonym || '—')}
            {infoRow(t('hospitalLink.linkedAt'), link?.linked_at ? formatDate(link.linked_at) : '—')}
            {infoRow(t('hospitalLink.lastSync'), link?.last_sync_at ? formatDateTime(link.last_sync_at) : t('hospitalLink.neverSynced'))}
            <StatusBadge
              label={statusBadge.label}
              color={statusBadge.color}
              icon={<Ionicons name={statusBadge.icon} size={14} color={statusBadge.color} />}
              style={styles.statusBadge}
              textStyle={styles.statusBadgeText}
            />
            {effectiveStatus === 'error' && !!link?.last_sync_error && (
              <Text style={[typography.tiny, { color: colors.textSecondary, textAlign, marginTop: 6 }]}>
                {link.last_sync_error}
              </Text>
            )}
            {!!actionError && (
              <Text accessibilityRole="alert" style={[typography.caption, { color: colors.error, textAlign, marginTop: spacing.sm }]}>
                {actionError}
              </Text>
            )}
            <PrimaryButton
              title={t('hospitalLink.syncNow')}
              onPress={() => syncMutation.mutate()}
              loading={syncMutation.isPending}
              icon={<Ionicons name="sync-outline" size={18} color="#FFFFFF" />}
              style={{ marginTop: spacing.base }}
            />
            <SecondaryButton
              title={t('hospitalLink.viewProgram')}
              onPress={() => router.push('/program')}
              variant="tint"
              style={{ marginTop: spacing.sm }}
            />
          </Card>

          <Text style={[typography.captionBold, { color: colors.textSecondary, textAlign, marginTop: spacing.lg, marginBottom: 8 }]}>
            {t('hospitalLink.documentsTitle')}
          </Text>
          {documents.length === 0 ? (
            <Card>
              <Text style={[typography.body, { color: colors.textSecondary, textAlign }]}>{t('hospitalLink.noDocuments')}</Text>
            </Card>
          ) : documents.map((document, index) => (
            <Card key={document.id || `document-${index}`} variant="outlined" style={styles.documentCard}>
              <View style={[styles.documentRow, { flexDirection }]}>
                <View style={[styles.documentIcon, { backgroundColor: colors.primaryLight, borderRadius: radii.md }]}>
                  <Ionicons name={documentIcon(document.type)} size={18} color={colors.primary} />
                </View>
                <View style={styles.documentText}>
                  <Text style={[typography.tiny, { color: colors.textMuted, textAlign }]}>{documentLabel(document.type)}</Text>
                  <Text style={[typography.bodyBold, { color: colors.textPrimary, textAlign }]}>{document.title}</Text>
                  {!!document.date && (
                    <Text style={[typography.caption, { color: colors.textSecondary, textAlign }]}>{formatDate(document.date)}</Text>
                  )}
                </View>
              </View>
            </Card>
          ))}

          <TouchableOpacity
            accessibilityRole="button"
            activeOpacity={0.7}
            onPress={() => setWithdrawVisible(true)}
            style={[styles.withdraw, { marginTop: spacing.xl }]}
          >
            <Text style={[typography.caption, { color: colors.textMuted, textDecorationLine: 'underline' }]}>
              {t('hospitalLink.withdraw')}
            </Text>
          </TouchableOpacity>
        </>
      )}

      <ConfirmationDialog
        visible={withdrawVisible}
        title={t('hospitalLink.withdrawTitle')}
        message={t('hospitalLink.withdrawMessage')}
        confirmText={t('hospitalLink.withdrawConfirm')}
        isDestructive
        loading={unlinkMutation.isPending}
        onConfirm={() => unlinkMutation.mutate()}
        onCancel={() => setWithdrawVisible(false)}
      />
    </ScreenContainer>
  );
};

const styles = StyleSheet.create({
  card: {
    marginVertical: 6,
  },
  sharedRow: {
    alignItems: 'flex-start',
    marginVertical: 3,
  },
  rowIcon: {
    marginHorizontal: 6,
  },
  notice: {
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  consentRow: {
    alignItems: 'flex-start',
    minHeight: 44,
  },
  linkedHeader: {
    alignItems: 'center',
    marginBottom: 8,
  },
  infoRow: {
    justifyContent: 'space-between',
    alignItems: 'center',
    marginVertical: 4,
    gap: 12,
  },
  statusBadge: {
    alignSelf: 'stretch',
    justifyContent: 'flex-start',
    paddingVertical: 6,
    marginTop: 8,
  },
  statusBadgeText: {
    flexShrink: 1,
  },
  documentCard: {
    marginVertical: 4,
  },
  documentRow: {
    alignItems: 'center',
  },
  documentIcon: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 4,
  },
  documentText: {
    flex: 1,
    paddingHorizontal: 6,
  },
  withdraw: {
    alignSelf: 'center',
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
});
