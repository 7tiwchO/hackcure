import React, { useMemo, useState } from 'react';
import { ActivityIndicator, Platform, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { PrescriptionItem, MedicationDose } from '../../types';
import { medicationsApi } from '../../services/api/medications';
import { useTheme } from '../../theme';
import { useRTL } from '../../i18n/RTLContext';

interface MedicationTrackerCardProps {
  medication: PrescriptionItem;
  doses: MedicationDose[];
  onPressMedication: () => void;
}

const dateKey = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const syncLocalStockReminder = async (medicationId: string, isLow: boolean, wasLow: boolean, title: string, body: string) => {
  if (Platform.OS === 'web') return;
  try {
    const Notifications = await import('expo-notifications');
    const storageKey = `@hackcure_stock_reminder_${medicationId}`;
    const existingId = await AsyncStorage.getItem(storageKey);
    if (!isLow) {
      if (existingId) await Notifications.cancelScheduledNotificationAsync(existingId);
      await AsyncStorage.removeItem(storageKey);
      return;
    }
    if (wasLow || existingId) return;
    const { status } = await Notifications.getPermissionsAsync();
    if (status !== 'granted') return;
    const id = await Notifications.scheduleNotificationAsync({
      content: { title, body, sound: true, data: { screen: '/treatment' } },
      trigger: null,
    });
    await AsyncStorage.setItem(storageKey, id);
  } catch {
    // The low-stock banner remains visible if local notifications are unavailable.
  }
};

export const MedicationTrackerCard: React.FC<MedicationTrackerCardProps> = ({ medication, doses, onPressMedication }) => {
  const { colors, spacing, radii, typography } = useTheme();
  const { flexDirection, textAlign, isRTL } = useRTL();
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [stock, setStock] = useState(medication.stock_remaining == null ? '' : String(medication.stock_remaining));
  const [threshold, setThreshold] = useState(String(medication.stock_reminder_threshold ?? 10));
  const [reminderEnabled, setReminderEnabled] = useState(Boolean(medication.stock_reminder_enabled));
  const [saveError, setSaveError] = useState(false);

  const week = useMemo(() => {
    const today = new Date();
    today.setHours(12, 0, 0, 0);
    return Array.from({ length: 7 }, (_, index) => {
      const day = new Date(today);
      day.setDate(today.getDate() - (6 - index));
      return day;
    });
  }, []);

  const medicationDoses = doses.filter((dose) => dose.prescription_item_id === medication.id);
  const updateStockMutation = useMutation({
    mutationFn: () => medicationsApi.updateStock(medication.id, {
      stock_remaining: stock.trim() === '' ? null : Number(stock),
      stock_reminder_enabled: reminderEnabled,
      stock_reminder_threshold: Number(threshold),
    }),
    onSuccess: async (updatedMedication) => {
      setSaveError(false);
      setStock(updatedMedication.stock_remaining == null ? '' : String(updatedMedication.stock_remaining));
      setThreshold(String(updatedMedication.stock_reminder_threshold ?? 10));
      setReminderEnabled(Boolean(updatedMedication.stock_reminder_enabled));
      const wasLow = Boolean(
        medication.stock_reminder_enabled
        && medication.stock_remaining != null
        && medication.stock_remaining <= (medication.stock_reminder_threshold ?? 10)
      );
      const isUpdatedLow = Boolean(
        updatedMedication.stock_reminder_enabled
        && updatedMedication.stock_remaining != null
        && updatedMedication.stock_remaining <= (updatedMedication.stock_reminder_threshold ?? 10)
      );
      await syncLocalStockReminder(
        medication.id,
        isUpdatedLow,
        wasLow,
        t('treatment.stockNotificationTitle'),
        t('treatment.stockNotificationBody'),
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['activePrescriptions'] }),
        queryClient.invalidateQueries({ queryKey: ['medications'] }),
        queryClient.invalidateQueries({ queryKey: ['medication', medication.id] }),
      ]);
    },
    onError: () => setSaveError(true),
  });

  const parsedStock = stock.trim() === '' ? null : Number(stock);
  const parsedThreshold = Number(threshold);
  const canSave = (parsedStock === null || (Number.isInteger(parsedStock) && parsedStock >= 0))
    && Number.isInteger(parsedThreshold) && parsedThreshold >= 1;
  const isLow = reminderEnabled && parsedStock !== null && Number.isInteger(parsedStock)
    && Number.isInteger(parsedThreshold) && parsedStock <= parsedThreshold;

  return (
    <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.cardBorder, borderRadius: radii.lg }]}>
      <TouchableOpacity accessibilityRole="button" onPress={onPressMedication} style={[styles.titleRow, { flexDirection }]}>
        <View style={[styles.icon, { backgroundColor: colors.primaryLight, borderRadius: radii.md }]}>
          <Ionicons name="medical-outline" size={19} color={colors.primary} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={[typography.bodyBold, { color: colors.textPrimary, textAlign }]}>{medication.medication_name}</Text>
          <Text style={[typography.tiny, { color: colors.textSecondary, textAlign }]}>{medication.dosage} · {medication.frequency}</Text>
        </View>
      </TouchableOpacity>

      <Text style={[typography.tiny, { color: colors.textSecondary, textAlign, marginBottom: 6 }]}>{t('treatment.weeklyProgress')}</Text>
      <View style={[styles.weekRow, { flexDirection }]}>
        {week.map((day) => {
          const key = dateKey(day);
          const dayDoses = medicationDoses.filter((dose) => dose.scheduled_date === key && dose.status !== 'CANCELLED');
          const taken = dayDoses.filter((dose) => dose.status === 'TAKEN_ON_TIME' || dose.status === 'TAKEN_LATE').length;
          const complete = dayDoses.length > 0 && taken === dayDoses.length;
          const missed = dayDoses.some((dose) => dose.status === 'MISSED');
          const stateColor = complete ? colors.success : missed ? colors.error : colors.textMuted;
          const label = new Intl.DateTimeFormat(i18n.language, { weekday: 'short' }).format(day);
          const isToday = key === dateKey(new Date());

          return (
            <View key={key} style={styles.dayColumn}>
              <Text style={[typography.tiny, { color: isToday ? colors.primary : colors.textSecondary }]} numberOfLines={1}>
                {label.replace('.', '')}
              </Text>
              <View style={[styles.dayStatus, {
                backgroundColor: complete ? colors.success : missed ? colors.errorLight : colors.inputBg,
                borderColor: isToday ? colors.primary : (complete ? colors.success : colors.cardBorder),
              }]}>
                {complete ? <Ionicons name="checkmark" size={16} color={colors.textInverse} />
                  : missed ? <Ionicons name="close" size={16} color={colors.error} />
                    : <Text style={[typography.tiny, { color: colors.textMuted }]}>{dayDoses.length ? '·' : '—'}</Text>}
              </View>
              <Text style={[typography.tiny, { color: stateColor }]}>
                {dayDoses.length ? `${taken}/${dayDoses.length}` : '—'}
              </Text>
            </View>
          );
        })}
      </View>

      <View style={[styles.divider, { backgroundColor: colors.cardBorder }]} />

      <View style={[styles.stockHeader, { flexDirection }]}>
        <View style={[styles.stockTitle, { flexDirection }]}>
          <Ionicons name="cube-outline" size={18} color={colors.primary} />
          <Text style={[typography.captionBold, { color: colors.textPrimary, marginHorizontal: 6 }]}>{t('treatment.stockTitle')}</Text>
        </View>
        <Switch
          accessibilityLabel={t('treatment.stockReminder')}
          value={reminderEnabled}
          onValueChange={setReminderEnabled}
          trackColor={{ false: colors.cardBorder, true: colors.success }}
        />
      </View>

      <Text style={[typography.tiny, { color: colors.textSecondary, textAlign, marginBottom: spacing.xs }]}>
        {t('treatment.stockManualNotice')}
      </Text>

      <View style={[styles.inputRow, { flexDirection }]}>
        <Text style={[typography.caption, { color: colors.textSecondary, flex: 1, textAlign }]}>{t('treatment.stockRemaining')}</Text>
        <TextInput
          accessibilityLabel={t('treatment.stockRemaining')}
          keyboardType="number-pad"
          value={stock}
          onChangeText={(value) => setStock(value.replace(/\D/g, '').slice(0, 6))}
          placeholder="—"
          placeholderTextColor={colors.textMuted}
          style={[styles.input, typography.caption, { backgroundColor: colors.inputBg, borderColor: colors.cardBorder, color: colors.textPrimary, borderRadius: radii.md, textAlign: isRTL ? 'right' : 'left' }]}
        />
        <Text style={[typography.tiny, { color: colors.textSecondary, marginHorizontal: 4 }]}>{t('treatment.stockUnits')}</Text>
      </View>

      <View style={[styles.inputRow, { flexDirection }]}>
        <Text style={[typography.caption, { color: colors.textSecondary, flex: 1, textAlign }]}>{t('treatment.stockThreshold')}</Text>
        <TextInput
          accessibilityLabel={t('treatment.stockThreshold')}
          keyboardType="number-pad"
          value={threshold}
          onChangeText={(value) => setThreshold(value.replace(/\D/g, '').slice(0, 6))}
          style={[styles.input, typography.caption, { backgroundColor: colors.inputBg, borderColor: colors.cardBorder, color: colors.textPrimary, borderRadius: radii.md, textAlign: isRTL ? 'right' : 'left' }]}
        />
        <Text style={[typography.tiny, { color: colors.textSecondary, marginHorizontal: 4 }]}>{t('treatment.stockUnits')}</Text>
      </View>

      {isLow && (
        <View style={[styles.lowStock, { backgroundColor: colors.warningLight, borderRadius: radii.md, flexDirection }]}>
          <Ionicons name="alert-circle-outline" size={16} color={colors.warning} />
          <Text style={[typography.tiny, { color: colors.warning, flex: 1, marginHorizontal: 6, textAlign }]}>{t('treatment.stockLow')}</Text>
        </View>
      )}

      <TouchableOpacity
        accessibilityRole="button"
        disabled={!canSave || updateStockMutation.isPending}
        onPress={() => updateStockMutation.mutate()}
        style={[styles.saveButton, { backgroundColor: canSave ? colors.primary : colors.textMuted, borderRadius: radii.md, flexDirection }]}
      >
        {updateStockMutation.isPending ? <ActivityIndicator size="small" color={colors.textInverse} /> : <Ionicons name="save-outline" size={16} color={colors.textInverse} />}
        <Text style={[typography.captionBold, { color: colors.textInverse, marginHorizontal: 6 }]}>{t('common.save')}</Text>
      </TouchableOpacity>
      {saveError && <Text accessibilityRole="alert" style={[typography.tiny, { color: colors.error, textAlign }]}>{t('treatment.stockSaveError')}</Text>}
    </View>
  );
};

const styles = StyleSheet.create({
  card: { borderWidth: 1, padding: 12, marginVertical: 6 },
  titleRow: { alignItems: 'center', gap: 8, marginBottom: 12 },
  icon: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center' },
  weekRow: { justifyContent: 'space-between', gap: 4 },
  dayColumn: { flex: 1, minWidth: 32, alignItems: 'center', gap: 5 },
  dayStatus: { width: 30, height: 30, borderRadius: 15, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  divider: { height: 1, marginVertical: 12 },
  stockHeader: { alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
  stockTitle: { alignItems: 'center' },
  inputRow: { alignItems: 'center', marginTop: 7, gap: 4 },
  input: { width: 76, borderWidth: 1, paddingHorizontal: 8, paddingVertical: 7 },
  lowStock: { alignItems: 'center', padding: 8, marginTop: 8 },
  saveButton: { alignSelf: 'flex-end', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12, paddingVertical: 8, marginTop: 10 },
});
