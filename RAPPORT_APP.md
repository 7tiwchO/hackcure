# Rapport — application patient reliée à Hospital Copilot

Branche `feat/hospital-link-agent` (créée depuis `main`, commit `90ec945`). Nuit du 10 au 11/10/2026.
Décisions : `DECISIONS_APP.md`. Déroulé de démonstration : `docs/DEMO_LIEN_HOPITAL.md`. Blocages : `BLOCKERS_APP.md`.

## 1. Ce qui a été construit

| Étape | Contenu | Fichiers |
|---|---|---|
| 1. Lien sécurisé | Client HTTP FHIR (jeton de service, délai, 3 tentatives, cache local), liaison par pseudonyme + date de naissance + consentement, synchronisation manuelle et périodique, documents stockés en `DocumentSource` | `backend/app/integrations/hospital_copilot.py`, `services/hospital_sync.py`, `api/hospital_link.py`, `models/hospital_link.py` |
| 2. Côté hôpital | `DocumentReference` (rapports signés, sortie), `MedicationRequest` de l'ordonnance de sortie avec `dosageInstruction` structuré, dans `$everything` | dépôt `Hospital_copilot`, commit `beae298` sur `feat/v2` (module FHIR seulement) |
| 3. CarePlanAgent | Extraction, médicaments sans LLM par le pipeline existant, programme de vie (LLM encadré ou règles), brouillon + validation, suivi d'observance, journal | `backend/app/agents/care_plan_agent.py` |
| 4. Sakina | Contexte tiré du dossier hospitalier, refus déterministe de modifier un traitement, mode sans LLM, protocole de crise inchangé | `services/sakina_context.py`, `api/sakina.py`, `prompts/sakina_system.md` |
| 5. Abonnement | Modèle, activation de démonstration, partage de revenus configurable, exigé pour le lien et l'agent | `models/hospital_link.py`, `services/hospital_sync.py` |
| 6. Mobile | Écrans « Lier mon dossier hospitalier », « Mon programme », « Mon abonnement », contexte affiché dans Sakina, FR / AR / EN | `mobile/app/{hospital-link,program,subscription}.tsx`, `mobile/src/features/…` |
| 7. Démo | Seed de la patiente liée à `PAT-0004`, script de démarrage, script des gestes côté hôpital | `app/seeds/seed_hospital_demo.py`, `scripts/start_with_hospital.ps1`, `scripts/demo_hospital_side.py` |

API ajoutée (JWT du patient) : `GET/POST/DELETE /api/hospital-link`, `POST /api/hospital-link/sync`, `GET /api/care-program`,
`POST /api/care-program/{id}/validate` (médecin), `GET /api/agent/runs`, `POST /api/agent/run`, `GET /api/subscription`,
`POST /api/subscription/activate`. `POST /api/chat` renvoie en plus `context_used` et `mode`.

## 2. Ce qui marche (vérifié)

**Tests automatiques** — `backend/tests/test_hospital_link.py`, 8 tests, hôpital simulé par un transport HTTP local (aucun réseau) :
analyse du Bundle sans rien inventer ; règles et garde-fous (allergie, hyposodé, glucides, activité contre-indiquée, conseil touchant au
traitement supprimé) ; observance (3 prises manquées d'un médicament critique) ; parcours complet liaison → synchronisation → agent →
programme → hors ligne → validation par un médecin ; `DEMO_AUTO_APPLY` ; abonnement obligatoire et séjour lié à un seul compte ;
notification au patient et signalement à l'équipe ; Sakina fondée sur l'ordonnance, refus de modifier une dose, protocole de crise inchangé.

- Backend de l'application : **42 tests verts, 2 en échec — les 2 échecs existaient avant ce travail** (voir § 5).
- Hospital Copilot : **270 tests verts** après l'ajout FHIR.
- Mobile : `npx tsc --noEmit` sans erreur, `npm run check:i18n` vert, lint 0 erreur (30 avertissements antérieurs).

**Essai réel de bout en bout** (application sur 8100 ↔ instance de test de Hospital Copilot sur **8010**, vrai serveur, vraie API FHIR) :
rapport et ordonnance de sortie signés par l'API de l'hôpital → mauvaise date de naissance refusée (404) → liaison acceptée →
7 types de ressources reçus (178 observations, 6 ordonnances, 4 documents) → nom retiré à la réception → 2 médicaments de l'ordonnance de
sortie, 55 prises planifiées → programme par règles (profils détectés : orthopédie, anémie, ostéoporose, anticoagulant) → Sakina cite
l'ordonnance et refuse « Je peux arrêter le Lovenox ? ».

## 3. Ce qui est simulé ou en mode de secours

- **LLM** : pas de crédit d'API. Le programme de vie est produit **par règles** (`mode: rules`, `fallback: true`) et Sakina répond par des
  **textes préparés** (`mode: offline_support`). Le chemin LLM existe (prompt, appel, garde-fous) mais **n'a jamais été exécuté avec un vrai
  modèle** ; seul un LLM factice l'a traversé dans les tests.
- **Abonnement** : aucun paiement ; l'activation est une démonstration.
- **Données** : patiente fictive ; l'ordonnance et le rapport de démonstration sont créés par `scripts/demo_hospital_side.py`.
- **Heures de prise** : l'ordonnance de sortie de la plateforme donne une fréquence (« 3/j ») sans heures. L'application applique alors sa
  convention d'horaires et l'indique. Ce n'est pas une donnée du médecin.
- **État psychologique de l'hôpital** : le code le lit s'il est présent dans le Bundle, mais l'hôpital **ne l'exporte pas** aujourd'hui.

## 4. Variables `.env` à renseigner (backend de l'application)

| Variable | Valeur | Remarque |
|---|---|---|
| `HOSPITAL_COPILOT_URL` | `http://localhost:8000` | plateforme hospitalière |
| `HOSPITAL_COPILOT_SERVICE_TOKEN` | **à renseigner** = `PLATFORM_SERVICE_TOKEN` de `Hospital_copilot/.env` | `start_with_hospital.ps1` le lit tout seul |
| `HOSPITAL_SYNC_INTERVAL_MINUTES` | `0` | > 0 pour la synchronisation périodique |
| `DEMO_AUTO_APPLY` | `false` | `true` en démonstration (le script le met à `true`) |
| `CARE_AGENT_USE_LLM` | `true` | sans effet tant que `ANTHROPIC_API_KEY` est vide |
| `ANTHROPIC_API_KEY` | vide | à renseigner pour sortir du mode de secours |
| `SUBSCRIPTION_HOSPITAL_SHARE_PCT` | `60` | part de l'hôpital |
| `HOSPITAL_NAME` | `Clinique HackCure` | |
| `HOSPITAL_COPILOT_VERIFY_TLS` | `true` | `false` seulement si l'hôpital est en HTTPS auto-signé |

Mobile : `EXPO_PUBLIC_API_URL=http://localhost:8100`. Liste complète dans `backend/.env.example`.

## 5. Points non vérifiés et limites

- **Aucun écran mobile n'a été vu** : ni Expo ni un navigateur n'ont été lancés. Les trois écrans et le chat sont vérifiés par le typage
  seulement ; leur rendu, leur mise en page en arabe (droite à gauche) et leurs appels réels au backend restent à essayer.
- **Le serveur de démonstration du port 8000 n'a pas été utilisé** : il tournait avec l'ancien code et n'a pas été arrêté. L'essai réel a
  été fait sur le port 8010. **Avant la démo, relancer Hospital Copilot sur 8000** pour qu'il serve le rapport et l'ordonnance de sortie.
- **`scripts/start_with_hospital.ps1` n'a pas été exécuté** (syntaxe vérifiée seulement) ; ses étapes ont été faites à la main.
- **Deux tests existants échouent, avant comme après** : `test_companion_provider_failure_returns_localized_retryable_fallback` (texte
  attendu « réessayez », texte réel « réessayer ») et `test_triage_risk_bypasses_normal_companion_reply` (validation Pydantic d'un
  `conversation_id` absent). Non corrigés : hors périmètre.
- **Dépendances** : les versions figées de `requirements.txt` ne s'installent pas avec Python 3.13. Le `.venv` utilisé contient des
  versions plus récentes (FastAPI 0.143, SQLAlchemy 2.1, Pydantic 2.14), sans `asyncpg` ni `psycopg2`. Avec Python 3.11 ou 3.12 et les
  versions figées, rien n'a été retesté.
- **Pas de migration Alembic** pour les nouvelles tables (créées au démarrage par `create_all`).
- **Nom du patient** : l'hôpital envoie le nom au jeton de service ; l'application le supprime à la réception. À durcir côté hôpital
  (jeton dédié sans droit d'identité).
- **Synchronisation périodique** : la boucle est écrite, jamais exécutée sur la durée.
- **Garde-fous** : ce sont des règles écrites par l'équipe, pas un référentiel validé ; la liste des « médicaments critiques » et celle des
  allergènes alimentaires sont courtes. Les codes LOINC / SNOMED ajoutés côté hôpital n'ont pas été passés au validateur HL7.
- **PostgreSQL** : tout a été testé avec SQLite.
- Textes générés (sources, conseils, messages d'observance) en **français** même quand l'application est en arabe ou en anglais ; seule
  l'interface et les réponses de Sakina sont traduites.
