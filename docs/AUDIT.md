# Rapport d'Audit & Validation Finale — HackCure

## Vérification complémentaire — 2026-10-11

Cette passe a repris les anomalies visibles dans les dernières captures (écran d'accueil de l'onboarding, compteurs de prises, bannière « hors ligne », dates identiques du compagnon) et a vérifié les changements associés.

### Problèmes observés et corrections

- **Écran final d'onboarding bloquant** : l'achèvement attendait des permissions natives, ce qui peut bloquer le parcours Web. Le bouton final et « Passer » partagent maintenant un chemin de fin qui persiste l'état et remplace la route; les permissions sont demandées sans bloquer et uniquement hors Web.
- **Compteurs de traitement incomplets/incohérents** : l'API n'exposait pas les agrégats journaliers et mensuels attendus par le mobile, et les dates étaient calculées selon le fuseau de la machine. Un service partagé classe les doses selon le fuseau du patient, expose les compteurs cohérents avec la liste du jour et rafraîchit l'écran au retour du focus. La valeur de repli est `Africa/Tunis`; le champ patient `timezone` est ajouté par migration additive `0002_patient_timezone`.
- **Alerte hors ligne incorrecte** : le mobile testait un site Internet tiers au lieu de vérifier l'API. Il utilise maintenant `/health` de l'API configurée.
- **Session authentifiée expirée qui restait affichée** : l'API renvoyait `401` aux requêtes du compagnon et le gestionnaire supprimait les jetons persistés sans vider l'état d'authentification en mémoire. L'état patient reste maintenant synchronisé avec la suppression des jetons, et l'espace protégé redirige vers la connexion après expiration.
- **Dates du compagnon identiques** : les dates absolues sans heure masquaient les conversations du même jour; le mobile affiche maintenant date relative et heure en fuseau tunisien. Les anciens horodatages SQLite sans fuseau sont interprétés comme UTC, cohérent avec l'ancien producteur `datetime.utcnow`; aucun ancien message n'a été réécrit.
- **Workflow chatbot importable** : `n8n/chatbot-psychologique.workflow.json` contenait un échappement JSON invalide dans des apostrophes du code JavaScript. L'échappement a été corrigé; JSON, connexions et syntaxe des Code nodes ont été vérifiés statiquement.
- **Protection des fichiers SQLite** : `.gitignore` couvre maintenant les fichiers de base et leurs fichiers annexes.

### Vérifications et limites

- Tests backend : **32 réussis** sur une copie migrée de la base. La première tentative sur une copie non migrée a échoué sur l'absence de `patients.timezone`; la copie a ensuite été migrée et tous les tests sont passés.
- Migration fraîche : Alembic passe sur une nouvelle base. La base locale a été sauvegardée via l'API SQLite en ligne (`hackcure_before_timezone_20261011.db`), puis migrée; `PRAGMA integrity_check` renvoie `ok`. Le fichier source n'a pas été supprimé.
- Mobile : `tsc --noEmit` et `check:i18n` réussis; ESLint n'a aucune erreur et conserve 31 avertissements préexistants.
- Backend `/health`, Expo Web `/` et la route `/companion` renvoient HTTP 200; l'export web de production a assemblé 1 617 modules. La vérification visuelle a révélé que la session du navigateur était expirée (`401` sur consentement/contacts); après rechargement, l'application affiche l'écran de connexion. Une nouvelle connexion patient est nécessaire pour valider le chat authentifié et son consentement; aucun message n'a été envoyé pendant cette vérification.
- Six workflows n8n passent les contrôles JSON/références/syntaxe JavaScript. Aucun n8n ou Docker n'est installé ici; import réel, résolution des credentials et test avec les API Anthropic/Tavily restent à faire sur une instance configurée.
- La configuration locale ne contient actuellement ni clé Anthropic ni URL/secret de webhook chatbot n8n. Les réponses réelles du modèle nécessitent une clé privée dans `backend/.env`; le flux direct Anthropic fonctionne sans n8n. Pour le flux n8n, installer/configurer n8n et renseigner le webhook + secret partagé. Aucun secret n'a été ajouté au dépôt.
- Le dépôt n'a pas de répertoire `.git`; création d'une branche et commits séparés impossibles dans cet environnement.

### Non corrigé / à valider

- Les 31 avertissements ESLint restants sont dans des écrans/utilitaires existants sans lien avec les changements vérifiés; aucun remaniement sans rapport n'a été fait.
- La règle métier « prise oubliée après 24 heures » et la classification des prises très anticipées comme `TAKEN_LATE` doivent être approuvées par l'équipe clinique.
- Les textes de crise, le partage avec l'équipe de soin, la recherche Web/Tavily et la conservation des exécutions n8n doivent être revus avant activation ou utilisation avec des patients.
- Une clé Anthropic/Tavily et une instance n8n sont nécessaires pour vérifier les réponses génératives réelles. Le fichier d'évaluation de 30 messages est un jeu de revue, pas une certification clinique.

Ce rapport documente l'audit complet du système HackCure, les corrections apportées, les résultats des tests automatisés et les instructions pour le test sur smartphone physique.

---

## 1. Synthèse des Bogues Détectés et Corrections Appliquées

### A. Mobile & Expo Go (Android SDK 53+)
1. **Crash natif `Cannot find native module 'ExpoTopicSubscriptionModule'`** :
   - *Fichiers modifiés* : `mobile/node_modules/expo-notifications/build/TopicSubscriptionModule.android.js`, `mobile/src/hooks/useNotifications.ts`, `mobile/src/features/onboarding/OnboardingScreen.tsx`.
   - *Cause* : Expo SDK 53+ a supprimé certains modules natifs de notifications push dans le binaire d'Expo Go sur Android. L'importation synchrone de `expo-notifications` provoquait une exception non rattrapée qui bloquait le chargement de toutes les routes dépendantes.
   - *Solution* : Détection automatique de l'environnement Expo Go (`Constants.executionEnvironment === 'storeClient'`), chargement différé et défensif de `expo-notifications` (`loadNotifications()`), et encapsulation par un `try/catch` du module natif pour garantir un fonctionnement sans plantage dans Expo Go.

2. **Routes Expo Router signalées "missing default export"** :
   - *Fichiers inspectés* : `mobile/app/(tabs)/treatment.tsx`, `mobile/app/treatment/medications.tsx`.
   - *Cause* : Symptôme en cascade du plantage natif ci-dessus lors de l'évaluation des composants importés.
   - *Solution* : Résolu via la stabilisation de `useNotifications.ts` et des exports React.

3. **Incompatibilités de tokens de couleurs TypeScript** :
   - *Fichiers modifiés* : `mobile/src/features/medications/DoseHistoryScreen.tsx`, `mobile/src/features/nutrition/NutritionScreen.tsx`, `mobile/src/features/sport/SportScreen.tsx`, `mobile/src/features/treatment/TreatmentScreen.tsx`.
   - *Cause* : Utilisation des clés non définies `danger` et `dangerLight` au lieu des tokens réels du thème `error` et `errorLight`.
   - *Solution* : Remplacement par les tokens stricts de la palette de couleurs.

4. **Dépendance manquante signalée par `expo-doctor`** :
   - *Action* : Installation de `react-native-worklets` via `npx expo install react-native-worklets` pour satisfaire les dépendances de `react-native-reanimated`.

5. **Détection d'IP pour le téléphone physique** :
   - *Fichier créé* : `scripts/start_dev.ps1` et mise à jour de `mobile/.env`.
   - *Cause* : Sur un téléphone réel, `localhost` pointe vers le téléphone lui-même, provoquant `Network request failed`.
   - *Solution* : Détection automatique de l'IP Wi-Fi de l'hôte (`172.20.10.3`) et injection dans `mobile/.env`.

### B. Backend FastAPI & Base de Données
1. **Colonnes `SportPlan` et `NutritionPlan` dans `app/api/automation.py`** :
   - *Fichier corrigé* : `backend/app/api/automation.py`.
   - *Cause* : L'instanciation de `SportPlan` et `NutritionPlan` utilisait des noms de colonnes obsolètes (`goal`, `level`, `weekly_target_minutes`) au lieu des colonnes réelles du modèle (`activity_name`, `activity_type`, `duration_minutes`, `intensity`, `frequency_per_week`, etc.).
   - *Solution* : Alignement rigoureux sur les colonnes de `app/models/sport.py` et `app/models/nutrition.py`.

2. **Type de `scheduled_time` dans `MedicationDose`** :
   - *Fichier corrigé* : `backend/app/api/automation.py`.
   - *Cause* : Passage d'une chaîne de caractères `time_str` au lieu d'un objet `datetime.time`.
   - *Solution* : Conversion systématique avec `datetime.strptime(time_str, "%H:%M").time()`.

3. **Collision d'unicité sur `prescription_number`** :
   - *Fichier corrigé* : `backend/app/api/automation.py`.
   - *Cause* : Lors de ré-exécutions d'extractions, `prescription_number` violait la contrainte UNIQUE.
   - *Solution* : Gestion intelligente avec suffixe de version automatique en cas de collision.

4. **Champ `doctor_id` nullable pour les ordonnances automatisées** :
   - *Fichier corrigé* : `backend/app/schemas/prescription.py`.
   - *Cause* : Les ordonnances issues d'OCR n'ont pas toujours un identifiant médecin interne au système dès l'extraction.
   - *Solution* : Définition de `doctor_id: Optional[UUID] = None` dans `PrescriptionResponse`.

5. **Mise en place de l'historique et des brouillons mobiles** :
   - *Fichier modifié* : `backend/app/api/patients.py`.
   - *Endpoints ajoutés* :
     - `GET /api/v1/patients/me/doses/history` (historique des prises réelles avec horodatage).
     - `GET /api/v1/patients/me/automation/drafts` (consultation des brouillons par le patient).
     - `POST /api/v1/patients/me/automation/apply` (application sécurisée du brouillon par le patient).

---

## 2. Preuve d'Exécution : Résultat de `check_all.ps1`

Exécution complète du script de vérification automatisée :

```
==========================================================
            HACKCURE FULL-SYSTEM VERIFICATION            
==========================================================

1. Running Backend Pytest Test Suite (22 integration tests)...
   [PASS] All 22 backend integration tests passed.
2. Verifying Backend App Startup & /health endpoint...
   [PASS] FastAPI app starts and /health responds OK (200).
3. Verifying Mobile TypeScript compilation (tsc --noEmit)...
   [PASS] 0 TypeScript compilation errors.
4. Running Mobile ESLint linter...
   [PASS] ESLint passed with 0 errors.
5. Checking Expo SDK Dependencies (expo install --check)...
   [PASS] Expo SDK dependencies are aligned.
6. Validating n8n JSON Workflows & Connection Graphs...
   [PASS] All 5 n8n workflow JSONs are structurally valid.

==========================================================
                     SUMMARY RESULTS                      
==========================================================
  [PASS] n8n Workflows Validation           
  [PASS] Backend Pytest (22 tests)          
  [PASS] FastAPI Health & Startup           
  [PASS] Expo SDK Dependencies              
  [PASS] Mobile ESLint                      
  [PASS] Mobile TypeScript (tsc)            
==========================================================
  OVERALL STATUS: ALL CHECKS PASSED PERFECTLY!
```

---

## 3. Ce qui n'a pas été modifié et Pourquoi

1. **Docker Compose en local** : Docker n'étant pas installé sur la machine Windows de développement, le backend utilise SQLite avec `check_same_thread=False` via `aiosqlite`. Le fichier `backend/docker-compose.yml` est préservé pour les déploiements de production (PostgreSQL).
2. **`mobile/App.tsx`** : Fichier conservé sans modification car Expo Router utilise `mobile/app/` comme point d'entrée officiel via `"main": "expo-router/entry"`.

---

## 4. Pré-requis et Informations à Fournir

Pour un fonctionnement complet en production ou avec l'IA n8n externe :
- **Clé API Anthropic (Claude)** : Nécessaire si vous activez les nœuds LLM dans n8n (à renseigner dans les Credentials n8n).
- **Comptes de test disponibles dans la base de données** :
  - Compte Démo Patient : `mohamed@example.com` / Mot de passe : `Test123!@#`
  - Compte Personnalisé : `mohamedallagui22@gmail.com`

---

## 5. Risques Résiduels & Bonnes Pratiques

- **Restrictions réseau Wi-Fi** : Si vous testez sur un Wi-Fi d'université ou d'entreprise avec isolation des clients (AP Isolation), utilisez le partage de connexion 4G/5G de votre téléphone ou lancez Expo en mode tunnel (`npx expo start --tunnel -c`).
- **Cache Metro Bundler** : En cas de modification de fichiers natifs ou d'environnement, pensez à toujours vider le cache avec le drapeau `-c`.

---

## 6. Re-audit et dossier médical (2026-10-10)

### Constatations et corrections

1. **Le patient n'avait pas de raccourci visible vers son dossier depuis l'accueil** : les écrans liste/détail et l'API existaient déjà. Ajout d'un raccourci dossier avec marqueur tunisien vers `/medical-records`, dans les langues et le style existants.
2. **Cache mobile non séparé entre comptes** : les requêtes du dossier utilisaient des clés React Query sans l'identité du compte. Les clés liste/détail incluent désormais l'ID de l'utilisateur connecté; l'API vérifie toujours côté serveur que les données appartiennent au patient authentifié. Un test d'intégration vérifie qu'un patient ne peut ni lister ni obtenir le dossier d'un autre.
3. **Risque de vérification sur la base patient réelle** : `scripts/check_all.ps1` utilisait la base configurée et pouvait exécuter des tests d'intégration qui modifient des données. Le script travaille maintenant sur une copie temporaire et exécute la migration Alembic sur une base temporaire neuve.
4. **Scripts de lancement trop intrusifs et mauvais Python** : les scripts de développement remplaçaient `mobile/.env` et pouvaient utiliser le Python global. Ils utilisent maintenant `backend/.venv`, conservent `.env` et définissent l'URL mobile pour le seul processus lancé.
5. **Compatibilité Passlib/bcrypt** : bcrypt 5.x cassait les tests d'authentification avec la version Passlib du projet. `backend/requirements.txt` fixe bcrypt à une version compatible (`4.0.1`).

### Vérification

- `scripts/check_all.ps1`: 23 tests pytest réussis sur une copie jetable, migration Alembic fraîche réussie, démarrage FastAPI et `/health` réussis, `tsc --noEmit` réussi, workflows n8n valides.
- `npx expo install --check`: réussi après un premier échec TLS transitoire.
- ESLint : aucune erreur; 37 avertissements restants d'import/variables inutilisés dans d'autres écrans et utilitaires. Un import inutilisé sur l'accueil a été supprimé.
- Le premier contrôle de compatibilité Expo a rencontré une coupure TLS réseau; relancé avec succès, puis le script complet a terminé avec tous les contrôles au vert.
- Aucun schéma ni fichier de base patient existant n'a été modifié.

### Limites restantes

- Les données de démonstration restent synthétiques et liées au patient de démonstration. Les nouveaux comptes voient un dossier vide jusqu'à ce que leurs propres documents soient ajoutés par le flux médecin/document. Aucun faux dossier médical n'est généré pour un vrai patient.
- Le lancement sur un appareil physique n'a pas été retesté dans cette session; il faut encore vérifier le réseau local et le parcours dans Expo sur le téléphone.
- Le répertoire fourni ne contient pas de métadonnées Git (`git status` répond « not a git repository »); il n'était donc pas possible de créer une branche ni des commits de correction séparés.
