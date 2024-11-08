from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
from openai import OpenAI
import os
import json
import base64
import os
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from pydantic import BaseModel
import urllib.parse
import time


streamlit_data = {}

app = Flask(__name__)


class clothing(BaseModel):
    Item: str
    Amazon_Search: str

class Outfit(BaseModel):
    Outfit:str
    Article:list[clothing]

# Configure OpenAI API key
load_dotenv()
TWILIO_ACCOUNT_SID=os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN=os.getenv('TWILIO_AUTH_TOKEN')
API_KEY=os.getenv('OPENAI_API_KEY')
EBAY_AFFILIATE_ID = os.getenv("EBAY_AFFILIATE_ID")
EBAY_APP_ID = os.getenv("EBAY_APP_ID")
EBAY_DEV_ID = os.getenv("EBAY_DEV_ID")
EBAY_CERT_ID = os.getenv("EBAY_CERT_ID")

EBAY_ENDPOINT = "https://api.ebay.com/buy/browse/v1/item_summary/search?q="

@app.route("/clothes", methods=['POST'])
def clothes():
    from_number = request.form.get('From')
    if from_number in streamlit_data:
        return json.dumps(streamlit_data[from_number])
    else:
        return json.dumps({"clothes": []})

prompt = """You are the best fashion and accessories finder in the world. When people share photos of outfits with you, you identify each individual item in the outfit—including clothing and accessories—with as much detail as possible. For each item, you provide:

Item: The name of the item, including specific details.

Amazon_Search: A detailed search query string that can be used on Amazon to find that exact item, incorporating all identifiable attributes.

In your Amazon_Search details, include key details such as:
- Gender
- Color
- Shape
- Cut
- Material
- Pattern
- Branding (logos, brand names like Nike, Ralph Lauren, Uniqlo, H&M)
- Style descriptors (e.g., vintage, bohemian, athletic)
- Fit and size descriptors (e.g., slim fit, oversized, cropped)
- Occasion or use-case (e.g., formal, casual, outdoor)
- Type of accessory (e.g., shirt, jumper, dress, peacoat, sunglasses, purses, earrings, bracelets)

IF A BRAND CAN NOT BE IDENTIFIED, SUGGESTING POTENTIAL BRANDS IS ACCEPTABLE.

Your outputs should follow this format exactly:

Item: [Detailed Item Name]
Amazon_Search: [Detailed Search Query String]
Examples:

Item: Men's Black Nike Fleece Jacket with High Collar and Zip-Up Front
Amazon_Search: men's black nike fleece jacket zip-up high collar sherpa relaxed fit athletic wear

Item: Women's White Uniqlo Crew Neck T-Shirt with Short Sleeves
Amazon_Search: women's white uniqlo t-shirt crew neck short sleeve cotton regular fit basic layering

Item: Women's Silver Hoop Earrings with Small Diamonds
Amazon_Search: women's silver hoop earrings with small diamonds sterling silver jewelry elegant accessory

Item: Men's Ray-Ban Aviator Sunglasses with Gold Frame and Green Lenses
Amazon_Search: men's ray-ban aviator sunglasses gold frame green lenses classic pilot style UV protection

Item: Women's Black Leather H&M Crossbody Purse with Gold Chain Strap
Amazon_Search: women's black leather h&m crossbody purse gold chain strap small handbag trendy accessory
Instructions:

Focus on providing as much detail as possible to uniquely identify each clothing item and accessory.
Ensure that all items in the outfit are identified, including accessories like sunglasses, purses, earrings, shoes, etc.
"""

client = OpenAI()

@app.route("/sms", methods=['POST'])
def sms_reply():
    # Extract incoming message information
    from_number = request.form.get('From')
    media_url = request.form.get('MediaUrl0')  # This will be the first image URL


    if media_url:        
        response = requests.get(media_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))

# Check the response to ensure it was successful
        if response.status_code == 200:
            # Get the binary content of the image
            image_content = response.content
            #print("image_content")
            #print(image_content)

            # Convert the binary content to base64 format
            base64_image = base64.b64encode(image_content).decode('utf-8')

            # Create a data URI for the image
            base64_image_data = f"data:image/jpeg;base64,{base64_image}"

            # Print the data URI or use it further
            #print("Data URI for the image:")
            #print(base64_image_data)

            # Analyze the image using OpenAI to determine clothing items
            clothing_items = analyze_image_with_openai(base64_image_data)
            links = {}
            images= {}
            shortDescriptions= {}
            prices= {}
            ebay_access_token = ebay_oauth_flow()
            # Search for the top ebay links for each detected clothing item
            
            
            
            for item in clothing_items.Article:
                links[item.Amazon_Search] = search_ebay(item.Amazon_Search,ebay_access_token)['links'] 

            # Construct a response message with the links for each clothing item
            resp = MessagingResponse()
            for item, urls in links.items():
                message = f"Top links for {item}:\n" 
                for url in urls:
                    short_url = shorten(url)
                    message += short_url + "\n"
                try:
                    resp.message(message)
                except Exception as e:
                    print(f"Error sending message: {e}")
                    resp.message("An error occurred while processing your request.")
            #return str(resp)
            if from_number not in streamlit_data:
                streamlit_data[from_number] = {
                    "clothes": []
                }
            clothes_data = {}
            for item in clothing_items.Article:
                images[item.Amazon_Search+"_image"] = search_ebay(item.Amazon_Search,ebay_access_token)['images']    
                shortDescriptions[item.Amazon_Search+"_shortdescription"] = search_ebay(item.Amazon_Search,ebay_access_token)['shortDescription']    
                prices[item.Amazon_Search+"_price"] = search_ebay(item.Amazon_Search,ebay_access_token)['price']   
            for (item, urls), (desc, name), (detail, desc), (pic, image) in zip(links.items(), images.items(),shortDescriptions.items(),prices.items()):
                clothes_data[item] = {
                    "urls": urls,
                    "images": name,
                    "shortDescription": desc,
                    "price": image
                }
            streamlit_data[from_number]["clothes"].append(clothes_data)
            return str(resp)
        else:
            return "Error: Unable to fetch the image."
    else:
        # Respond if no media is sent
        resp = MessagingResponse()
        resp.message("Please send a screenshot of a TikTok or Reel.")
        return str(resp)

def analyze_image_with_openai(base64_image):
    try:
        # Example of using OpenAI to generate a response about clothing items
        # Assuming OpenAI GPT-4 can analyze text data about images (would need further development for visual analysis)
        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert at structured data extraction. You will be given a photo and should convert it into the given structure."},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": base64_image
                            },
                        },
                    ],
                }
            ],
            response_format=Outfit,
            max_tokens=2000,
        )
        return response.choices[0].message.parsed
    except Exception as e:
        print(f"Error analyzing image with OpenAI: {e}")
        return None

def search_amazon(query,ebay_access_token):
    results= [f"https://www.amazon.com/s?k={query}&page={i}" for i in range(1, 4)]
    print(results)
    return results


def ebay_oauth_flow():
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {base64.b64encode((EBAY_APP_ID + ':' + EBAY_CERT_ID).encode()).decode()}"
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope"
    }

    response = requests.post("https://api.ebay.com/identity/v1/oauth2/token", headers=headers, data=data)

    if response.status_code == 200:
        token_data = response.json()
        access_token = token_data.get("access_token")
        #print(f"Obtained eBay OAuth token: {access_token}")
        return access_token
    else:
        print(f"Failed to obtain eBay OAuth token: {response.status_code} - {response.text}")
        return None   
    
def search_ebay(query,ebay_access_token):
    try:
        headers = {
            "Authorization": f"Bearer {ebay_access_token}",
            "Content-Type": "application/json"
        }
        #print(ebay_access_token)
        url_query=urllib.parse.quote_plus(query)
        endpoint = f"{EBAY_ENDPOINT}{url_query}&limit=3&filter=buyingOptions:{{'FIXED_PRICE'}}&filter=deliveryCountry:US,conditions:{{'NEW'}}"
        response = requests.get(
            endpoint,
            headers=headers
        )
        links={}
        response.raise_for_status()  # Raise an HTTPError for bad responses
        response_data = response.json()
        items = response_data.get("itemSummaries", [])
        links['links'] = [item.get("itemWebUrl") for item in items]
        links['images'] = [item.get("image").get("imageUrl") for item in items]
        links['shortDescription'] = [item.get("shortDescription", "") for item in items]
        links['price'] = [item.get("price", {}).get("value", "") for item in items]
        return links
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        return ["HTTP error occurred"]
    except Exception as err:
        print(f"Other error occurred: {err}")
        return ["An error occurred"]
    
    
    
from flask import Flask, request, jsonify, redirect
import string
import random

app = Flask(__name__)

# Dictionary to store short-to-original URL mappings
url_mapping = {}

# Function to generate a random short code for a URL
def generate_short_code(length=6):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

# Function to shorten a URL
def shorten_url(original_url):
    # Generate a unique short code
    short_code = generate_short_code()
    while short_code in url_mapping:
        short_code = generate_short_code()

    # Store the mapping of short code to original URL
    url_mapping[short_code] = original_url
    
    # Return the short URL
    return f"https://item.wha7.com/{short_code}"

# Function to retrieve the original URL
def retrieve_original_url(short_code):
    return url_mapping.get(short_code, None)

# Flask route to shorten a URL
def shorten(url):
    if not url:
        return jsonify({'error': 'Please provide a long URL'}), 400
    short_url = shorten_url(original_url)
    return {'shortened_url': short_url}

# Flask route to retrieve the original URL and redirect
@app.route('/<short_code>', methods=['GET'])
def retrieve(short_code):
    original_url = retrieve_original_url(short_code)
    if original_url:
        return redirect(original_url)
    else:
        return jsonify({'error': 'Short code not found'}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000,debug=True)
