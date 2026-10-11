# Anonymiseur local

Masque **en local** les données sensibles d'un texte (noms, e-mails, IBAN, adresses…)
avant de l'envoyer à une IA cloud (ChatGPT, Claude, Gemini…), puis remet les vraies
valeurs dans la réponse. Rien ne sort de ta machine : ni le texte original, ni la
table de correspondance.

```
Texte original ──► [ anonymiser ] ──► texte avec étiquettes ──► IA cloud
                        │                                          │
                  table.json (reste local)                  réponse avec étiquettes
                        │                                          │
                        └──────────► [ desanonymiser ] ◄───────────┘
                                            │
                                   réponse avec les vraies valeurs
```

## Installation

Le moteur de règles n'a **aucune dépendance** (Python 3.9+). Pour détecter aussi les
noms sans civilité, les organisations et les lieux, installe spaCy (recommandé) :

```bash
pip install spacy
python -m spacy download fr_core_news_md
```

## Utilisation

```bash
# 1. Vérifier ce qui est détecté (surligné, rien n'est écrit)
python -m anonymiseur anonymiser contrat.txt --apercu

# 2. Anonymiser (crée contrat.anon.txt et contrat.txt.table.json)
python -m anonymiseur anonymiser contrat.txt -o contrat.anon.txt \
        --terme "Acme Industries" --terme "Projet Phoenix"

# 3. Envoyer contrat.anon.txt à l'IA, enregistrer sa réponse dans reponse.txt

# 4. Restaurer les vraies valeurs
python -m anonymiseur desanonymiser reponse.txt --table contrat.txt.table.json
```

Options utiles : `--terme` (répétable) ou `--termes-fichier` pour toujours masquer des
noms de clients/projets ; `--sans-ner` pour désactiver spaCy ; `--labels PER` pour ne
masquer que les personnes. Si la table existe déjà, elle est réutilisée : plusieurs
documents d'une même conversation gardent des étiquettes cohérentes.

Depuis Python :

```python
from anonymiseur import Anonymizer, deanonymize

a = Anonymizer(extra_terms=["Projet Phoenix"])
res = a.anonymize("Mme Martin : jean@example.com")
print(res.text)                       # [PERSONNE_1] : [EMAIL_1]
print(deanonymize(res.text, res.mapping).text)
```

## Ce qui est détecté

| Type | Méthode |
|---|---|
| E-mail, téléphone (FR + international), IBAN, carte bancaire (Luhn), n° de sécurité sociale, adresse postale FR | règles (regex + validations) |
| Personne introduite par une civilité (Mme, M., Dr…) | règles |
| Personnes, organisations, lieux sans civilité | spaCy (optionnel) |
| Termes de ton choix (clients, projets…) | liste `--terme` |

Choix de conception : mieux vaut **masquer trop** que pas assez. Les validations sont
tolérantes (un IBAN avec une faute de frappe est quand même masqué).

## Limites : à lire avant de s'y fier

- **L'outil réduit le risque, il ne le supprime pas.** Une donnée oubliée est une fuite :
  relis toujours le texte anonymisé (`--apercu`) avant envoi.
- **Sans spaCy**, « Jean Dupont » (sans civilité) n'est **pas** détecté. L'outil l'affiche
  en avertissement au lancement.
- **Non détecté dans les tests** : e-mails obfusqués (`contact [at] exemple [dot] fr`),
  noms écrits `DUPONT Jean` sans civilité (spaCy les rate aussi dans notre jeu de test).
- **Ré-identification par le contexte** : « le PDG de la société [TERME_1], ancien ministre
  des Finances » peut identifier quelqu'un sans qu'aucun nom n'apparaisse. L'anonymisation
  d'identifiants directs n'est pas une anonymisation au sens juridique du RGPD ; c'est une
  pseudonymisation.
- **`table.json` contient les vraies données** : ne l'envoie jamais à l'IA, ne la mets pas
  dans un dépôt Git. (Le fichier est créé en lecture seule pour ton utilisateur, sous Unix.)
- Faux positifs possibles : un long nombre commençant par 1 ou 2 peut ressembler à un
  numéro de sécu, « 12 rue » + texte libre peut être pris pour une adresse.
- Entrée : **texte brut uniquement** (pas encore de PDF/Word).
- Une étiquette `[PERSONNE_1]` peut représenter plusieurs écritures de la même personne
  (« Mme Martin », « Martin ») ; à la restauration, c'est la première écriture rencontrée
  qui est remise.

## Mesurer la qualité

```bash
python benchmark.py          # règles seules
python benchmark.py --ner    # avec spaCy
python -m pytest             # tests unitaires
```

Le benchmark donne le rappel par type et liste les fuites. Résultat actuel sur le jeu
fourni (18 éléments, **petit et écrit par l'auteur de l'outil, donc optimiste**) :
règles seules 78 %, avec spaCy 89 %, 0 faux positif sur 3 textes neutres.
Pour une vraie mesure, ajoute tes propres cas dans `benchmark.py`.

## Structure

```
anonymiseur/detectors.py   règles : regex + validations (Luhn, IBAN mod 97…)
anonymiseur/ner.py         détection des noms/orgs/lieux avec spaCy (optionnel)
anonymiseur/core.py        fusion des détections, étiquettes, anonymisation, restauration
anonymiseur/__main__.py    ligne de commande
tests/test_core.py         tests unitaires
benchmark.py               rappel par type et faux positifs
```

## Pistes pour la suite

1. Entrée PDF / DOCX (extraction de texte locale).
2. Petite interface de bureau (Tauri) avec surlignage et possibilité d'ajouter/retirer
   une détection à la main avant envoi.
3. Jeu de test plus grand et plus réaliste ; mesurer précision et rappel sérieusement.
4. Types supplémentaires : dates de naissance, SIRET/SIREN, plaques d'immatriculation,
   numéros de dossier propres à un métier.
5. Comparer avec Microsoft Presidio, qui propose un cadre d'extension proche.
