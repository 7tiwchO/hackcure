import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import { useTheme } from '../../theme';
import { useRTL } from '../../i18n/RTLContext';
import { ProgressBar } from '../../components/ui/ProgressBar';

interface SourceConfidenceProps {
  source?: string | null;
  /** Between 0 and 1 (values above 1 are read as a percentage). */
  confidence?: number | null;
}

export const toPercent = (value?: number | null): number | null => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const percent = value <= 1 ? value * 100 : value;
  return Math.max(0, Math.min(100, Math.round(percent)));
};

/** Traceability footer shown under every generated element: where it comes from and how sure the agent is. */
export const SourceConfidence: React.FC<SourceConfidenceProps> = ({ source, confidence }) => {
  const { colors, typography, spacing } = useTheme();
  const { flexDirection, textAlign } = useRTL();
  const { t } = useTranslation();
  const percent = toPercent(confidence);

  if (!source && percent === null) return null;

  const tone = percent === null ? colors.textMuted : percent >= 80 ? colors.success : percent >= 50 ? colors.warning : colors.textMuted;

  return (
    <View style={[styles.container, { borderTopColor: colors.divider, marginTop: spacing.md, paddingTop: spacing.sm }]}>
      {!!source && (
        <View style={[styles.row, { flexDirection }]}>
          <Ionicons name="document-text-outline" size={14} color={colors.textMuted} style={styles.icon} />
          <Text style={[typography.tiny, { color: colors.textSecondary, textAlign, flex: 1 }]}>
            {t('program.sourceLabel')}{' : '}{source}
          </Text>
        </View>
      )}
      {percent !== null && (
        <View
          accessible
          accessibilityLabel={t('program.confidenceA11y', { percent })}
          style={[styles.row, { flexDirection, marginTop: source ? 6 : 0 }]}
        >
          <Ionicons name="speedometer-outline" size={14} color={tone} style={styles.icon} />
          <Text style={[typography.tiny, { color: colors.textSecondary }]}>
            {t('program.confidence')}
          </Text>
          <View style={styles.bar}>
            <ProgressBar progress={percent} color={tone} height={6} />
          </View>
          <Text style={[typography.tiny, { color: tone, fontWeight: '700' }]}>
            {percent} %
          </Text>
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    borderTopWidth: 1,
  },
  row: {
    alignItems: 'center',
  },
  icon: {
    marginHorizontal: 4,
  },
  bar: {
    flex: 1,
    marginHorizontal: 8,
  },
});
