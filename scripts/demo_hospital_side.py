"""
Côté hôpital de la démonstration : le médecin signe le rapport de sortie et l'ordonnance de sortie de Zohra (PAT-0004).
À lancer quand on ne veut pas faire ces gestes à la main dans l'interface de Hospital Copilot.

    python scripts/demo_hospital_side.py [--url http://localhost:8000] [--user medecin] [--password hackcure2026]

Utilise uniquement l'API de la plateforme (les mêmes appels que l'interface). Idempotent : si une ordonnance signée
existe déjà pour le séjour, rien n'est recréé.
"""
import argparse
import sys

import httpx

REPORT = (
    "Compte rendu de sortie. Patiente de 75 ans hospitalisée pour les suites d'une prothèse totale de hanche droite après fracture du col du fémur. "
    "Anémie post-opératoire modérée, bien tolérée. Suites opératoires simples, cicatrice propre, apyrexie.\n\n"
    "Consignes de sortie : marche avec déambulateur, appui complet autorisé. Kinésithérapie 3 fois par semaine pendant 6 semaines. "
    "Éviter de croiser les jambes et de s'asseoir sur un siège bas pendant 6 semaines. Régime riche en protéines et en fer. "
    "Surveillance de la cicatrice et de la température ; contrôle de la NFS dans 10 jours. "
    "Allergie connue aux AINS et à l'aspirine : ne prendre aucun anti-inflammatoire. Consultation de contrôle avec le chirurgien dans 6 semaines."
)
LINES = [("Doliprane", "1 g", "3/j", 7), ("Lovenox", "4000 UI", "1/j", 30)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--user", default="medecin")
    ap.add_argument("--password", default="hackcure2026")
    ap.add_argument("--patient", default="patient_04")
    a = ap.parse_args()
    c = httpx.Client(base_url=a.url.rstrip("/"), timeout=20, verify=False)
    r = c.post("/api/auth/login", json={"username": a.user, "password": a.password})
    if r.status_code != 200:
        print(f"Connexion refusée ({r.status_code}) : vérifier l'URL et le compte médecin.", file=sys.stderr)
        return 1
    rec = next((p for p in c.get("/api/records").json() if p["patient_id"] == a.patient), None)
    if not rec or not rec.get("room"):
        print("La patiente n'est pas hospitalisée (pas de séjour en cours).", file=sys.stderr)
        return 1
    adm = rec.get("admission_id") or (rec.get("admission") or {}).get("id")
    if not adm:  # l'identifiant du séjour n'est pas dans la fiche : on le lit dans un risque ou une ordonnance du séjour
        detail = c.get(f"/api/records/{a.patient}").json()
        adm = detail.get("admission_id") or (detail.get("admission") or {}).get("id") or next((x.get("id") for x in detail.get("admissions", []) if not x.get("discharged_at")), None)
    if not adm:
        print("Identifiant du séjour introuvable par l'API.", file=sys.stderr)
        return 1
    code = rec.get("code", "PAT-0004")
    existing = [p for p in c.get("/api/prescriptions").json() if p.get("admission_id") == adm and p.get("status") == "signed"]
    if existing:
        print(f"{code} : une ordonnance de sortie signée existe déjà (#{existing[0]['id']}) — rien à faire.")
        return 0
    rep = c.post("/api/reports", json={"admission_id": adm, "title": "Compte rendu de sortie d'hospitalisation", "content": REPORT})
    rep.raise_for_status()
    c.post(f"/api/reports/{rep.json()['id']}/sign").raise_for_status()
    meds = {m["brand"]: m for m in c.get("/api/pharmacy/medications").json()}
    lines = [{"medication_id": meds[b]["id"], "dosage": dose, "frequency": freq, "duration_days": days, "route": "SC" if b == "Lovenox" else "PO"} for b, dose, freq, days in LINES if b in meds]
    missing = [b for b, *_ in LINES if b not in meds]
    pr = c.post("/api/prescriptions", json={"admission_id": adm, "notes": "Ordonnance de sortie", "lines": lines})
    pr.raise_for_status()
    signed = c.post(f"/api/prescriptions/{pr.json()['id']}/sign?force=true")
    signed.raise_for_status()
    print(f"{code} : rapport de sortie #{rep.json()['id']} signé, ordonnance de sortie #{pr.json()['id']} signée ({len(lines)} ligne(s))" + (f" — absents de la pharmacie : {', '.join(missing)}" if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
