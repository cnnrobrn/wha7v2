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
import re
from pprint import pprint


app = Flask(__name__)



# Configure OpenAI API key
load_dotenv()
TWILIO_ACCOUNT_SID=os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN=os.getenv('TWILIO_AUTH_TOKEN')
API_KEY=os.getenv('OPENAI_API_KEY')
DATABASE_URL= os.getenv("DATABASE_URL")
OXY_USERNAME= os.getenv("OXY_USERNAME")
OXY_PASSWORD= os.getenv("OXY_PASSWORD")

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
    image_data = db.Column(db.Text, nullable=True)  # New column to store the base64 encoded image
    description = db.Column(db.String(1000), nullable=False)
    items = db.relationship('Item', backref='outfit', lazy=True)
    
class Item(db.Model):
    __tablename__ = 'items'
    id = db.Column(db.Integer, primary_key=True)
    outfit_id = db.Column(db.Integer, db.ForeignKey('outfits.id'), nullable=False)
    description = db.Column(db.Text, nullable=True)  # Change to Text to handle longer descriptions
    search = db.Column(db.Text, nullable=True)  # Change to Text to handle longer descriptions
    processed_at =  db.Column(db.Float, nullable=True)
    links = db.relationship('Link', backref='item', lazy=True)

class Link(db.Model):
    __tablename__ = 'links'
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    photo_url = db.Column(db.Text, nullable=True)  # Increased to accommodate long photo URLs
    url = db.Column(db.String(2000), nullable=False)  # Increased to accommodate longer URLs
    price = db.Column(db.String(200), nullable=True)  # Increase length if needed
    title = db.Column(db.String(2000), nullable=False)  # Increased to accommodate longer URLs
    rating = db.Column(db.Float, nullable=True)
    reviews_count = db.Column(db.Integer, nullable=True)
    merchant_name = db.Column(db.String(200), nullable=True)



migrate = Migrate(app, db)



class clothing(BaseModel):
    Item: str
    Amazon_Search: str

class Recommendations(BaseModel):
    Response:str
    Recommendations:list[clothing]

class Outfits(BaseModel):
    Outfits:str
    Response:str
    Purpose:int
    Article:list[clothing]




EBAY_ENDPOINT = "https://api.ebay.com/buy/browse/v1/item_summary/search?q="

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

Item: Men's Black Leather H&M Crossbody Purse with Gold Chain Strap
Amazon_Search: women's black leather h&m crossbody purse gold chain strap small handbag trendy accessory
Instructions:

Focus on providing as much detail as possible to uniquely identify each clothing item and accessory.
Ensure that all items in the outfit are identified, including accessories like sunglasses, purses, earrings, shoes, etc.

You will also be providing a 'response'. This will be the message back to the user and should be largely positive. If the user is asking for feedback constructive feedback should be provided on how the outfit can be improved. This should be done in a way that makes it seem like the user is your best friend. If the user does not ask how the outfit can be improved, comment on the vibes, but don't recommend suggestions!

Determine which of the following the text is most likely to be about and reply with the corresponding number in the purpose field:
- What clothes are in the image -> 1
- An evaluation of the outfit including how it can be improved ->2
- None of the above -> 3
"""

recommendation_prompt ="""You are the best fashion and accessories finder in the world. When people share photos of outfits with you, you will identify each individual item in the outfit—including clothing and accessories—with as much detail as possible. 

To create the Clothing objects, use the following guidelines:

Item: The name of the item, including specific details.

Amazon_Search: A detailed search query string that can be used on Amazon to find that exact item, incorporating all identifiable attributes. Include key details such as:

Gender
Color
Shape
Cut
Material
Pattern
Branding (logos, brand names like Nike, Ralph Lauren, Uniqlo, H&M)
Style descriptors (e.g., vintage, bohemian, athletic)
Fit and size descriptors (e.g., slim fit, oversized, cropped)
Occasion or use-case (e.g., formal, casual, outdoor)
Type of accessory (e.g., shirt, jumper, dress, peacoat, sunglasses, purses, earrings, bracelets)
IF A BRAND CAN NOT BE IDENTIFIED, SUGGESTING POTENTIAL BRANDS IS ACCEPTABLE.

The Response field in the Recommendations class should be a message back to the user. This message should be largely positive. If the user is asking for feedback, constructive feedback should be provided on how the outfit can be improved. This should be done in a way that makes it seem like the user is your best friend. If the user does not ask how the outfit can be improved, comment on the vibes, but don't recommend suggestions!

Example output:

Python
recommendations = Recommendations(
    Response="Wow, you look amazing! That jacket is fire and those jeans fit you perfectly. Love the whole vibe!",
    Recommendations=[
        Clothing(
            Item="Men's Black Nike Fleece Jacket with High Collar and Zip-Up Front",
            Amazon_Search="men's black nike fleece jacket zip-up high collar sherpa relaxed fit athletic wear"
        ),
        Clothing(
            Item="Men's Blue Slim Fit Jeans",
            Amazon_Search="men's blue slim fit jeans denim stretch classic 5-pocket style casual wear"
        ),
        Clothing(
            Item="Men's White Leather Sneakers",
            Amazon_Search="men's white leather sneakers low top lace-up casual wear"
        )
    ]
)

print(recommendations.json())
Use code with caution.

Instructions:

Focus on providing as much detail as possible to uniquely identify each clothing item and accessory.
Ensure that all items in the outfit are identified, including accessories like sunglasses, purses, earrings, shoes, etc.
Output the Recommendations object as a JSON string."""

client = OpenAI()

@app.route("/sms", methods=['POST'])
def sms_reply():
    # Extract incoming message information
    from_number = request.form.get('From')
    media_url = request.form.get('MediaUrl0')  # This will be the first image URL
    text = request.form.get('Body')

    if media_url:        
        response = requests.get(media_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
        if response.status_code == 200:
            image_content = response.content
            base64_image = base64.b64encode(image_content).decode('utf-8')
            clothing_items = process_response(base64_image,from_number,text)

            # Construct response message
            if(clothing_items.Purpose == 1):
                resp = MessagingResponse()
                resp.message(f"{clothing_items.Response}/n you can view the outfit on the Wha7 app. Join the waitlist at https://www.wha7.com/f/5f804b34-9f3a-4bd6-a9e5-bf21e2a9018d")
                return str(resp)
            elif(clothing_items.Purpose == 2):
                resp = MessagingResponse()
                resp.message(f"{clothing_items.Response}")
                return str(resp)
            elif(clothing_items.Purpose == 3):
                resp = MessagingResponse()
                resp.message("I'm sorry, I'm not sure how to respond to that. Can you retry?")
                return str(resp)
        else:
            return "Error: Unable to fetch the image."
    else:
        resp = MessagingResponse()
        resp.message("Please send a screenshot of a TikTok or Reel. You can access outfits you've already shared on our app or after signing up via https://www.wha7.com/f/5f804b34-9f3a-4bd6-a9e5-bf21e2a9018d")
        return str(resp)


@app.route("/ios/consultant", methods=['POST'])
def ios_consultant():
    data = request.get_json()
    image_content = data.get('image_content')
    text = data.get('text')
    from_number = format_phone_number(data.get('from_number'))
    Clothing_Items = process_response(image_content, from_number, text, prompt_text=recommendation_prompt, format=Recommendations)
    
    return jsonify({
        "response": Clothing_Items.Response,
        "recommendations": [
            {
                "Item": article.Item,
                "Amazon_Search": article.Amazon_Search,
                "Recommendation_ID": get_recommendation_id(article.Item)
            } 
            for article in (Clothing_Items.Recommendations or [])
        ]
    })

@app.route("/ios", methods=['POST'])
def ios_image():
    # Get data from request body instead of args
    data = request.get_json()  # For JSON data
    image_content = data.get('image_content')
    from_number = format_phone_number(data.get('from_number'))
    process_response(image_content, from_number,text=None)
    return "success"  # Return a response

def analyze_text_with_openai(text=None, true_prompt=prompt,format=Outfits):
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
                            "text": true_prompt,
                        },
                        {
                            "type": "text",
                            "text": f"The user sent the following text: {text}",
                        },
                    ],
                }
            ],
            response_format=format,
            max_tokens=2000,
        )
        return response.choices[0].message.parsed
    except Exception as e:
        print(f"Error analyzing image with OpenAI: {e}")
        return None   
def analyze_image_with_openai(base64_image=None,text=None,true_prompt=prompt,format=Outfits):
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
                            "text": true_prompt,
                        },
                        {
                            "type": "text",
                            "text": f"The user sent the following text: {text}",
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
            response_format=format,
            max_tokens=2000,
        )
        return response.choices[0].message.parsed
    except Exception as e:
        print(f"Error analyzing image with OpenAI: {e}")
        return None
def process_response(base64_image,from_number,text,prompt_text=prompt,format=Outfits):
    if base64_image:
        base64_image_data = f"data:image/jpeg;base64,{base64_image}"
        clothing_items = analyze_image_with_openai(base64_image_data,text,prompt_text,format)
        database_commit(clothing_items, from_number, base64_image_data)
    else:
        clothing_items = analyze_text_with_openai(text=text,true_prompt=prompt_text,format=format)      
    return clothing_items
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
def database_commit(clothing_items, from_number, base64_image_data = None):
    # Extract the items from the parsed response
            # Save to PostgreSQL
            # Create or get the PhoneNumber
    phone = PhoneNumber.query.filter_by(phone_number=from_number).first()
    if not phone:
        phone = PhoneNumber(phone_number=from_number)
        db.session.add(phone)
        db.session.commit()

        # Create a new Outfit
    outfit = Outfit(phone_id=phone.id,image_data=base64_image_data ,description="Outfit from image")
    db.session.add(outfit)
    db.session.commit()
            
    if clothing_items.Article != None:
        for item in clothing_items.Article:
            new_item = Item(outfit_id=outfit.id, description=item.Item, search=item.Amazon_Search, processed_at=None)
            db.session.add(new_item)
            db.session.commit()
    else:
        print("No items found in clothing_items.Article")
        # for link in item['Amazon_Search']:
        #     new_link = Link(item_id=new_item.id, url=link['url'], title=link['title'], photo_url=link['photo_url'], price=link['price'])
        #     db.session.add(new_link)
        #     db.session.commit()
    return None
def format_phone_number(phone_number):
    phone_number = phone_number.strip().replace("-", "").replace("(", "").replace(")", "").replace(" ", "").replace("+1", "")
    if not phone_number.startswith("+1"):
        phone_number = "+1" + phone_number
    return phone_number
def get_recommendation_id(item_description):
    flask_api_url = "https://access.wha7.com/rag_search"  # Replace with your actual URL
    response = requests.post(flask_api_url, json={"item_description": item_description})
    if response.status_code == 200:
        return response.json()["item_id"]  # Assuming your API returns the item_id
    else:
        # Handle error (e.g., log the error, return a default value)
        return None

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
    db.create_all()

