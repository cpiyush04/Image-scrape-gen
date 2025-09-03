import re
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse, urljoin
import os
from difflib import SequenceMatcher
import google.generativeai as genai
import requests
from PIL import Image
from io import BytesIO
import dotenv

dotenv.load_dotenv()

def extract_product_name(url: str) -> str:

    # Parse URL path
    path = urlparse(url).path

    # Split by "/" and filter empty parts
    parts = [p for p in path.split("/") if p]

    product_name = None
    for i, p in enumerate(parts):
        if p in {"dp", "p"} and i > 0:
            product_name = parts[i-1]
            break
        elif '-' in p and any(char.isdigit() for char in p):
        # 1. Isolate the part before the file extension (e.g., '.html').
          slug = p.rsplit('.', 1)[0]

          # 2. Split the slug by hyphens.
          name_parts = slug.split('-')

          # 3. Remove any trailing parts that are purely numbers.
          while name_parts and name_parts[-1].isdigit():
              name_parts.pop()

          # 4. Join the remaining words to form the final name.
          # The filter(None, ...) handles empty strings from double hyphens '--'.
          product_name = ' '.join(filter(None, name_parts))
          break

    # Part having Hyphens
    if not product_name:
        candidates = [p for p in parts if "-" in p and not re.match(r"^[A-Z0-9]+$", p)]
        product_name = max(candidates, key=len, default="")

    # Cleanup: replace "-" with spaces, remove redundant stuff
    product_name = re.sub(r"[^a-zA-Z0-9\- ]", " ", product_name)
    product_name = product_name.replace("-", " ").strip()

    return product_name

def save_image(img_url, filename="product.jpg"):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        response = requests.get(img_url, headers=headers, stream=True)
        response.raise_for_status()

        with open(filename, "wb") as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)

        print(f"Image saved as {os.path.abspath(filename)}")

    except Exception as e:
        print(f"Failed to save image: {e}")


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def generate_image_prompt_with_gemini(product_name):

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-pro')

        prompt_template = f"""
        You are a creative assistant specializing in writing prompts for AI image generators.
        Based on the following product name, create a concise, visually descriptive prompt.
        The prompt should describe a professional, high-quality photograph of the product on a clean, neutral background, suitable for an e-commerce website.

        Product Name: "{product_name}"

        Image Prompt:
        """
        print("\nSending product name to Gemini to generate an image prompt...")
        response = model.generate_content(prompt_template)
        image_prompt = response.text.strip()
        return image_prompt

    except Exception as e:
        print(f"An error occurred with the Gemini API: {e}")
        return None

def generate_image_with_stabilityai(prompt):

    STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
    API_URL = "https://api.stability.ai/v2beta/stable-image/generate/ultra"
    filename="generated_image.png"

    print(f"\nSending prompt to Stability AI's new ultra model")

    if not STABILITY_API_KEY:
        raise Exception("Missing Stability AI API key.")

    headers = {
        "authorization": f"Bearer {STABILITY_API_KEY}",
        "accept": "image/*"
    }

    files = {'none': ''}
    data = {
        "prompt": prompt,
        "output_format": "png",
    }

    try:
        response = requests.post(API_URL, headers=headers, files=files, data=data)

        if response.status_code == 200:
            with open(filename, 'wb') as file:
                file.write(response.content)
            print(f"\nImage successfully saved as: {filename}")
        else:
            # Raise an exception with the error details from the API
            raise Exception(f"Error from API: {str(response.json())}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the Stability AI API call: {e}")

    except Exception as e:
        print(f"An error occurred during Gemini image generation: {e}")

def get_img(page_url):

    product_name = extract_product_name(page_url)
    print(product_name)

    print(f"\nGetting image from {page_url}")

    image_found = False

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36", # Changed User-Agent
        }
        response = requests.get(page_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        img_tags = soup.find_all('img')

        best_img_url, best_score = None, -1

        for img in img_tags:
            src_raw = img.get("src", "")
            alt_raw = img.get("alt", "")

            # Absolute URL
            img_url = urljoin(page_url, src_raw)
            src_name = extract_product_name(src_raw).lower()
            alt_name = alt_raw.lower()

            score_src = similarity(product_name, src_name)
            score_alt = similarity(product_name, alt_name)

            # Combine (favor alt if present)
            if score_alt > 0.5:
                score = score_alt
            elif score_src > 0.5:
                score = score_src
            else:
                continue

            if score > best_score:
                best_score, best_img_url = score, img_url

        if best_img_url and best_score >= 0.5:  # threshold
            print(f"Image Found")
            image_found = True
            save_image(best_img_url, "product.jpg")
        else:
            print("No good matching image found")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

    if not image_found:
        img_prompt = generate_image_prompt_with_gemini(product_name)
        print("\nObtained Img Prompt")
        if img_prompt:
            generate_image_with_stabilityai(img_prompt)

#-------------------------------------------------------------------------------

if __name__ == "__main__":

    product_url = input("Enter the product URL: ")
    get_img(product_url)