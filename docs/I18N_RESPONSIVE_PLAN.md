# French localization and responsive layout plan

## Reconnaissance

- The Expo application is `mobile/` (`main: expo-router/entry`), using Expo Router file routes in `mobile/app/` and screen implementations in `mobile/src/features/`.
- Navigation is a root Stack plus a six-tab patient navigator. Shared user-visible copy also lives in reusable UI/cards, translation resources, validation schemas, notification/reminder utilities, and `mobile/app.json` permission metadata.
- The project already uses i18next/react-i18next and supports French, English, and Arabic (including RTL). Keep this system and all three languages intact. French is the app's default and fallback. Translation dictionaries remain organized per feature so adding a language only requires a resource and registration in the existing resources map; no screen changes.
- Branch `feat/french-responsive` cannot be created because the supplied workspace has no `.git` repository metadata. No commits can be made here; preserve small, reviewable edits and document this limitation.

## User-visible screen inventory

### Router screens (`mobile/app/`)

- Root/index and initialization: `app/index.tsx`, `app/_layout.tsx`, `app/onboarding.tsx`.
- Authentication: `app/(auth)/welcome.tsx`, `login.tsx`, `register.tsx`, `forgot-password.tsx`, and `(auth)/_layout.tsx`.
- Main tabs: `(tabs)/index.tsx` (Accueil), `treatment.tsx`, `pharmacy.tsx`, `doctor.tsx`, `companion.tsx`, `profile.tsx`, and `(tabs)/_layout.tsx`.
- Care and records: `treatment/medications.tsx`, `treatment/medication/[id].tsx`, `treatment/history.tsx`, `treatment/adherence.tsx`, `treatment/sport.tsx`, `treatment/nutrition.tsx`, `prescription/[id].tsx`, `medical-records/index.tsx`, `medical-records/[id].tsx`.
- Communication, appointments, notifications, settings: `conversation/[id].tsx`, `appointment/list.tsx`, `appointment/[id].tsx`, `notifications.tsx`, `settings/language.tsx`, `settings/theme.tsx`.

Most route files mount a corresponding feature screen. Audit both route options and feature copy.

### Feature screens and shared visible UI (`mobile/src/`)

- Feature screens: `features/{adherence,appointments,auth,companion,doctor,home,medical-records,medications,notifications,nutrition,onboarding,pharmacy,prescription,profile,settings,sport,treatment}`; inspect every screen file in these folders.
- Shared cards: `components/cards/{Appointment,Doctor,Dose,MedicalRecord,Medication,Notification,Nutrition,Pharmacy,Prescription,Progress,Sport}Card.tsx`.
- Shared components: `components/layout/{Header,ScreenContainer}.tsx` and all `components/ui/*.tsx`, especially buttons, inputs, labels, status badges, empty/error/loading states, dialogs, and tabs.
- User-facing system strings: `i18n/locales/{fr,en,ar}.ts`, `constants/index.ts`, `utils/validationSchemas.ts`, `utils/dateUtils.ts`, notification/reminder hooks, and `app.json` app/permission descriptions.

## Plan and conventions

1. Preserve API routes, schemas, database values, backend business logic, medication names, quantities, and units. Map known statuses to localized display labels only.
2. Audit user-visible literals and translation-key coverage. Move screen copy, alerts, accessibility labels, route labels, permission rationales and validation copy to feature keys. Use formal **vous**, short clear sentences and French medical terms consistently.
3. Configure device locale detection with French default/fallback while preserving explicit user choice and existing English/Arabic resources. Format dates/numbers using `fr-FR` when French is active. Use i18next plural rules for count-bearing labels.
4. Add one responsive hook with small (≤360 px), standard, large and tablet (≥768 px) breakpoints and a centered tablet content width. Reuse theme spacing/typography tokens and avoid new dependencies unless the existing Expo-compatible stack cannot meet a requirement.
5. Audit text layouts across forms, list rows, cards, tabs, headers, chips, dialogs and chat. Permit important clinical instructions/notes to wrap; only ellipsize secondary filenames. Add scroll/keyboard handling where content/input can be obscured, safe-area padding, 44 px touch targets and bounded scaling only for tight controls.
6. Inspect Expo APIs against the SDK 57 documentation before changing Expo-specific code. Preserve existing styles and colors.
7. Verify with TypeScript, ESLint, Expo Doctor, route/source scans for unlocalized literals and an Expo export/bundle. Run existing tests without modifying backend logic. Phone rotation, smallest-screen, large-font and accessibility checks still require a real device.

## Glossary

| English/domain concept | French term |
|---|---|
| prescription | ordonnance |
| medical report | rapport médical |
| dosage/instructions | posologie |
| treatment | traitement |
| appointment | rendez-vous |
| dose reminder | rappel de prise |
| doctor | médecin |
| pharmacist | pharmacien / pharmacienne |
| adherence | observance du traitement |
| pharmacy | pharmacie |

Use formal **vous** throughout. Preserve the spelling, dosage, unit, and frequency values that come from patient data; localize only surrounding explanatory labels.

## Risks / assumptions

- Translating locale dictionaries can change visible content but must not alter machine-readable enums, persisted keys, endpoints, or stored values.
- Arabic support and RTL are existing product behavior and must remain usable; this is not an English/Arabic removal project.
- French is the completed source and fallback for newly introduced UI keys. Existing English/Arabic translations remain where provided, but untranslated new copy falls back to French until those resource entries receive full parity.
- Native permission descriptions are configured in `app.json`; changing them affects generated native builds and may not change the already-installed Expo Go permission dialog.
- The database/backend do not require schema or logic changes for this UI task.

## Implementation status

- Added and applied a French-default i18next initialization while retaining the existing French, English, and Arabic resources and RTL behavior.
- Migrated visible app text, validation/API error copy, tab labels, known backend status enums, notification templates, and date/time formatting to translation keys. Patient-provided medical names, dosages, and free-text notes remain unchanged.
- Added `useResponsiveLayout` and applied small-screen horizontal padding, centered tablet content, safe-area-aware keyboard layout, wrapping headers and labels, accessible minimum touch targets, and flexible tab sizing.
- Added `npm run check:i18n` to detect remaining literal UI strings and references without French resource keys.
- Remaining manual checks: test on physical/simulated 320 px and 360 px phones, standard and large phones, tablet width, landscape, large system font, Arabic RTL, long clinical copy, keyboard-visible forms/chat, and screen reader navigation. No simulator is available in this workspace.
- Git operations could not be performed because this workspace has no `.git` metadata; consequently the requested feature branch and commits are unavailable here.
