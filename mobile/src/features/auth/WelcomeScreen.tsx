import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { useTheme } from '../../theme';
import { useRTL } from '../../i18n/RTLContext';
import { ScreenContainer } from '../../components/layout/ScreenContainer';
import { PrimaryButton } from '../../components/ui/PrimaryButton';
import { SecondaryButton } from '../../components/ui/SecondaryButton';

export const WelcomeScreen: React.FC = () => {
  const router = useRouter();
  const { colors, typography, spacing, radii } = useTheme();
  const { textAlign } = useRTL();
  const { t } = useTranslation();

  return (
    <ScreenContainer scrollable={false} withNetworkBanner={false} withPadding={false}>
      <View style={[styles.container, { backgroundColor: colors.background, padding: spacing.xl }]}>
        <View style={styles.heroSection}>
          <View
            style={[
              styles.iconCircle,
              {
                backgroundColor: colors.primaryLight,
                borderRadius: radii.full,
              },
            ]}
          >
            <Ionicons name="medical" size={64} color={colors.primary} />
          </View>

          <Text style={[typography.h1, styles.brandName, { color: colors.primary, textAlign }]}>
            HackCure
          </Text>

          <Text style={[typography.h3, styles.title, { color: colors.textPrimary, textAlign }]}>
            {t('auth.welcomeTitle')}
          </Text>

          <Text style={[typography.body, styles.subtitle, { color: colors.textSecondary, textAlign }]}>
            {t('auth.welcomeSubtitle')}
          </Text>
        </View>

        <View style={styles.actionSection}>
          <PrimaryButton
            title={t('auth.login')}
            onPress={() => router.push('/(auth)/login')}
            style={{ marginBottom: spacing.md }}
          />

          <SecondaryButton
            title={t('auth.register')}
            onPress={() => router.push('/(auth)/register')}
            variant="outline"
          />
        </View>
      </View>
    </ScreenContainer>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'space-between',
  },
  heroSection: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  iconCircle: {
    width: 120,
    height: 120,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 24,
  },
  brandName: {
    fontWeight: '800',
    letterSpacing: -0.5,
    marginBottom: 8,
  },
  title: {
    marginBottom: 12,
  },
  subtitle: {
    maxWidth: 320,
    lineHeight: 22,
  },
  actionSection: {
    width: '100%',
    paddingBottom: 24,
  },
});
