# HorlogeStudio

![Build](https://github.com/samuelvermeulenpro/HorlogeStudio/actions/workflows/build.yml/badge.svg)

Horloge murale numérique pour affichage en studio, inspirée du modèle Orium
(anneau de points + affichage digital). Écrite en Python 3 avec Tkinter
uniquement (aucune dépendance externe), compatible Linux et Windows.

La palette de couleurs par défaut (bleu / orange) reprend, à titre d'exemple,
l'identité visuelle de Radio Mercure — libre à toi de l'adapter à tes propres
couleurs via les constantes `COLOR_*` en tête du script.

## Fonctionnalités

- Affichage digital 24h ou 12h (AM/PM), secondes, date en français
- Anneau de 60 points façon horloge Orium, animé en temps réel
- Plein écran ou fenêtré, taille personnalisable
- Épinglage au premier plan (*always on top*)
- Mode sans bordure ni barre de titre, avec déplacement à la souris
- Opacité réglable, à la volée ou au lancement
- Découpe circulaire réelle de la fenêtre (plus de carré noir autour du
  cercle) : extension X11 Shape sous Linux, couleur-clé native sous Windows
- Petite croix discrète au survol pour quitter sans clavier (utile en mode
  sans bordure)

## Installation

### Option 1 — Télécharger un exécutable prêt à l'emploi

Chaque version taguée génère automatiquement, via GitHub Actions, un
exécutable Windows (`.exe`) et un binaire Linux. Voir l'onglet
[**Releases**](../../releases) du dépôt.

### Option 2 — Lancer depuis les sources

Nécessite seulement Python 3.7+ avec Tkinter (`python3-tk` sur Debian/Ubuntu,
inclus par défaut sous Windows).

```bash
python3 horloge_studio.py
```

## Utilisation

```
python3 horloge_studio.py [options]
```

| Option           | Effet                                                              |
|-------------------|---------------------------------------------------------------------|
| `--window`        | Mode fenêtré (plein écran par défaut)                              |
| `--size WxH`       | Taille de la fenêtre en mode fenêtré (ex. `900x900`)               |
| `--12h`            | Affichage 12h avec AM/PM                                           |
| `--no-seconds`     | Masque les secondes et l'anneau animé                              |
| `--no-logo`        | Masque le bandeau logo                                             |
| `--no-date`        | Masque la date                                                     |
| `--no-topmost`     | Ne pas épingler la fenêtre au premier plan                         |
| `--borderless`     | Fenêtre sans bordure ni barre de titre (glisser pour déplacer)     |
| `--opacity 0.1–1.0`| Opacité de la fenêtre au lancement (défaut : `1.0`)                |
| `--shaped`         | Découpe la fenêtre en cercle (implique `--window --borderless`)    |
| `--shape-selftest` | Teste la disponibilité de la découpe circulaire, puis quitte       |

### Raccourcis clavier

| Touche        | Action                                              |
|---------------|------------------------------------------------------|
| `Échap` / `q` | Quitter                                              |
| `F11` / `f`   | Bascule plein écran / fenêtré                        |
| `t`           | Bascule l'épinglage au premier plan                  |
| `+` / `-`     | Ajuste l'opacité par pas de 5 %                      |
| `o`           | Bascule opacité totale / semi-transparente           |

> En mode `--borderless`, si le focus clavier ne répond pas (dépend du
> gestionnaire de fenêtres), survole le cercle : une petite croix apparaît
> en haut à droite pour quitter au clic.

### Exemple — overlay studio discret

```bash
python3 horloge_studio.py --window --size 480x360 --shaped --opacity 0.9
```

## Compilation (PyInstaller)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon assets/icon.ico --name HorlogeStudio horloge_studio.py   # Windows
pyinstaller --onefile --icon assets/icon.png --name HorlogeStudio-linux horloge_studio.py         # Linux
```

> PyInstaller ne fait pas de compilation croisée : chaque exécutable doit
> être généré sur sa propre plateforme cible. C'est ce qu'automatise le
> pipeline CI de ce dépôt (voir `.github/workflows/build.yml`).

## Intégration continue

Le workflow GitHub Actions (`.github/workflows/build.yml`) compile
automatiquement une version Windows et une version Linux à chaque push, et
publie les deux exécutables en pièce jointe d'une **Release GitHub** dès
qu'un tag `vX.Y.Z` est poussé :

```bash
git tag -a v1.0.0 -m "Première version stable"
git push origin v1.0.0
```

## Licence

Distribué sous licence [MIT](LICENSE).

---

*Développé par Samuel Vermeulen (SV Pro).*
