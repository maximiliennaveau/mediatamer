import subprocess
from pathlib import Path


def burn_metadata(file_path: str, metadata: dict):
    """
    Injecte les métadonnées TVDB dans les headers du fichier MKV.
    """
    path = Path(file_path)
    if not path.exists():
        print(f"Erreur : Le fichier {file_path} n'existe pas.")
        return

    # Préparation des arguments pour mkvpropedit
    # --edit info : modifie les informations générales du segment
    # --set title : définit le titre global (ex: Doctor Who (2005) - S09E01 - Title)

    full_title = f"{metadata['series_full_name']} - S{metadata['seasonNumber']:02d}E{metadata['number']:02d} - {metadata['name']}"

    cmd = [
        "mkvpropedit",
        str(path),
        "--edit",
        "info",
        "--set",
        f"title={full_title}",
    ]

    # Ajout des Tags globaux (Global Tags)
    # On utilise --add-set pour s'assurer que les tags sont bien écrits
    tags = [
        ("TITLE", metadata["name"]),
        ("SUMMARY", metadata["overview"]),
        ("DESCRIPTION", metadata["overview"]),
        ("DATE_RELEASED", metadata["aired"]),
        ("YEAR", metadata["year"]),
        ("IMDB", metadata.get("imdbId", "")),  # Si présent
        ("TVDB", str(metadata["id"])),
        ("SEASON_NUMBER", str(metadata["seasonNumber"])),
        ("EPISODE_NUMBER", str(metadata["number"])),
        ("SERIES_TITLE", metadata["series_full_name"]),
    ]

    for tag_name, tag_value in tags:
        if tag_value:
            # Nettoyage des guillemets pour éviter les erreurs de shell
            safe_value = str(tag_value).replace('"', '\\"')
            cmd.extend(["--set", f"metadata:{tag_name}={safe_value}"])

    print(f"Injection des métadonnées dans : {path.name}...")

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("Succès : Métadonnées injectées.")
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de l'exécution de mkvpropedit : {e.stderr}")
