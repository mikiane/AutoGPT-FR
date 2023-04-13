import requests
import io
import os.path
from PIL import Image
from config import Config
import uuid
import openai
from base64 import b64decode

cfg = Config()

working_directory = "auto_gpt_workspace"

def generate_image(prompt):

    filename = str(uuid.uuid4()) + ".jpg"

    # DALL-E
    if cfg.image_provider == 'dalle':

        openai.api_key = cfg.openai_api_key

        response = openai.Image.create(
            prompt=prompt,
            n=1,
            size="256x256",
            response_format="b64_json",
        )

        print("Image générée pour l'invite :" + prompt)

        image_data = b64decode(response["data"][0]["b64_json"])

        with open(working_directory + "/" + filename, mode="wb") as png:
            png.write(image_data)

        return "Saved to disk:" + filename

    # STABLE DIFFUSION
    elif cfg.image_provider == 'sd':

        API_URL = "https://api-inference.huggingface.co/models/CompVis/stable-diffusion-v1-4"
        headers = {"Authorization": "Bearer " + cfg.huggingface_api_token}

        response = requests.post(API_URL, headers=headers, json={
            "inputs": prompt,
        })

        image = Image.open(io.BytesIO(response.content))
        print("Image Généré pour l'invite :" + prompt)

        image.save(os.path.join(working_directory, filename))

        return "Sauvée sur le disque:" + filename

    else:
        return "Pas de fournisseur d'images défini"
