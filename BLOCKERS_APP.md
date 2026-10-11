# Blocages — application patient

| Heure (11/10) | Blocage | Ce qui a été fait |
|---|---|---|
| 04:14 | Le dossier `hackcure/` n'existait pas à côté de `Hospital_copilot/` (seul `hackcure-update/`, sans dépôt git, était présent). | Dépôt cloné depuis `https://github.com/7tiwchO/hackcure` (branche `main`). |
| 04:20 | `pip install -r backend/requirements.txt` échoue avec Python 3.13 : pas de paquets précompilés pour `pydantic-core` 2.14, `asyncpg` 0.29, `psycopg2-binary` 2.9.9. | Versions récentes compatibles installées dans `backend/.venv` (sans `asyncpg` ni `psycopg2`, inutiles avec SQLite). `requirements.txt` non modifié. Avec Python 3.11 / 3.12, les versions figées devraient s'installer : non retesté. |
| 04:36 | **Push refusé** : `remote: Permission to 7tiwchO/hackcure.git denied to Firas-Bennani` (HTTP 403). Le compte git de cette machine n'a pas le droit d'écriture sur le dépôt de l'application. | Tout est **commité en local** sur la branche `feat/hospital-link-agent` de `HACKcure/hackcure`. Pour publier : se faire ajouter comme collaborateur puis `git push -u origin feat/hospital-link-agent`, ou pousser vers un fork (`git remote add fork <url> ; git push -u fork feat/hospital-link-agent`) et ouvrir une demande de fusion. |
| 04:30 | Le serveur de démonstration de Hospital Copilot sur le port 8000 tournait avec l'ancien code (sans rapport ni ordonnance de sortie en FHIR) et ne devait pas être arrêté. | Essai réel fait contre une instance de test sur le port 8010. **À faire avant la démo : relancer Hospital Copilot sur 8000** (`.\scripts\run-demo.ps1`). |
| — | Aucun crédit d'API Anthropic. | Mode de secours partout (programme par règles, réponses préparées de Sakina), signalé dans l'interface. Le chemin LLM n'a pas été exécuté avec un vrai modèle. |
