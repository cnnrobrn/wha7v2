from flask import Flask, request, jsonify, redirect
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
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship, sessionmaker
import psycopg2
from flask_migrate import Migrate, upgrade


app = Flask(__name__)



# Configure OpenAI API key
load_dotenv()
TWILIO_ACCOUNT_SID=os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN=os.getenv('TWILIO_AUTH_TOKEN')
API_KEY=os.getenv('OPENAI_API_KEY')
EBAY_AFFILIATE_ID = os.getenv("EBAY_AFFILIATE_ID")
EBAY_APP_ID = os.getenv("EBAY_APP_ID")
EBAY_DEV_ID = os.getenv("EBAY_DEV_ID")
EBAY_CERT_ID = os.getenv("EBAY_CERT_ID")
DATABASE_URL= os.getenv("DATABASE_URL")

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class PhoneNumber(db.Model):
    __tablename__ = 'phone_numbers'
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    outfits = db.relationship('Outfit', backref='phone_number', lazy=True)

class Outfit(db.Model):
    __tablename__ = 'outfits'
    id = db.Column(db.Integer, primary_key=True)
    phone_id = db.Column(db.Integer, db.ForeignKey('phone_numbers.id'), nullable=False)
    description = db.Column(db.String(1000), nullable=False)
    items = db.relationship('Item', backref='outfit', lazy=True)


class Item(db.Model):
    __tablename__ = 'items'
    id = db.Column(db.Integer, primary_key=True)
    outfit_id = db.Column(db.Integer, db.ForeignKey('outfits.id'), nullable=False)
    url = db.Column(db.String(2000), nullable=False)  # Increased to accommodate longer URLs
    price = db.Column(db.String(200), nullable=True)  # Increase length if needed
    ebay_short_description = db.Column(db.Text, nullable=True)  # Change to Text to handle longer descriptions
    photo_url = db.Column(db.String(2000), nullable=True)  # Increased to accommodate long photo URLs



streamlit_data = {}

migrate = Migrate(app, db)


class clothing(BaseModel):
    Item: str
    Amazon_Search: str

class Outfits(BaseModel):
    Outfits:str
    Article:list[clothing]



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
Amazon_Search: women's white uniqlo t-shirt crew neck short sleeve cotton regular fit basic layering small tent logo on right chest

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
        if response.status_code == 200:
            image_content = response.content
            base64_image = base64.b64encode(image_content).decode('utf-8')
            base64_image_data = f"data:image/jpeg;base64,{base64_image}"
            clothing_items = analyze_image_with_openai(base64_image_data)
            
            # Search for eBay links
            ebay_access_token = ebay_oauth_flow()
            links = {}
            images = {}
            shortDescriptions = {}
            prices = {}
            
            for item in clothing_items.Article:
                ebay_list = search_ebay(item.Amazon_Search, ebay_access_token)
                links[item.Amazon_Search] = ebay_list['links'] 
                images[item.Amazon_Search+"_image"] = ebay_list['images']    
                shortDescriptions[item.Amazon_Search+"_shortdescription"] = ebay_list['shortDescription']    
                prices[item.Amazon_Search+"_price"] = ebay_list['price']   
            
            # Save to PostgreSQL
            # Create or get the PhoneNumber
            phone = PhoneNumber.query.filter_by(phone_number=from_number).first()
            if not phone:
                phone = PhoneNumber(phone_number=from_number)
                db.session.add(phone)
                db.session.commit()

            # Create a new Outfit
            outfit = Outfit(phone_id=phone.id, description="Outfit from image")
            db.session.add(outfit)
            db.session.commit()

            # Add Items to the outfit
            for (item, urls), (desc, name), (detail, desc_value), (pic, image) in zip(links.items(), images.items(), shortDescriptions.items(), prices.items()):
                new_item = Item(
                    outfit_id=outfit.id,
                    url=urls,
                    price=image,
                    ebay_short_description=desc_value,
                    photo_url=name
                )
                db.session.add(new_item)
            
                db.session.commit()

            # Construct response message
            resp = MessagingResponse()
            for item, urls in links.items():
                message = f"Top links for {item}:\n" 
                for url in urls:
                    short_url = shorten_url(url)
                    message += short_url + "\n"
                try:
                    resp.message(message)
                except Exception as e:
                    print(f"Error sending message: {e}")
                    resp.message("An error occurred while processing your request.")
            return str(resp)
        else:
            return "Error: Unable to fetch the image."
    else:
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
            response_format=Outfits,
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

# Flask route to retrieve the original URL and redirect
@app.route('/<short_code>', methods=['GET'])
def retrieve(short_code):
    original_url = retrieve_original_url(short_code)
    if original_url:
        return redirect(original_url)
    else:
        return jsonify({'error': 'Short code not found'}), 404



def shorten_url(long_url):
    # Define the endpoint URL (change port if necessary)
    url = 'https://item.wha7.com/shorten'

    # Prepare the headers and payload
    headers = {'Content-Type': 'application/json'}
    payload = {
        'long_url': long_url
    }

    # Send a POST request
    response = requests.post(url, headers=headers, data=json.dumps(payload))

    # Handle the response
    if response.status_code == 200:
        return(response.json().get('shortened_url'))
    else:
        print('Error:', response.json().get('error'))
        return None

if __name__ == "__main__":
    db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)