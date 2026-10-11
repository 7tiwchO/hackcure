# Démonstration — du séjour à l'hôpital au suivi à domicile

Parcours : dans **Hospital Copilot**, le médecin signe le rapport et l'ordonnance de sortie de Zohra (`PAT-0004`, chambre 104) →
dans **l'application patient**, liaison du dossier → synchronisation → le **CarePlanAgent** crée les rappels de médicaments, le régime,
l'activité et les habitudes → **Sakina** répond en s'appuyant sur l'ordonnance.

Toutes les données sont fictives. Sans crédit d'API, l'agent et le chatbot fonctionnent en **mode de secours** (règles et réponses préparées) :
c'est indiqué à l'écran (« Programme généré par règles », « Mode sans IA »).

## 1. Démarrage

| Service | Port | Commande |
|---|---|---|
| Hospital Copilot | 8000 | dans `Hospital_copilot/` : `.\scripts\run-demo.ps1 -Reset` |
| Backend de l'application | 8100 | dans `hackcure/` : `.\scripts\start_with_hospital.ps1` (ajouter `-Web` pour ouvrir aussi l'application dans le navigateur) |
| Application (Expo web) | port par défaut d'Expo | lancé par `-Web`, ou `cd mobile ; $env:EXPO_PUBLIC_API_URL='http://localhost:8100' ; npx expo start --web` |

Important : **Hospital Copilot doit tourner avec le code de `feat/v2` à jour** (commit `beae298` ou suivant) : c'est lui qui expose le rapport
de sortie (`DocumentReference`) et l'ordonnance de sortie. Un serveur lancé avant cette mise à jour doit être relancé.

`start_with_hospital.ps1` lit le jeton de service dans `..\Hospital_copilot\.env` (`PLATFORM_SERVICE_TOKEN`), crée la patiente de démonstration
(**`zohra@example.com` / `Test123!@#`**, abonnement actif, déjà liée à `PAT-0004`) et tente une première synchronisation.
Par défaut le programme est appliqué automatiquement (« Validé automatiquement — mode démonstration ») ; avec `-Validation`, il reste en
brouillon jusqu'à validation par un médecin.

## 2. Côté hôpital (1 minute)

Dans Hospital Copilot, connecté en **`medecin`** (`hackcure2026`) :
1. **Rapport médecin** → patiente de la chambre 104 → rédiger le compte rendu de sortie (consignes : appui, kinésithérapie, régime, surveillance) → **Signer**.
2. **Ordonnance** → chambre 104 → ajouter Doliprane 1 g 3/j 7 jours et Lovenox 4000 UI 1/j 30 jours → **Signer**.

Raccourci (mêmes appels d'API que l'interface) : `backend\.venv\Scripts\python.exe scripts\demo_hospital_side.py --url http://localhost:8000`

Ce que l'hôpital expose alors : `GET /fhir/Patient/PAT-0004/$everything` — problèmes, allergies, constantes, **rapport de sortie pseudonymisé**
(`DocumentReference`), **ordonnance de sortie** avec dose, voie, fréquence et durée structurées (`MedicationRequest`, catégorie `discharge`).

## 3. Côté application (3 minutes)

Connexion : `zohra@example.com` / `Test123!@#`.

| # | Écran | Geste | Ce que le jury voit |
|---|---|---|---|
| 1 | Profil → **Mon abonnement** | — | Abonnement actif vendu par la clinique, formule, dates, **partage de revenus hôpital 60 % / équipe 40 %** (configurable). Aucun paiement réel. |
| 2 | Profil → **Lier mon dossier hospitalier** | Pour montrer la liaison : « Retirer mon consentement », puis saisir `PAT-0004`, la date de naissance **1951-07-14**, cocher le consentement, valider | Vérification auprès de l'hôpital (une mauvaise date est refusée), date du consentement, **aucun nom échangé** : pseudonyme et données cliniques seulement. |
| 3 | même écran | **Synchroniser maintenant** | Date de synchronisation, documents reçus : ordonnance, rapport de sortie, dossier médical. Hôpital arrêté ⇒ « dernière synchronisation conservée ». |
| 4 | **Traitement** (onglet existant) | — | Les médicaments de l'ordonnance, aux heures prévues ; les rappels existants prennent le relais. Rien n'est modifiable par le patient ni par l'IA. |
| 5 | **Mon programme** | — | Alimentation, activité, habitudes ; chaque élément avec sa **source** (« issu de l'ordonnance de sortie du Dr … du … ») et son **indice de confiance** ; bandeau de validation ; mention « généré par règles » si le LLM est indisponible. |
| 6 | Mon programme → **Journal de l'agent** | — | Les exécutions du CarePlanAgent : extraction → médicaments (sans LLM) → programme (garde-fous) → validation → suivi. |
| 7 | **Sakina** | « Quels médicaments je dois prendre ? » | Réponse fondée sur l'ordonnance réelle, avec la mention « Basé sur votre ordonnance du … ». |
| 8 | Sakina | « Je peux arrêter le Lovenox ? » | Refus bienveillant : seul le médecin modifie un traitement. |
| 9 | Sakina | (ne pas faire en démonstration publique sans prévenir) message de détresse | Le protocole de crise existant s'applique, inchangé : message de soutien et numéros d'urgence. |

À dire au jury : **le calendrier des prises vient uniquement des données structurées de l'ordonnance** ; l'IA ne propose que l'hygiène de vie,
dans des garde-fous (allergies, régime cohérent avec la pathologie, aucune activité contre-indiquée), et un médecin valide.

## 4. Montrer par l'API (sans l'application)

```powershell
$login = Invoke-RestMethod -Method Post -Uri http://localhost:8100/api/v1/auth/login -ContentType 'application/json' -Body '{"email":"zohra@example.com","password":"Test123!@#"}'
$h = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod -Method Post -Uri http://localhost:8100/api/hospital-link/sync -Headers $h      # synchronisation
Invoke-RestMethod -Uri http://localhost:8100/api/care-program -Headers $h | ConvertTo-Json -Depth 6  # programme, sources, confiance
Invoke-RestMethod -Uri http://localhost:8100/api/agent/runs -Headers $h | ConvertTo-Json -Depth 5    # journal de l'agent
```
Documentation interactive : <http://localhost:8100/docs>.

## 5. Observance (suite de la démonstration)

Si trois prises consécutives d'un médicament critique (anticoagulant, insuline, antiépileptique…) sont manquées, l'agent notifie le patient
(« Reprenez à la prochaine prise prévue, sans doubler la dose, et contactez votre médecin ») et écrit un signalement pour l'équipe soignante
dans le journal (`care_team_note`). Déclenchement à la demande : `POST /api/agent/run`.

## 6. Si quelque chose ne va pas

- **« La plateforme hospitalière est injoignable »** : Hospital Copilot n'est pas lancé sur le port attendu (`-HospitalUrl`).
- **« … a refusé la demande »** : le jeton de service est absent ou faux (`HOSPITAL_COPILOT_SERVICE_TOKEN` = `PLATFORM_SERVICE_TOKEN` de l'hôpital).
- **Aucun médicament synchronisé** : l'ordonnance de sortie n'est pas signée côté hôpital, ou le serveur hospitalier n'a pas le code à jour.
- **« Aucun séjour ne correspond »** : la date de naissance doit être celle de la fiche hospitalière (1951-07-14 pour la patiente de démonstration en 2026).
