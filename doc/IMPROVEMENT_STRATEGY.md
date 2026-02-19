# Stratégie d'Amélioration de MediaTamer

L'intégration de `mkvmerge` et `MediaInfo` ouvre de nouvelles possibilités pour rendre le mapping DVD vers Jellyfin quasi infaillible. Voici les axes d'amélioration proposés :

## 1. Utilisation de `mkvmerge` pour la Structure MKV
Le passage de `ffprobe` à `mkvmerge` pour l'identification initiale offre :
- **Précision des IDs** : Les IDs de pistes fournis par `mkvmerge` sont les mêmes que ceux utilisés pour l'extraction via `mkvextract`. Cela évite les erreurs de mapping lors de l'OCR.
- **Flags Natifs** : Détecter les pistes marquées comme "Default" ou "Forced" permet de deviner la langue principale sans même lire le texte des sous-titres.

## 2. Analyse des Chapitres pour les Fichiers "Multi-Épisodes"
Les DVDs contiennent souvent plusieurs épisodes dans un seul gros fichier MKV.
- **Signal** : Utiliser `mkvmerge -J` pour compter les chapitres.
- **Stratégie** : Si un fichier dure 1h30 et possède 15 chapitres, il s'agit probablement de 3 épisodes de 30 min. MediaTamer pourrait proposer de diviser le fichier ou de le nommer `S01E01-E03`.

## 3. Empreinte Temporelle et Groupement (MediaInfo)
Les fichiers extraits avec MakeMKV contiennent souvent des métadonnées de création.
- **Signal** : L'attribut `Encoded_Date` de MediaInfo.
- **Stratégie** : Les fichiers d'un même disque sont extraits avec des dates très proches. On peut utiliser ce signal pour confirmer que `A1_t00` et `A2_t01` appartiennent bien à la même série, même si les noms de dossiers sont ambigus.

## 4. OCR Cerné sur les Génériques
Actuellement, MediaTamer fait de l'OCR sur les 10 premières minutes.
- **Amélioration** : Utiliser les chapitres (via `ffprobe`/`mkvmerge`) pour identifier exactement le début des génériques de fin ou de début et n'analyser que ces zones. C'est là que se trouvent les noms des acteurs et le titre de l'épisode.

---

### Prochaines étapes recommandées :

1. **Refactorisation de `technical.py`** : Créer un objet `MediaSignals` qui agrège les sorties des 3 outils pour fournir une vue unifiée.
2. **Implémentation de `ChapterSignal`** : Ajouter la détection des chapitres dans le score de matching.
3. **Optimisation de l'OCR** : Limiter l'OCR aux segments de chapitres identifiés.

**Souhaitez-vous que je commence par l'un de ces points, ou préférez-vous explorer une autre piste ?**
