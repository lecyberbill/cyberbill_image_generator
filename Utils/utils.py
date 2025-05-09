import os, sys
import importlib
import shutil
import gradio as gr
import torch
from pathlib import Path
import re
import html
import json
import requests
from tqdm import tqdm
from colorama import init, Fore, Style
from collections import defaultdict
import subprocess
import inspect
from compel import Compel, ReturnedEmbeddingsType
import gc
import math
from PIL import Image
from PIL.PngImagePlugin import PngInfo 
import piexif 
import piexif.helper 
import traceback
from packaging import version as pkg_version
from importlib_metadata import PackageNotFoundError
import base64

init()

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)


def load_locales(lang="fr"):
    """Charge les traductions depuis un fichier JSON."""
    root_dir = Path(__file__).parent.parent
    chemin_dossier_locales = root_dir / "locales"
    chemin_fichier_langue = chemin_dossier_locales / f"{lang}.json"
    

    try:
        with open(chemin_fichier_langue, "r", encoding="utf-8") as f:
            translations = json.load(f)
        print(txt_color("[OK] ","ok"),translate("langue_charge",translations),f" {lang}")
        return translations
    except FileNotFoundError:
        print(txt_color("[ERREUR] ","erreur"),translate("erreur_fichier_langue",translations), f": {chemin_fichier_langue}")
        return {}
    except json.JSONDecodeError:
        print(txt_color("[ERREUR] ","erreur"),translate("erreur_decodage_json",translations), f": {chemin_fichier_langue}")
        return {}
    

def translate(key, translations):
    """Traduit une clé en utilisant le dictionnaire de traductions."""
    return translations.get(key, f"[{key}]") #Si il ne trouve pas la valeur on affiche la clé

def get_language_options(translations):
    """Récupère la liste des langues disponibles."""
    # Get the root directory of the project
    root_dir = Path(__file__).parent.parent
    chemin_dossier_locales = root_dir / "locales"
    
    languages = []
    for filename in os.listdir(chemin_dossier_locales):
        if filename.endswith(".json"):
            languages.append(filename[:-5])  # Retire l'extension .json
    try:
        languages.remove("template")
    except:
        pass
    print(txt_color("[INFO] ","info"), translate("langue_disponible",translations), f": {languages}")
    return languages

def preparer_metadonnees_image(image_pil: Image.Image, metadonnees: dict, translations: dict, chemin_image: str):
    """
    Prépare les métadonnées (formatées en JSON) à injecter dans une image PIL
    pour une sauvegarde ultérieure au format PNG, JPEG ou WEBP.

    Args:
        image_pil (Image.Image): L'objet image PIL original.
        metadonnees (dict): Dictionnaire clé:valeur des métadonnées à ajouter.
        translations (dict): Dictionnaire pour la traduction des messages.
        chemin_image (str): Chemin prévu pour l'image (utilisé pour déterminer le format).

    Returns:
        tuple: Contenant:
            - metadata_to_save (PngInfo | bytes | None): La structure de métadonnées prête à être utilisée
              lors de la sauvegarde (PngInfo pour PNG, bytes pour EXIF JPEG ou XMP WebP, None sinon ou en cas d'erreur).
            - message (str): Message de statut (succès ou échec).
    """
    if not isinstance(image_pil, Image.Image):
        # Clé de traduction: "erreur_image_invalide_pour_meta"
        return None, translate("erreur_image_invalide_pour_meta", translations)

    if not isinstance(metadonnees, dict):
        # Clé de traduction: "erreur_metadonnees_invalides"
        return None, translate("erreur_metadonnees_invalides", translations)

    metadata_to_save = None
    message = ""
    format_image = os.path.splitext(chemin_image)[1].lower()

    try:
        # Sérialiser le JSON une seule fois (sans indentation pour JPEG/WebP)
        json_str = json.dumps(metadonnees, ensure_ascii=False)

        if format_image == ".png":
            # Utiliser une version indentée pour la lisibilité dans PNG
            json_str_png = json.dumps(metadonnees, ensure_ascii=False, indent=2)
            pnginfo = PngInfo()
            pnginfo.add_text("parameters", json_str_png)
            metadata_to_save = pnginfo
            # Clé de traduction: "metadonnees_png_preparees"
            message = translate("metadonnees_png_preparees", translations)

        elif format_image in [".jpg", ".jpeg"]:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
            try:
                # Utiliser piexif pour créer le UserComment EXIF
                user_comment_bytes = piexif.helper.UserComment.dump(json_str, encoding="unicode")
                if "Exif" not in exif_dict: exif_dict["Exif"] = {}
                exif_dict["Exif"][piexif.ExifIFD.UserComment] = user_comment_bytes

                # Générer les bytes EXIF finaux
                metadata_to_save = piexif.dump(exif_dict)
                # Clé de traduction: "metadonnees_jpeg_preparees"
                message = translate("metadonnees_jpeg_preparees", translations)
            except ValueError as e_val: # Erreur d'encodage UserComment
                message = translate("erreur_preparation_metadonnees_jpeg", translations) + f": {e_val}"
                print(txt_color("[ERREUR]", "erreur"), message)
                traceback.print_exc()
                metadata_to_save = None
            except Exception as e_dump: # Erreur piexif.dump
                message = translate("erreur_preparation_metadonnees_jpeg", translations) + f": {e_dump}"
                print(txt_color("[ERREUR]", "erreur"), message)
                traceback.print_exc()
                metadata_to_save = None

        elif format_image == ".webp":
            try:
                # Construction d'une structure XMP standard contenant le JSON échappé
                # Utilisation de dc:description et exif:UserComment pour une meilleure compatibilité
                # html.escape est crucial pour que le JSON soit valide dans le XML
                escaped_json_str = html.escape(json_str)
                xmp_data_string = f"""<?xpacket begin='﻿' id='W'?>
<x:xmpmeta xmlns:x='adobe:ns:meta/'>
  <rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>
    <rdf:Description xmlns:custom='https://example.org/ns/custom/'>
      <custom:Parameters><![CDATA[{escaped_json_str}]]></custom:Parameters>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end='w'?>"""
                
                # Encoder la chaîne XMP en bytes UTF-8 pour Pillow
                metadata_to_save = xmp_data_string.encode('utf-8')
                # Clé de traduction: "metadonnees_webp_preparees"
                message = translate("metadonnees_webp_preparees", translations)
            except Exception as e:
                # Clé de traduction: "erreur_preparation_metadonnees_webp"
                message = translate("erreur_preparation_metadonnees_webp", translations) + f": {e}"
                print(txt_color("[ERREUR]", "erreur"), message)
                traceback.print_exc()
                metadata_to_save = None

        else:
            # Clé de traduction: "format_non_supporte_pour_meta"
            message = translate("format_non_supporte_pour_meta", translations).format(format=format_image)
            metadata_to_save = None

    except json.JSONDecodeError as e_json:
        # Clé de traduction: "erreur_serialisation_json_meta"
        message = translate("erreur_serialisation_json_meta", translations) + f": {e_json}"
        print(txt_color("[ERREUR]", "erreur"), message)
        metadata_to_save = None
    except Exception as e:
        # Clé de traduction: "erreur_inconnue_preparation_meta"
        message = translate("erreur_inconnue_preparation_meta", translations) + f": {e}"
        print(txt_color("[ERREUR]", "erreur"), message)
        traceback.print_exc()
        metadata_to_save = None

    return metadata_to_save, message



def enregistrer_etiquettes_image_html(chemin_image, etiquettes, translations, is_last_image=False):
    """
    Enregistre les étiquettes d'une image dans un fichier HTML avec affichage de l'image et tableau stylisé (sans jQuery UI).
    Gère la réouverture du fichier HTML pour ajouter de nouvelles images.

    Args:
        chemin_image (str): Chemin vers le fichier image .jpg.
        etiquettes (dict): Dictionnaire d'étiquettes et de leurs valeurs.
        is_last_image (bool): Indique si c'est la dernière image à traiter.
    """
    root_dir = Path(__file__).parent.parent
    chemin_dossier_utils = root_dir / "html_util"
    chemin_jquery = chemin_dossier_utils / "jquery.min.js"
    chemin_magnific_popupCSS = chemin_dossier_utils / "magnific-popup.css"
    chemin_magnific_popupJS = chemin_dossier_utils / "jquery.magnific-popup.min.js"

    with open(chemin_jquery, 'r', encoding='utf-8') as f:
        contenu_jquery = f.read()

    with open(chemin_magnific_popupCSS, 'r', encoding='utf-8') as f:
        contenu_CSS = f.read()

    with open(chemin_magnific_popupJS, 'r', encoding='utf-8') as f:
        contenu_popupJS = f.read()

    title_lien_html = html.escape(etiquettes.get("Prompt"))

    try:
        nom_fichier_html = "rapport.html"
        chemin_fichier_html = os.path.join(os.path.dirname(chemin_image), nom_fichier_html)

        # Contenu HTML à ajouter pour chaque image
        image_html = ""

        # Ajouter les informations de l'image, l'image et les étiquettes dans un div avec un tableau
        image_html += "<div class='image-item'>\n"  # Début du div pour l'image
        image_html += "    <div class='image-container'>\n"  # Conteneur flex pour l'image et le tableau
        image_html += f"   <a class='image-popup' href='{os.path.basename(chemin_image)}' title='{title_lien_html}' target='_blank'><img src='{os.path.basename(chemin_image)}' alt='Image'></a>\n"  # Afficher l'image
        image_html += "        <div class='etiquettes'>\n"  # Début du div pour les étiquettes
        image_html += "             <table border='1'>\n"
        for etiquette, valeur in etiquettes.items():
            image_html += f"             <tr><td>{etiquette}</td><td>{valeur}</td></tr>\n"
        image_html += "             </table>\n"
        image_html += "       </div>\n"  # Fin du div pour les étiquettes
        image_html += "    </div>\n"  # Fin du conteneur flex
        image_html += "</div>\n\n"  # Fin du div pour l'image

        # Contenu à écrire dans le fichier HTML
        # Utilisation d'un dictionnaire global par chemin de fichier
        global html_contenu_buffer
        if 'html_contenu_buffer' not in globals():
            html_contenu_buffer = {}

        if chemin_fichier_html not in html_contenu_buffer:
            html_contenu_buffer[chemin_fichier_html] = []  # Initialise une liste pour chaque fichier

        html_contenu_buffer[chemin_fichier_html].append(image_html)  # Ajoute le contenu à la liste

        # Gestion de l'ouverture et de la fermeture du fichier HTML (seulement si c'est la dernière image)
        if is_last_image:
            # Si le fichier existe déjà
            if os.path.exists(chemin_fichier_html):
                with open(chemin_fichier_html, "r", encoding='utf-8') as f:
                    contenu = f.read()

                position_body = contenu.rfind("</body>")
                position_html = contenu.rfind("</html>")

                if position_body != -1 and position_html != -1 and position_body < position_html:
                    # Insérer le nouveau contenu avant </body> et avant </html>
                    nouveau_contenu = (
                            contenu[:position_body]
                            + "".join(html_contenu_buffer[chemin_fichier_html])
                            + contenu[position_body:position_html]
                            + contenu[position_html:]
                    )

                    with open(chemin_fichier_html, "w", encoding='utf-8') as f:
                        f.write(nouveau_contenu)

                    print(txt_color("[OK] ", "ok"), translate("mise_a_jour_du", translations),
                          txt_color(f"{chemin_fichier_html}", "ok"))
                    gr.Info(translate("mise_a_jour_du", translations) + f": {chemin_fichier_html}", 3.0)
                    # réinitialise le buffer
                    html_contenu_buffer.pop(chemin_fichier_html, None)
                    return translate("mise_a_jour_du", translations) + f": {chemin_fichier_html}"

            else:  # Fichier n'existe pas
                with open(chemin_fichier_html, 'w', encoding='utf-8') as f:
                    f.write("<!DOCTYPE html>\n")
                    f.write("<html>\n")
                    f.write("<head>\n")
                    f.write("<title>Recutecapitulatif des images</title>\n")
                    f.write(f"<script>{contenu_jquery}</script>\n")
                    f.write(f"<script>{contenu_popupJS}</script>\n")
                    f.write("<script>\n")
                    f.write("$(document).ready(function() {\n")
                    f.write("  $('.image-popup').magnificPopup({\n")
                    f.write("    type: 'image',\n")
                    f.write("    closeOnContentClick: true,  // Ferme la popup en cliquant sur l'image\n")
                    f.write("    closeBtnInside: false,      // Affiche le bouton de fermeture à l'extérieur de l'image\n")
                    f.write("    mainClass: 'mfp-with-zoom', // Ajoute une classe pour une animation de zoom\n")
                    f.write("    image: {\n")
                    f.write("      verticalFit: true, // Ajuste l'image à la hauteur de la fenêtre\n")
                    f.write("      titleSrc: 'title' // Affiche l'attribut 'title' comme titre de l'image dans la popup\n")
                    f.write("    },\n")
                    f.write("    zoom: {\n")
                    f.write("      enabled: true, // Active l'animation de zoom\n")
                    f.write("      duration: 300 // Durée de l'animation de zoom en millisecondes\n")
                    f.write("    }\n")
                    f.write("  });\n")
                    f.write("});\n")
                    f.write("</script>\n")
                    f.write("<style>\n")  # Style CSS personnalisé
                    f.write("body {\n")
                    f.write("  background-color: black;\n")  # Fond noir
                    f.write("  color: white;\n")  # Texte en blanc
                    f.write("  font-family: Arial, sans-serif;\n")  # Police
                    f.write("}\n")
                    f.write(".image-item {\n")
                    f.write("  margin-bottom: 20px;\n")  # Espacement entre les items
                    f.write("}\n")
                    f.write(".image-container {\n")
                    f.write("  display: flex;\n")  # Utilisation de flexbox
                    f.write("  flex-wrap: wrap;\n")  # Pour gérer les débordements
                    f.write("  margin-bottom: 10px;\n")
                    f.write("  padding: 10px;\n")
                    f.write("  background-color: #222;\n")  # Fond sombre pour la zone image
                    f.write("  border-radius: 8px;\n")
                    f.write("}\n")
                    f.write("img {\n")
                    f.write("  max-width: 300px;\n")
                    f.write("  height: auto;\n")
                    f.write("  margin-right: 20px;\n")  # Espacement entre l'image et le tableau
                    f.write("}\n")
                    f.write(".etiquettes {\n")
                    f.write("  flex: 1;\n")  # Permet à la section des étiquettes de prendre le reste de l'espace
                    f.write("}\n")
                    f.write("table {\n")
                    f.write("  width: 100%;\n")
                    f.write("  border-collapse: collapse;\n")
                    f.write("}\n")
                    f.write("th, td {\n")
                    f.write("  padding: 8px;\n")
                    f.write("  border: 1px solid #ddd;\n")
                    f.write("  text-align: left;\n")
                    f.write("}\n")
                    f.write(f"{contenu_CSS}\n")
                    f.write("</style>\n")
                    f.write("</head>\n")
                    f.write("<body>\n")  # Début du body
                    f.write("".join(html_contenu_buffer[chemin_fichier_html]))  # Ajouter le contenu de la première image
                    f.write("</body>\n")  # Fermeture du body
                    f.write("</html>\n")
                print(txt_color("[OK] ", "ok"), translate("fichier_cree", translations), f": {chemin_fichier_html}")
                # reset buffer
                html_contenu_buffer.pop(chemin_fichier_html, None)
                return translate("fichier_cree", translations) + f": {chemin_fichier_html}"
            return translate("mise_a_jour_du", translations) + f": {chemin_fichier_html}"

    except Exception as e:
        print(txt_color("[ERREUR] ", "erreur"), translate("erreur_lors_generation_html", translations), f": {e}")
        raise gr.Error(translate("erreur_lors_generation_html", translations) + f": {e}")
        return translate("erreur_lors_generation_html", translations) + f": {e}"


def charger_configuration():
    """Loads the configuration from the config.json file.
        Args:
        chemin_image (str): config.json file
        Return:
        Return a dictionary with the configuration values
    """

    try:
        # Get the script's directory
        root_dir = Path(__file__).parent.parent
        config_dir = root_dir / "config"
        config_json = config_dir / "config.json"
        chemin_styles = config_dir / "styles.json"
        
        with open(config_json, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        # Convert relative paths to absolute paths if necessary
        for key in ["MODELS_DIR", "VAE_DIR", "SAVE_DIR", "LORAS_DIR", "INPAINT_MODELS_DIR"]:
            if key in config:  # Check if the key exists
                if not os.path.isabs(config[key]):
                    # If it's a relative path, join it with the root directory
                    config[key] = os.path.abspath(os.path.join(root_dir, config[key]))

        # Chargement des styles
        if os.path.exists(chemin_styles):
             with open(chemin_styles, "r", encoding="utf-8") as fichier_styles:
                config["STYLES"] = json.load(fichier_styles)

        else:
             print(f"{txt_color('[ERREUR]','erreur')}", f"Error: styles.json not found at {chemin_styles}")
        
        print(txt_color("[OK] ","ok"),"Configuration successfully loaded")       
        return config

    except FileNotFoundError:
        print(txt_color("[ERREUR] ","erreur"), f"Error loading configuration: config file not found")
        return {}
    except json.JSONDecodeError as e:
        print(txt_color("[ERREUR] ","erreur"), f"Error loading configuration: JSON decode error: {e}")
        return {}
    except Exception as e:
        print(txt_color("[ERREUR] ","erreur"), f"Error loading configuration: An error occurred: {e}")
        return {}

        
        
#fonction pour changer le thème de gradio
def gradio_change_theme(theme):
  """
  Fonction pour choisir un thème Gradio 5 avec match-case.

  Args:
    nom_theme: Le nom du thème à appliquer (str).

  Returns:
    Le thème Gradio 5 correspondant (gr.theme.Theme) ou None si le thème n'existe pas.
  """

  theme = theme.lower() # Pour ignorer la casse

  match theme:
    case "base":
      return gr.themes.Base()
    case "default":
      return gr.themes.Default()
    case "origin":
      return gr.themes.Origin()
    case "citrus":
      return gr.themes.Citrus()
    case "monochrome":
      return gr.themes.Monochrome()
    case "soft":
      return gr.themes.Soft()
    case "glass":
      return gr.themes.Glass()
    case "ocean":
      return gr.themes.Ocean()
    case _:  # Cas par défaut (si aucun thème ne correspond)
      return gr.themes.Default()
      
      
# liste fichiers .safetensors
def lister_fichiers(dir, translations, ext=".safetensors", gradio_mode=False):
    """List files in a directory with a specific extension."""
    
    root_dir = Path(__file__).parent.parent
    # Try to get the list of files from the specified directory.

    if not os.path.isabs(dir):
        dir = os.path.abspath(os.path.join(root_dir, dir))

    fichiers = []
        
    try:
        fichiers = [f for f in os.listdir(dir) if f.endswith(ext)]
        
        # If no files are found, print a specific message and return an empty list.
        if not fichiers:
            print(txt_color("[INFO] ","info"), translate("aucun_modele",translations))
            if gradio_mode:
                gr.Warning(translate("aucun_modele",translations), 4.0)
            return [translate("aucun_modele",translations)]
            
    except FileNotFoundError:
        # If the directory doesn't exist, print a specific error message and return an empty list. 
        print(txt_color("[ERREUR] ","erreur"),translate("directory_not_found",translations),f" {dir}")
        if gradio_mode:
            gr.Warning(translate("repertoire_not_found",translations) + f": {dir}", 3.0)
        return [translate("repertoire_not_found", translations)]
        
    else:
        # If files are found, print them out and return the file_list. 
        print(txt_color("[INFO] ","info"),translate("files_found_in",translations),f" {dir}: {fichiers}")
        if gradio_mode:
            gr.Info(translate("files_found_in",translations) + f": {dir}: \n {translate('nombre_de_fichier',translations)} : {len(fichiers)} \n", 5.0)
        return fichiers
        
        
def telechargement_modele(lien_modele, nom_fichier, models_dir,translations):
    """Télécharge un modèle depuis un lien et l'enregistre dans models_dir."""
    try:
        print(txt_color("[INFO] ","info"),translate("telechargement_modele_commence",translations))
        response = requests.get(lien_modele, stream=True)
        response.raise_for_status()  # Vérifie si le téléchargement a réussi
        taille_totale = int(response.headers.get('content-length', 0))  # Taille du fichier
        
        chemin_destination = os.path.join(models_dir, nom_fichier)  # Chemin complet
        with open(chemin_destination, "wb") as f:
            with tqdm(total=taille_totale, unit='B', unit_scale=True, desc=nom_fichier) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:  # Filtre les chunks vides
                        f.write(chunk)
                        pbar.update(len(chunk))

        print(txt_color("[ok] ","ok"),translate("modele_telecharge",translations), f": {nom_fichier}")
        return True  # Indique que le téléchargement a réussi

    except requests.exceptions.RequestException as e:
        print(txt_color("[ERREUR] ","erreur"),translate("erreur_telechargement_modele",translations), f" : {e}")
        return False  # Indique que le téléchargement a échoué
    except Exception as e:
        print(txt_color("[ERREUR] ","erreur"),translate("erreur_telechargement_modele",translations), f" : {e}")
        return False
        

def txt_color(texte, statut):
    """
    Ajoute de la couleur à un texte en fonction du statut spécifié.

    Args:
        texte (str): La chaîne de caractères à colorer.
        statut (str): Le statut du message, parmi 'info', 'erreur', 'ok'.

    Returns:
        str: La chaîne de caractères colorée en fonction du statut.
             - 'info': retourne le texte en bleu.
             - 'erreur': retourne le texte en rouge.
             - 'ok': retourne le texte en vert.
             Pour tout autre statut ou si le statut n'est pas reconnu,
             retourne le texte sans couleur.
    """
    if statut == "erreur":
        return Fore.RED + texte + Style.RESET_ALL
    elif statut == "ok":
        return Fore.GREEN + texte + Style.RESET_ALL
    elif statut == "info":
        return Fore.CYAN + texte + Style.RESET_ALL
    elif statut == "debug":
        return Fore.MAGENTA + texte + Style.RESET_ALL
    else:
        return texte
        
        
def cprint(*args, statut=None, **kwargs):
    """
    Fonction d'impression personnalisée qui ajoute de la couleur si le paramètre 'statut' est fourni.

    Args:
        *args: Arguments à passer à la fonction print originale.
        statut (str, optional): Le statut pour la coloration ('info', 'erreur', 'ok'). Par défaut: None (pas de couleur).
        **kwargs: Arguments additionnels à passer à la fonction print originale (sep, end, file, flush).
    """
    if statut:
        colored_args = [txt_color(str(arg), statut) for arg in args] # Utilisation d'une compréhension de liste pour simplifier
        print(*colored_args, **kwargs) # Utiliser la fonction print originale (sans la redéfinir)
    else:
        print(*args, **kwargs) # Utiliser la fonction print originale sans coloration 
        # cprint("VRAM détectée :", f'{vram_total_gb:.2f} Go', statut='info')
        
def str_to_bool(s):
    """
    Convertit une chaîne de caractères en une valeur booléenne.

    Cette fonction convertit la chaîne d'entrée en minuscules et vérifie si celle-ci
    correspond à une des valeurs considérées comme représentant True.
    Les valeurs reconnues comme True sont : "true", "1", "yes", "oui", "o", "ok" et "y".
    Toute autre valeur sera évaluée à False.

    Paramètres :
      s (str) : La chaîne de caractères à convertir.

    Retourne :
      bool : True si la chaîne représente une valeur vraie, sinon False.

    Exemples :
      >>> str_to_bool("True")
      True
      >>> str_to_bool("false")
      False
      >>> str_to_bool("1")
      True
      >>> str_to_bool("0")
      False
      False
    """
    if s.lower() in ("true", "1", "yes", "y", "ok", "oui", "o"):
        return True
    else:
        return False


def enregistrer_image(image_pil: Image.Image, chemin_image: str, translations: dict, format_image: str = "JPEG", qualite: int = 95, metadata_to_save=None):
    """
    Enregistre une image PIL sur le disque, en incluant potentiellement des métadonnées préparées
    et en gérant les options de qualité.

    Args:
        image_pil (Image.Image): L'objet image PIL à enregistrer.
        chemin_image (str): Le chemin complet où enregistrer l'image.
        translations (dict): Dictionnaire pour la traduction des messages.
        format_image (str): Format de l'image ('JPEG', 'PNG', 'WEBP', etc.). Par défaut 'JPEG'.
        qualite (int): Qualité pour les formats compressés comme JPEG/WEBP (1-100). Par défaut 95.
        metadata_to_save (PngInfo | bytes | None): Métadonnées préparées par preparer_metadonnees_image.
                                                  Par défaut None.
    """
    if not isinstance(image_pil, Image.Image):
        # Clé de traduction: "erreur_image_invalide_enregistrement" -> "Tentative d'enregistrement d'un objet qui n'est pas une image PIL."
        erreur_msg = translate("erreur_image_invalide_enregistrement", translations)
        print(txt_color("[ERREUR] ", "erreur"), erreur_msg)
        raise gr.Error(erreur_msg) 

    try:
        save_params = {}
        format_upper = format_image.upper()

        if format_upper == "JPG":
            format_upper = "JPEG" 

        if format_upper == "JPEG":
            save_params['quality'] = qualite
            save_params['optimize'] = True
            save_params['progressive'] = True
            # --- Ajout pour EXIF ---
            if metadata_to_save and isinstance(metadata_to_save, bytes):
                save_params['exif'] = metadata_to_save
                print(txt_color("[INFO]", "info"), translate("injection_exif_jpeg", translations))
            elif metadata_to_save:
                print(txt_color("[AVERTISSEMENT]", "erreur"), translate("avertissement_meta_incompatible_jpeg", translations))

        elif format_upper == "PNG":
            save_params['optimize'] = True
            if metadata_to_save and isinstance(metadata_to_save, PngInfo):
                save_params['pnginfo'] = metadata_to_save
                print(txt_color("[INFO]", "info"), translate("injection_pnginfo", translations))
            elif metadata_to_save:
                print(txt_color("[AVERTISSEMENT]", "erreur"), translate("avertissement_meta_incompatible_png", translations))

        elif format_upper == "WEBP":
            save_params['quality'] = qualite
            if metadata_to_save and isinstance(metadata_to_save, bytes):
                save_params['xmp'] = metadata_to_save # Passer les bytes XMP
                print(txt_color("[INFO]", "info"), translate("injection_xmp_webp", translations))
            elif metadata_to_save:
                print(txt_color("[AVERTISSEMENT]", "erreur"), translate("avertissement_meta_incompatible_webp", translations))

        os.makedirs(os.path.dirname(chemin_image), exist_ok=True)

        image_pil.save(chemin_image, format=format_upper, **save_params)

        success_msg = f"{translate('image_sauvegarder', translations)}: {chemin_image}"
        print(txt_color("[OK] ", "ok"), success_msg)

    except FileNotFoundError:
        erreur_msg = f"{translate('erreur_chemin_invalide', translations)}: {chemin_image}"
        print(txt_color("[ERREUR] ", "erreur"), erreur_msg)
        traceback.print_exc()
        raise gr.Error(erreur_msg)
    except IOError as e:

        erreur_msg = f"{translate('erreur_io_sauvegarde', translations)} {chemin_image}: {e}"
        print(txt_color("[ERREUR] ", "erreur"), erreur_msg)
        traceback.print_exc()
        raise gr.Error(erreur_msg)
    except Exception as e:

        erreur_msg = f"{translate('erreur_sauvegarde_image', translations)} {chemin_image}: {e}"
        print(txt_color("[ERREUR] ", "erreur"), erreur_msg)
        traceback.print_exc()
        raise gr.Error(translate("erreur_sauvegarde_image", translations) + f": {e}")
        

class GestionModule:
    """
    Classe pour gérer le chargement et l'initialisation des modules.
    """

    def __init__(
        self,
        modules_dir="modules",
        translations=None,
        language="fr",
        config=None,
        model_manager_instance=None
    ):
        """
        Initialise le gestionnaire de modules.
        """
        self.modules_dir = modules_dir
        self.language = language
        self.translations = translations
        self.modules = {}
        self.tabs = {}
        self.modules_names = []
        self.config = config
        self.js_code = ""
        self.model_manager = model_manager_instance
        

    def verifier_version(self, package_name, min_version):
        """
        Vérifie si le package est installé et satisfait la version minimale requise.
        
        Args:
            package_name (str): Le nom du package tel qu'il est utilisé pour l'installation (ex: "Pillow").
            min_version (str): La version minimale requise (ex: "8.0.0").
        
        Returns:
            (bool, str): Un tuple indiquant si la version est satisfaisante et la version installée (ou None si non installé).
        """
        try:
            installed_version = get_version(package_name)
            if pkg_version.parse(installed_version) >= pkg_version.parse(min_version):
                return True, installed_version
            else:
                return False, installed_version
        except PackageNotFoundError:
            return False, None

    def check_and_install_dependencies(self, module_json_path):
        """
        Vérifie et installe les dépendances d'un module à partir de son fichier JSON.
        La configuration des dépendances dans le JSON peut être soit une liste de chaînes (nom du package)
        ou une liste de dictionnaires avec des clés 'package', 'import' (optionnel) et 'min_version'.

        Exemple de dépendance dans le JSON :
        [
            "numpy",
            {
                "package": "Pillow",
                "import": "PIL",
                "min_version": "8.0.0"
            }
        ]
        """
        try:
            with open(module_json_path, 'r', encoding="utf-8") as f:
                module_data = json.load(f)
        except FileNotFoundError:
            print(txt_color("[ERREUR] ", "erreur"), translate("module_json_not_found", self.translations).format(module_json_path))
            return False
        except json.JSONDecodeError:
            print(txt_color("[ERREUR] ", "erreur"), translate("module_json_decode_error", self.translations).format(module_json_path))
            return False

        if "dependencies" not in module_data:
            print(txt_color("[INFO] ", "info"), translate("module_no_dependencies", self.translations).format(module_json_path))
            return True

        # Chemin vers l'exécutable pip dans l'environnement virtuel
        venv_pip_path = sys.executable.replace("python", "pip")


        dependencies = module_data["dependencies"]

        print(txt_color("[INFO] ", "info"), translate("module_checking_dependencies", self.translations).format(module_data.get('name', 'module')))

        for dep in dependencies:
            # On supporte deux formats : une chaîne ou un dictionnaire
            if isinstance(dep, str):
                package_name = dep
                min_version = None
            elif isinstance(dep, dict):
                package_name = dep.get("package")
                min_version = dep.get("min_version")
                # Optionnellement, on peut utiliser 'import' pour le nom d'import si nécessaire,
                # mais ici on vérifie directement via le nom du package.
            else:
                print(txt_color("[ERREUR] ", "erreur"), f"Dépendance au format inconnu: {dep}")
                continue

            if min_version:
                valid, installed_version = self.verifier_version(package_name, min_version)
                if valid:
                    print(txt_color("[INFO] ", "info"), translate("dependency_already_installed", self.translations).format(f"{package_name} (v{installed_version})"))
                else:
                    if installed_version:
                        print(txt_color("[INFO] ", "info"), translate("dependency_outdated", self.translations).format(package_name, installed_version, min_version))
                    else:
                        print(txt_color("[INFO] ", "info"), translate("dependency_missing", self.translations).format(package_name))
                    try:
                        subprocess.check_call([venv_pip_path, "install", f"{package_name}>={min_version}"])
                        importlib.invalidate_caches()
                        # Vérifier de nouveau
                        valid, installed_version = self.verifier_version(package_name, min_version)
                        if valid:
                            print(txt_color("[INFO] ", "info"), translate("dependency_installed_success", self.translations).format(f"{package_name} (v{installed_version})"))
                        else:
                            print(txt_color("[ERREUR] ", "erreur"), translate("dependency_install_error", self.translations).format(package_name, f"version {installed_version}"))
                            return False
                    except subprocess.CalledProcessError as e:
                        print(txt_color("[ERREUR] ", "erreur"), translate("dependency_install_error", self.translations).format(package_name, e))
                        return False
            else:  # No min_version specified
                spec = importlib.util.find_spec(package_name)
                if spec is None:
                    print(txt_color("[INFO] ", "info"), f"Dependency '{package_name}' missing. Attempting installation...")
                    try:
                        result = subprocess.run([venv_pip_path, "install", package_name], capture_output=True, text=True, check=True)
                       
                        importlib.invalidate_caches()
                        print(txt_color("[INFO] ", "info"), f"Dependency '{package_name}' installed successfully.")
                    except subprocess.CalledProcessError as e:
                        print(txt_color("[ERREUR] ", "erreur"), f"Error installing {package_name}: return code {e.returncode}, stderr:\n{e.stderr}") # Improved error message
                        print(txt_color("[ERREUR] ", "erreur"), translate("dependency_install_manual", self.translations).format(package_name, sys.executable.replace("python", "pip")))
                        return False
                    except FileNotFoundError:
                        print(txt_color("[ERREUR] ", "erreur"), f"pip executable not found at: {venv_pip_path}")
                        print(txt_color("[ERREUR] ", "erreur"), translate("dependency_install_manual", self.translations).format(package_name, sys.executable.replace("python", "pip")))
                        return False
                    except Exception as e:
                        print(txt_color("[ERREUR] ", "erreur"), f"An unexpected error occurred while installing {package_name}: {e}")
                        print(txt_color("[ERREUR] ", "erreur"), translate("dependency_install_manual", self.translations).format(package_name, sys.executable.replace("python", "pip")))
                        return False
                else:
                    print(txt_color("[INFO] ", "info"), f"Dependency '{package_name}' already installed.")

        return True

    def charger_module(self, module_name):
        """
        Charge un module à partir de son nom de fichier et charge ses traductions.

        Args:
            module_name (str): Le nom du fichier du module (sans l'extension .py).

        Returns:
            module: Le module chargé ou None si le chargement a échoué.
        """
        try:
            module_path = os.path.join(self.modules_dir, module_name + "_mod.py")
            metadata_path = os.path.join(self.modules_dir, module_name + "_mod.json")

            if not os.path.exists(module_path):
                print(txt_color("[ERREUR] ", "erreur"), translate("module_not_exist", self.translations).format(module_name))
                return None

            # Check and install dependencies BEFORE importing the module
            if os.path.exists(metadata_path):
                if not self.check_and_install_dependencies(metadata_path):
                    print(txt_color("[ERREUR] ", "erreur"), translate("dependency_install_failed", self.translations).format(module_name))
                    return None


            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)



            # Vérifier si le module a un fichier de métadonnées
            if os.path.exists(metadata_path):
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                    module.metadata = metadata
            else:
                module.metadata = {}

            module.translations = self.charger_traductions_module(module, module_name, self.language)

            self.modules[module_name] = module
            print(txt_color("[OK] ", "ok"), translate("module_loaded", self.translations).format(module_name))
            return module
        except Exception as e:
            print(txt_color("[ERREUR] ", "erreur"), translate("module_load_error", self.translations).format(module_name, e))
            return None

    def charger_traductions_module(self, module, module_name, language):
        """
        Charge les traductions d'un module à partir de son fichier JSON de métadonnées.

        Args:
            module: Le module chargé.
            module_name (str): Le nom du module.
            language (str): La langue à charger (par exemple, "fr", "en").
        """
        if not hasattr(module, "metadata"):
            print(txt_color("[ERREUR] ", "erreur"), translate("module_no_metadata", self.translations).format(module_name))
            return self.translations

        metadata = module.metadata
        module_translations = {}

        if "language" in metadata and language in metadata["language"]:
            return metadata["language"][language]
        else:
            print(txt_color("[ERREUR] ", "erreur"), translate("module_translations_not_found", self.translations).format(module_name, language))
        
        merged_translations = self.translations.copy()
        merged_translations.update(module_translations)

        return merged_translations      

    def initialiser_module(self, module_name, *args, **kwargs):
        """Initialise un module chargé."""
        module = self.modules.get(module_name)
        if module is None:
            print(txt_color("[ERREUR] ", "erreur"), translate("module_not_loaded", self.translations).format(module_name))
            return None

        try:
            init_func_name = module.metadata.get("init_function", "initialize")
            if hasattr(module, init_func_name):
                init_func = getattr(module, init_func_name)
                # Correctly pass only three arguments
                instance = init_func(self.translations, self.model_manager, self, self.config, *args, **kwargs)
                module.instance = instance
                print(txt_color("[OK] ", "ok"), translate("module_initialized", self.translations).format(module_name))
                # Collect JavaScript code if the module has it
                if hasattr(module.instance, "get_module_js"):
                    self.js_code += module.instance.get_module_js()
                return instance
            else:
                print(txt_color("[ERREUR] ", "erreur"), translate("module_no_init_function", self.translations).format(module_name, init_func_name))
                return None
        except Exception as e:
            print(txt_color("[ERREUR] ", "erreur"), translate("module_init_error", self.translations).format(module_name, e))
            return None


    def charger_tous_les_modules(self):
        """Charge tous les modules dans le répertoire spécifié."""
        for filename in os.listdir(self.modules_dir):
            if filename.endswith("_mod.py"):
                print(txt_color("[INFO] ", "info"), translate("module_loading_attempt", self.translations).format(filename))
                # Charger le module
                module_name = filename[:-7]  # Supprimer l'extension _mod.py
                module = self.charger_module(module_name)
                if module:
                    module.translations = self.charger_traductions_module(module, module_name, self.language)
                    # Initialize the module and store the instance
                    instance = self.initialiser_module(module_name)
                    if instance:
                        module.instance = instance
                        self.modules_names.append(module_name)

    def creer_onglet_module(self, module_name, translations):
        """Crée un onglet Gradio à partir d'un module."""
        module = self.modules.get(module_name)
        if module is None:
            print(txt_color("[ERREUR] ", "erreur"), translate("module_not_loaded", self.translations).format(module_name))
            return None

        try:
            module_translations = module.translations if hasattr(module, "translations") else {}
            tab_name = module.metadata.get("tab_name", module_name)

            if hasattr(module, "instance") and hasattr(module.instance, "create_tab"):
                tab = module.instance.create_tab(module_translations)
                self.tabs[module_name] = tab
                print(txt_color("[OK] ", "ok"), translate("tab_created_for_module", self.translations).format(tab_name, module_name))
                return tab
            else:
                # Ne pas traiter comme une erreur si create_tab n'existe pas
                print(txt_color("[ERREUR] ", "erreur"), translate("module_no_create_tab", self.translations).format(module_name))
                return None
        except Exception as e:
            print(txt_color("[ERREUR]", "erreur"), f"Erreur inattendue lors de la création de l'onglet pour {module_name}: {e}")
            traceback.print_exc() # Imprimer la trace pour le débogage
            return None             

    def creer_tous_les_onglets(self, translations):
        """Crée tous les onglets Gradio pour les modules chargés."""
        print(txt_color("[INFO] ", "info"), translate("creating_all_tabs", self.translations))
        for module_name in self.modules:
            self.creer_onglet_module(module_name, self.translations)
    
    def get_loaded_modules(self):
        """Returns a list of the names of the loaded modules."""
        return self.modules_names
    
    def get_js_code(self):
        """Return the javascript code"""
        return self.js_code


# In the check_gpu_availability function
def check_gpu_availability(translations):
    """
    Checks if a CUDA-enabled GPU is available and configures PyTorch accordingly.

    Args:
        translations (dict): The translation dictionary for localized messages.

    Returns:
        tuple: A tuple containing:
            - device (str): The device to use ("cuda" or "cpu").
            - torch_dtype (torch.dtype): The recommended data type (torch.float16 or torch.float32).
            - vram_total_gb (float): The total VRAM in GB (or 0 if no GPU is available).
    """
    if torch.cuda.is_available():
        gpu_device = torch.device(f'cuda:{torch.cuda.current_device()}')
        cpu_device = torch.device('cpu')
        try:
            vram_total_gb = torch.cuda.get_device_properties(gpu_device).total_memory / (1024 ** 3)
        except Exception as e:
            print(txt_color("[ERREUR]", "erreur"), f"Impossible de lire la mémoire GPU via check_gpu_availability: {e}")
            vram_total_gb = 0 # Fallback
        print(translate("vram_detecte", translations), f"{txt_color(f'{vram_total_gb:.2f} Go', 'info')}")

        # Enable expandable_segments if VRAM < 10 GB
        if vram_total_gb < 10:
            os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True max_split_size_mb:512"
            print(translate("pytroch_active", translations))
        # Enable expandable_segments if VRAM < 6 GB
        if vram_total_gb < 6:
            os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True max_split_size_mb:256"
            print(translate("pytroch_active", translations))

        device = gpu_device # Retourner le device local
        torch_dtype = torch.float16
    else:
        print(txt_color(translate("cuda_dispo", translations), "erreur"))
        device = "cpu"
        torch_dtype = torch.float32
        vram_total_gb = 0

    print(txt_color(f'{translate("utilistation_device", translations)} : {str(device)} + dtype {torch_dtype}', 'info'))
    return device, torch_dtype, vram_total_gb

class ImageSDXLchecker:
    def __init__(self, image, global_translations, max_pixels=1048576):
        """
        Initializes the ImageSDXLchecker with an image, translations, and maximum pixel limit.

        Args:
            image (PIL.Image.Image): The image to check and resize.
            global_translations (dict): The global translations dictionary.
            max_pixels (int): The maximum allowed number of pixels in the image.
        """
        self.image = image
        self.translations = global_translations
        self.max_pixels = max_pixels

    def image_est_valide(self, largeur, hauteur):
        """
        Checks if the image dimensions are valid (multiples of 8 and within pixel limit).

        Args:
            largeur (int): The width of the image.
            hauteur (int): The height of the image.

        Returns:
            bool: True if the image is valid, False otherwise.
        """
        return (largeur % 8 == 0) and (hauteur % 8 == 0) and (largeur * hauteur <= self.max_pixels)

    def redimensionner_image(self):
        """
        Resizes the image while preserving aspect ratio if it's not valid.

        Returns:
            PIL.Image.Image: The resized image, or the original image if it was valid.
        """
        if not isinstance(self.image, Image.Image):
            print(txt_color("[ERREUR] ", "erreur"), translate("erreur_type_image_invalide", self.translations).format(type(self.image)))
            gr.Warning(translate("erreur_type_image_invalide", self.translations), 4.0)
            return self.image
        
        try:
            largeur_orig, hauteur_orig = self.image.size
        except AttributeError:
            print(txt_color("[ERREUR] ", "erreur"), translate("erreur_attribut_size_manquant", self.translations).format(type(self.image)))           
            gr.Warning(translate("erreur_attribut_size_manquant", self.translations), 4.0)
            return self.image


        total_pixels = largeur_orig * hauteur_orig

        # If the image is already valid, return it without modification.
        if self.image_est_valide(largeur_orig, hauteur_orig):
            print(txt_color(translate("image_deja_conforme", self.translations), "info"))
            return self.image

        # Calculate the maximum scaling factor without enlarging.
        scale_max = min(1.0, math.sqrt(self.max_pixels / total_pixels))

        if largeur_orig == 0 or hauteur_orig == 0:
            print(txt_color("[ERREUR] ", "erreur"), translate("erreur_dimension_zero", self.translations))
            gr.Warning(translate("erreur_dimension_zero", self.translations), 4.0) # Nouvelle clé
            return self.image

        # Calculate the effective scaling factor to ensure the result is a multiple of 8.
        s_w = ((int(largeur_orig * scale_max) // 8) * 8) / largeur_orig
        s_h = ((int(hauteur_orig * scale_max) // 8) * 8) / hauteur_orig
        s_final = min(s_w, s_h)

        # Apply the scaling factor to get the target dimensions.
        nouvelle_largeur = (int(largeur_orig * s_final) // 8) * 8
        nouvelle_hauteur = (int(hauteur_orig * s_final) // 8) * 8

        # Additional check to avoid getting 0 pixels in extreme cases.
        nouvelle_largeur = max(8, nouvelle_largeur)
        nouvelle_hauteur = max(8, nouvelle_hauteur)

        print(txt_color ("[INFO] ", "info"), translate("redimensionnement_image", self.translations).format(largeur_orig, hauteur_orig, total_pixels, nouvelle_largeur, nouvelle_hauteur))
        try:
            resampling_filter = Image.Resampling.LANCZOS
        except AttributeError:
            resampling_filter = Image.LANCZOS
        
        
        return self.image.resize((nouvelle_largeur, nouvelle_hauteur), resampling_filter)


def styles_fusion(style_selection, prompt_text, base_negative_prompt, styles_config, translations):
    """
    Fusionne les styles sélectionnés avec le prompt utilisateur et gère les prompts négatifs.

    Args:
        style_selection (list): Liste des noms des styles sélectionnés.
        prompt_text (str): Le prompt positif de l'utilisateur (potentiellement traduit).
        base_negative_prompt (str): Le prompt négatif par défaut.
        styles_config (list): La liste complète des dictionnaires de styles.
        translations (dict): Le dictionnaire de traductions.

    Returns:
        tuple: Contenant:
            - final_positive_prompt (str): Le prompt positif final combiné.
            - final_negative_prompt (str): Le prompt négatif final combiné.
            - style_display_names (list): La liste des noms des styles sélectionnés pour l'affichage.
    """
    combined_style_parts = []
    combined_negative_parts = set()
    style_display_names = []

    if style_selection:  # Si au moins un style est sélectionné
        for style_name in style_selection:
            selected_style = next((item for item in styles_config if item["name"] == style_name), None)
            if selected_style:
                style_display_names.append(style_name)
                # Extraire la partie style du prompt positif
                style_prompt_part = selected_style.get("prompt", "").replace("{prompt}", "").strip(", ").strip()
                if style_prompt_part:
                    combined_style_parts.append(style_prompt_part)

                # Ajouter les éléments du prompt négatif du style
                style_neg_prompt = selected_style.get("negative_prompt", "")
                if style_neg_prompt:
                    style_neg_parts = {part.strip() for part in style_neg_prompt.split(',') if part.strip()}
                    combined_negative_parts.update(style_neg_parts)
        # Si des styles sont sélectionnés, combined_negative_parts contient UNIQUEMENT les négatifs des styles.
    else:
        # Aucun style sélectionné -> utiliser le négatif par défaut
        if base_negative_prompt:
            base_neg_parts = {part.strip() for part in base_negative_prompt.split(',') if part.strip()}
            combined_negative_parts.update(base_neg_parts)
        # style_display_names reste vide, ce qui est correct

    # Construire le prompt positif final
    final_style_string = ", ".join(filter(None, combined_style_parts))
    if final_style_string:
        final_positive_prompt = f"{prompt_text}, {final_style_string}"
    else:
        final_positive_prompt = prompt_text

    # Construire le prompt négatif final (string)
    final_negative_prompt = ", ".join(sorted(list(combined_negative_parts)))

    return final_positive_prompt, final_negative_prompt, style_display_names

# Dans Utils/utils.py
import base64 # Assurez-vous que base64 est importé
from pathlib import Path # Assurez-vous que Path est importé

# MODIFIER la signature pour ajouter text_info
def create_progress_bar_html(current_step: int, total_steps: int, progress_percent: int, text_info: str = None, image_fond_name: str = "piste.svg", image_remplissage_name: str = "barre.svg") -> str:
    """
    Génère le code HTML pour une barre de progression personnalisée avec texte et images SVG.

    Args:
        current_step (int): L'étape actuelle de la progression.
        total_steps (int): Le nombre total d'étapes.
        progress_percent (int): Le pourcentage de progression.
        text_info (str, optional): Texte supplémentaire à afficher (ex: "Image 2/4"). Par défaut None.
        image_fond_name (str): Nom du fichier SVG pour la piste.
        image_remplissage_name (str): Nom du fichier SVG pour le remplissage.

    Returns:
        str: La chaîne HTML complète pour la barre de progression.
    """
    # S'assurer que les chemins sont valides pour l'URL CSS (utiliser des slashes)
    root_dir = Path(__file__).parent.parent
    chemin_dossier_utils = root_dir / "html_util"
    # Utiliser les arguments corrects pour les noms de fichiers SVG
    chemin_image_fond = chemin_dossier_utils / image_fond_name
    chemin_image_remplissage = chemin_dossier_utils / image_remplissage_name

    # --- Lire et encoder les SVG en Data URI ---
    def svg_to_data_uri(filepath):
        if not filepath.is_file():
            # Utiliser txt_color ici si vous l'avez importé ou défini dans utils.py
            # Sinon, utiliser un print standard ou le logger
            print(f"[ERREUR Utils] Fichier SVG non trouvé: {filepath}")
            return "none" # Retourne 'none' pour la propriété CSS background-image
        try:
            with open(filepath, "rb") as f: # Lire en binaire
                svg_bytes = f.read()
            # Encoder en Base64
            encoded_svg = base64.b64encode(svg_bytes).decode("utf-8")
            # Créer la Data URI
            return f"data:image/svg+xml;base64,{encoded_svg}"
        except Exception as e:
            print(f"[ERREUR Utils] Erreur lecture/encodage SVG {filepath}: {e}")
            return "none"

    data_uri_fond = svg_to_data_uri(chemin_image_fond)
    data_uri_remplissage = svg_to_data_uri(chemin_image_remplissage)

    # Définir les styles CSS (inchangé)
    css_styles = f"""
    <style>
        .progress-container {{
            position: relative;
            width: 100%;
            height: 25px; /* Ajuste si besoin */
            border-radius: 8px;
            border: 1px solid #555;
            overflow: hidden;
            background-image: url('{data_uri_fond}');
            background-size: cover;
            background-repeat: no-repeat;
            background-position: center center;
        }}
        .custom-progress {{
            appearance: none; -webkit-appearance: none; -moz-appearance: none;
            border: none;
            width: 100%;
            height: 100%;
            position: absolute; top: 0; left: 0;
            background-color: transparent;
            color: #4CAF50;
        }}
        .custom-progress::-webkit-progress-bar {{
            background-image: url('{data_uri_fond}');
            background-size: cover;
            background-repeat: no-repeat;
            background-position: center center;
            border-radius: 8px;
        }}
        .custom-progress::-webkit-progress-value {{
            background-image: url('{data_uri_remplissage}');
            background-size: cover;
            background-repeat: no-repeat;
            background-position: left center;
            border-radius: 8px;
            transition: width 0.1s ease;
        }}
        .custom-progress::-moz-progress-bar {{
            background-image: url('{data_uri_remplissage}');
            background-size: cover;
            background-repeat: no-repeat;
            background-position: left center;
            border-radius: 8px;
            transition: width 0.1s ease;
        }}
        .progress-text-overlay {{
            position: absolute; top: 0; left: 0;
            width: 100%; height: 100%;
            display: flex; align-items: center; justify-content: center;
            font-size: 0.9em;
            color: #fff;
            text-shadow: 0 0 3px #000, 0 0 3px #000;
            line-height: 25px;
            z-index: 1;
            pointer-events: none;
            font-weight: bold;
        }}
    </style>
    """

    # MODIFIER la construction du texte de l'overlay
    progress_text = f"{current_step}/{total_steps} ({progress_percent}%)"
    if text_info: # Ajouter text_info s'il est fourni
        progress_text = f"{text_info} - {progress_text}"

    # Construire l'HTML final (utiliser progress_text)
    progress_html = f'''
        {css_styles}
        <div class="progress-container">
            <progress class="custom-progress" value="{current_step}" max="{total_steps}"></progress>
            <div class="progress-text-overlay">{progress_text}</div>
        </div>
    '''
    return progress_html