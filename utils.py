import os
import gradio as gr
import torch
from pathlib import Path
import re
import html
import json


def fichier_recap(chemin_image, etiquettes):
    """
    Enregistre les étiquettes d'une image dans un fichier texte.

    Args:
        chemin_image (str): Chemin vers le fichier image .jpg.
        etiquettes (dict): Dictionnaire d'étiquettes et de leurs valeurs.
    """

    try:
        # 1. Créer le chemin du fichier texte
        nom_fichier_txt = os.path.splitext(os.path.basename(chemin_image))[0] + ".txt"
        chemin_fichier_txt = os.path.join(os.path.dirname(chemin_image), nom_fichier_txt)

        # 2. Écrire les informations dans le fichier texte
        with open(chemin_fichier_txt, 'w') as f:
            f.write(f"Image: {chemin_image}\n")
            for etiquette, valeur in etiquettes.items():
                f.write(f"{etiquette}: {valeur}\n")

        print(f"Les étiquettes ont été enregistrées dans : {chemin_fichier_txt}")

    except Exception as e:
        print(f"Une erreur s'est produite : {e}")
        
  

def enregistrer_etiquettes_image_html(chemin_image, etiquettes):
    """
    Enregistre les étiquettes d'une image dans un fichier HTML avec affichage de l'image et tableau stylisé (sans jQuery UI).
    Gère la réouverture du fichier HTML pour ajouter de nouvelles images.

    Args:
        chemin_image (str): Chemin vers le fichier image .jpg.
        etiquettes (dict): Dictionnaire d'étiquettes et de leurs valeurs.
    """
    chemin_dossier_utils = Path(__file__).parent / "html_util"
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

        # Gestion de l'ouverture et de la fermeture du fichier HTML
        if os.path.exists(chemin_fichier_html):  # Vérifier si le fichier existe
            with open(chemin_fichier_html, "r", encoding='utf-8') as f:
                contenu = f.read()
            
            position_body = contenu.rfind("</body>")
            position_html = contenu.rfind("</html>")
            
            if position_body != -1 and position_html != -1 and position_body < position_html:
                #Insérer le nouveau contenu avant </body> et avant </html>
                nouveau_contenu = (
                contenu[:position_body]
                + image_html
                + contenu[position_body:position_html]
                + contenu[position_html:]
                )
                
                with open(chemin_fichier_html, "w", encoding='utf-8') as f:
                    f.write(nouveau_contenu)
                    
                print(f"Mise à jour : {chemin_fichier_html}")

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
                f.write(image_html)  # Ajouter le contenu de la première image
                f.write("</body>\n")  # Fermeture du body
                f.write("</html>\n")
            print(f"Création du fichier rapport : {chemin_fichier_html}")
    
    except Exception as e:
        print(f"Erreur lors de la génération : {e}")



def charger_configuration():
    """Charge la configuration depuis un fichier JSON.
        Args:
        chemin_image (str): passer en argument le fichier config.json
        Return:
        Return un tableau avec les valeurs de configuration
    """

    try:
        # Récupère le dossier du script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        chemin_dossier_conf = Path(__file__).parent / "config"
        conf_json = chemin_dossier_conf / "config.json"       
        with open(conf_json, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        # Convertir les chemins relatifs en absolus
        for key in ["MODELS_DIR", "VAE_DIR", "SAVE_DIR"]:
            if not os.path.isabs(config[key]):
                config[key] = os.path.join(script_dir, config[key])
        
        
        print("Configuration chargée avec succès.")
        return config
    except Exception as e:
        print(f"Erreur lors du chargement de la configuration : {e}")
        return None
        
        
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