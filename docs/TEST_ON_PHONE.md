# Guide Complet : Tester HackCure sur Votre Téléphone Physique

Ce guide vous donne les étapes pas-à-pas pour lancer et tester l'application **HackCure** sur votre smartphone (Android ou iPhone) depuis votre PC Windows, avec **zéro erreur**.

---

## 🚀 Méthode Rapide (En 1 Seule Commande)

Dans PowerShell :
```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\moham\Desktop\hackcure\scripts\start_dev.ps1
```
Cette commande :
1. Détecte automatiquement l'adresse IP Wi-Fi de votre PC (ex: `172.20.10.3`).
2. Configure automatiquement le fichier `mobile/.env` avec cette adresse IP.
3. Lance le serveur Backend (`uvicorn`) sur toutes les interfaces réseau (`0.0.0.0:8000`).
4. Lance le serveur Expo (`npx expo start -c`) avec purge du cache Metro.

Il ne vous reste plus qu'à scanner le QR code affiché à l'écran !

---

## 📋 Méthode Détaillée Pas-à-Pas

### Étape 1 : Installer Expo Go sur votre téléphone
- **Android** : Ouvrez Google Play Store et installez l'application **Expo Go**.
- **iPhone** : Ouvrez l'App Store et installez l'application **Expo Go**.
> **Compatibilité** : Le projet utilise **Expo SDK 57**. L'application Expo Go actuelle sur les stores supporte cette version.

---

### Étape 2 : Connecter le PC et le téléphone au même réseau Wi-Fi
- Votre téléphone et votre PC doivent être sur le **même réseau Wi-Fi local** (ex: partage de connexion 4G/5G de votre téléphone ou même box Wi-Fi).
- *Remarque* : Les réseaux Wi-Fi publics d'entreprise ou d'université bloquent souvent les connexions directes entre appareils. Si vous êtes sur un tel réseau, utilisez le mode tunnel (voir section Dépannage).

---

### Étape 3 : Trouver l'IP locale de votre PC et configurer l'URL
Dans PowerShell :
```powershell
ipconfig
```
Repérez la ligne **Adresse IPv4** de votre carte sans fil Wi-Fi (ex: `172.20.10.3`).

> ⚠️ **Important** : Ne mettez **JAMAIS** `localhost` ou `127.0.0.1` pour tester sur un téléphone, car pour le téléphone, `localhost` désigne le téléphone lui-même et non votre PC !

Vérifiez que votre fichier `c:\Users\moham\Desktop\hackcure\mobile\.env` contient cette IP :
```env
EXPO_PUBLIC_API_URL=http://172.20.10.3:8000
```
*(Remplacez `172.20.10.3` par votre propre adresse IPv4 si elle change)*.

---

### Étape 4 : Autoriser les ports dans le Pare-feu Windows (À faire une seule fois)
Pour que Windows autorise votre téléphone à joindre le serveur backend et Expo, ouvrez PowerShell en **Administrateur** et exécutez ces deux commandes :

```powershell
New-NetFirewallRule -DisplayName "HackCure Backend API (8000)" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "HackCure Expo Metro (8081)" -Direction Inbound -LocalPort 8081 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue
```

---

### Étape 5 : Démarrer le Backend
Dans un terminal PowerShell :
```powershell
cd C:\Users\moham\Desktop\hackcure\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Le serveur écoute sur toutes les interfaces (`0.0.0.0:8000`). Vous pouvez vérifier qu'il répond en ouvrant sur le navigateur de votre téléphone : `http://172.20.10.3:8000/health`. Vous devez voir `{"status":"ok"}`.

---

### Étape 6 : Démarrer Expo
Dans un **deuxième** terminal PowerShell :
```powershell
cd C:\Users\moham\Desktop\hackcure\mobile
npx expo start -c
```
> Le paramètre `-c` vide le cache de Metro Bundler pour éviter tout reliquat d'anciennes versions.

---

### Étape 7 : Scanner et ouvrir l'application
- **Sur Android** : Ouvrez l'application **Expo Go**, appuyez sur **"Scan QR code"** et visez le QR code dans votre terminal.
- **Sur iPhone** : Ouvrez l'application **Appareil photo** native d'iOS, visez le QR code, et appuyez sur la bannière jaune ouvrant Expo Go.

---

## 🧪 Checklist de Test dans l'Application

Une fois l'application ouverte sur votre téléphone :

| Écran / Action | Ce que vous faites | Résultat Attendu |
| :--- | :--- | :--- |
| **Connexion** | Tapez `mohamed@example.com` et `Test123!@#` | Redirection immédiate vers le Dashboard d'accueil. |
| **Accueil (Dashboard)** | Observez le tableau de bord | Affichage de l'observance, des prises du jour et du prochain rendez-vous. |
| **Onglet "Traitement"** | Appuyez sur l'icône Traitement en bas | Affichage de la **Synthèse du Rapport Médical** (diagnostic, objectifs, alertes, résumé patient) et de l'ordonnance active. |
| **Sous-onglet "Médicaments"** | Appuyez sur "Médicaments" | Affichage des doses groupées par moment de la journée (matin, soir). |
| **Validation d'une prise** | Appuyez sur le bouton vert **"J'ai pris ma dose"** | La dose passe en statut vert avec horodatage, et l'escalade d'alarme est stoppée. |
| **Historique des prises** | Appuyez sur "Historique & Suivi des prises" | Écran `/treatment/history` listant les prises validées et les oublis avec horodatage réel. |
| **Sous-onglet "Sport"** | Appuyez sur l'onglet "Sport" | Affichage des **activités recommandées** (vertes), des **contre-indications / à éviter** (rouges), et de la fréquence prescrite. |
| **Sous-onglet "Nutrition"** | Appuyez sur l'onglet "Nutrition" | Affichage du **régime DASH / Méditerranéen**, des aliments à privilégier/éviter, et des cibles hydratation & calories. |
| **Onglet "Pharmacie"** | Appuyez sur "Pharmacie" | Affichage des pharmacies partenaires réelles avec le stock des médicaments de votre ordonnance, distance en km et prix en TND. |

---

## 🛠️ Tableau de Dépannage (Troubleshooting)

| Symptôme | Cause Fréquente | Solution |
| :--- | :--- | :--- |
| `Network request failed` | Le téléphone n'arrive pas à joindre l'IP du PC | 1. Vérifiez que le téléphone et le PC sont sur le même Wi-Fi.<br>2. Vérifiez que l'IP dans `mobile/.env` correspond à celle d'`ipconfig`.<br>3. Exécutez la règle de pare-feu de l'étape 4.<br>4. Testez d'ouvrir `http://<VOTRE-IP>:8000/health` dans le navigateur de votre téléphone. |
| Erreur `ExpoTopicSubscriptionModule` | Module natif Android absent dans Expo Go | **Déjà résolu** : le code utilise une détection automatique d'Expo Go et un try-catch défensif. Si l'erreur apparaît, relancez avec `npx expo start -c`. |
| Le QR code ne se connecte pas | Blocage du port 8081 par le pare-feu ou routeur | Démarrez Expo en mode tunnel : `npx expo start --tunnel -c`. |
| Écran blanc au lancement | Cache JavaScript corrompu | Stoppez Expo (`Ctrl + C`), puis relancez avec le flag de purge de cache : `npx expo start -c`. |
| Wi-Fi public / universitaire bloque la connexion | Isolation des clients (AP Isolation) | Utilisez le partage de connexion 4G/5G de votre téléphone vers votre PC, ou utilisez **cloudflared / ngrok** :<br>`cloudflared tunnel --url http://localhost:8000`<br>puis mettez l'URL `https://...` générée dans `mobile/.env`. |
