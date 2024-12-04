# Standard library imports
import base64
import json
import os
import tempfile
import urllib.parse
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from typing import List, Tuple, Optional

# Web framework and database
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.orm import sessionmaker

# Third-party utilities
import psutil
import psycopg2
from dotenv import load_dotenv
from pydantic import BaseModel

# Image processing and computer vision
import cv2
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim

# Communication and API services
import requests
from openai import OpenAI
from twilio.twiml.messaging_response import MessagingResponse


# Concurrency and logging
from concurrent.futures import ThreadPoolExecutor
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# wha7_models imports
from wha7_models import init_db, PhoneNumber, Outfit, Item, Link, ReferralCode, Referral

# Create Flask app and db instance
app = Flask(__name__)
CORS(app)

# Load environment variables
load_dotenv()
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
API_KEY = os.getenv('OPENAI_API_KEY')
DATABASE_URL = os.getenv("DATABASE_URL")
OXY_USERNAME = os.getenv("OXY_USERNAME")
OXY_PASSWORD = os.getenv("OXY_PASSWORD")
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME')
INSTAGRAM_PASSWORD = os.getenv('INSTAGRAM_PASSWORD')
INSTAGRAM_ACCESS_TOKEN = os.getenv('INSTAGRAM_ACCESS_TOKEN')
INSTAGRAM_BUSINESS_ACCOUNT_ID = os.getenv('INSTAGRAM_BUSINESS_ACCOUNT_ID')
WEBHOOK_VERIFY_TOKEN = os.getenv('WEBHOOK_VERIFY_TOKEN')  # Add this to your .env file
GRAPH_API_URL = "https://graph.instagram.com/v12.0"


# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy
db = SQLAlchemy()
db.init_app(app)

# Initialize migrations - add this line
migrate = Migrate(app, db)

# Initialize database engine from wha7_models
engine, session_factory = init_db()

# Create all tables and initialize migrations
with app.app_context():
    db.create_all()
    migrate = Migrate(app, db)
    
# Your pydantic models remain the same
class clothing(BaseModel):
    Item: str
    Amazon_Search: str

class Recommendations(BaseModel):
    Response: str
    Recommendations: list[clothing]

class Outfits(BaseModel):
    Outfits: str
    Response: str
    Purpose: int
    Article: list[clothing]


EBAY_ENDPOINT = "https://api.ebay.com/buy/browse/v1/item_summary/search?q="

prompt = """You are the world's premier fashion and accessories finder, specializing in exact item identification. When analyzing outfit photos, you identify every single component with precise, searchable detail.

For each identified item, provide:

Item: Exhaustively detailed item name including all visible characteristics
Amazon_Search: Ultra-specific search string optimized for exact item matching

Required details for Amazon_Search (include ALL that apply):

1. Core Identity:
- Exact gender designation (men's, women's, unisex, boys', girls')
- Precise size range (XXS-4XL, numeric sizes, etc.)
- Target age group (adult, junior, youth)
- Season/year specificity (Spring 2024, etc.)

2. Visual Specifications:
- Primary color (including shade: navy blue, forest green, etc.)
- Secondary colors
- Color placement
- Pattern type and scale (small polka dots, wide stripes, etc.)
- Pattern direction
- Pattern spacing
- Surface texture (ribbed, smooth, distressed, etc.)
- Finish type (matte, glossy, metallic, etc.)
- Print placement
- Graphics/artwork details

3. Construction Details:
- Primary material (100% cotton, wool blend, etc.)
- Material weight (lightweight, medium-weight, etc.)
- Secondary materials
- Fabric structure (woven, knit, etc.)
- Thread count/density
- Lining material
- Manufacturing technique
- Care requirements

4. Design Elements:
- Exact fit description (slim fit, relaxed fit, etc.)
- Cut specifics (regular cut, athletic cut, etc.)
- Rise height (low-rise, mid-rise, high-rise)
- Length measurements
- Sleeve type and length
- Neckline style
- Collar type
- Cuff style
- Hem style
- Closure type (button, zipper, etc.)
- Button type/material
- Zipper type/color
- Pocket style and placement
- Seam details
- Decorative elements
- Hardware specifications

5. Brand Information:
- Brand name (if visible)
- Sub-brand/line
- Collection name
- Alternative brand suggestions (if brand unclear)
- Price tier indication
- Logo placement
- Logo size
- Logo color

6. Usage/Style Context:
- Specific occasion type
- Activity suitability
- Weather appropriateness
- Style category
- Fashion era/influence
- Trend alignment
- Dress code category

7. Accessory-Specific Details:
For Jewelry:
- Metal type and quality
- Stone types and cuts
- Setting style
- Clasp type
- Measurements
- Finish
- Cultural influences

For Bags:
- Exact dimensions
- Compartment count
- Interior features
- Strap type/length
- Hardware finish
- Corner protection
- Base structure

For Shoes:
- Sole material
- Heel height/type
- Toe shape
- Insole material
- Arch support type
- Lacing system
- Tread pattern

For Watches:
- Movement type
- Case material/size
- Band material/width
- Face details
- Water resistance
- Special features

Example outputs:

Item: Men's Nike Dri-FIT Run Division Sphere Running Jacket Spring 2024 Collection
Amazon_Search: mens nike dri-fit run division sphere jacket black reflective details full zip mock neck moisture wicking lightweight running performance wear spring 2024 collection side zip pockets mesh panels back ventilation regular fit weather resistant

Item: Women's Tiffany & Co. Elsa Peretti Open Heart Pendant Sterling Silver 2024
Amazon_Search: womens tiffany co elsa peretti open heart pendant necklace sterling silver 16 inch chain spring 2024 collection classic design polished finish lobster clasp gift packaging included authentic hallmark

Classification Purpose Field:
1 - Image clothing identification
2 - Outfit evaluation with improvement suggestions
3 - Other topics

Response Guidelines:
- For feedback requests: Provide warm, constructive suggestions while maintaining a best-friend tone
- Without feedback requests: Focus on positive outfit assessment without suggestions
- Always maintain enthusiastic, supportive language
- Reference specific styling choices positively
- Use contemporary fashion vocabulary
- Incorporate trending style concepts from 2024"""

recommendation_prompt ="""You are the world's premier fashion and accessories consultant, specializing in contemporary style optimization and personalized recommendations. Your expertise covers all current trends through 2024 and you provide advice in a warm, encouraging, and professional manner.

To generate Clothing recommendations, strictly follow these comprehensive guidelines:

Item: Provide a detailed description of the recommended item, including all relevant specifications.

Amazon_Search: Create a precise search query optimized for Amazon, incorporating these mandatory elements:

1. Core Characteristics:
- Gender specification (men's, women's, unisex)
- Size category (plus, petite, regular, tall)
- Age group (adult, junior, teen)
- Season (spring/summer 2024, fall/winter 2023-24)

2. Visual Elements:
- Primary and secondary colors
- Patterns and prints
- Texture and finish
- Design details (ruffles, pleats, distressing, etc.)

3. Construction:
- Material composition
- Fabric weight/type
- Construction method (knitted, woven, etc.)
- Care requirements

4. Style Attributes:
- Fit description (relaxed, slim, oversized, etc.)
- Cut details (crop length, neckline type, sleeve style)
- Silhouette
- Rise (for bottoms)
- Length
- Closure type

5. Brand & Marketing:
- Brand name (if known)
- Style category (streetwear, formal, athletic, etc.)
- Collection or line (if applicable)
- Suggested alternative brands (if primary brand unknown)

6. Usage Context:
- Occasion type
- Activity suitability
- Weather appropriateness
- Dress code compliance
- Styling versatility

7. Accessories Specific:
- Material grade/quality
- Hardware details
- Dimensions
- Closure mechanisms
- Special features
- Storage/compartments (for bags)
- Setting type (for jewelry)

The Response field must include:

1. Enthusiasm and Authenticity:
- Genuine, personalized compliments
- Recognition of successful styling choices
- Acknowledgment of personal style

2. If Feedback Requested:
- Constructive suggestions framed positively
- Specific, actionable improvements
- Alternative styling options
- Proportion and balance recommendations
- Color harmony suggestions
- Accessorizing tips
- Seasonal appropriateness advice

3. If No Feedback Requested:
- Positive reinforcement of current choices
- Discussion of outfit cohesion
- Appreciation of personal style expression
- Commentary on overall aesthetic
- Validation of styling decisions

Example output:

recommendations = Recommendations(
    Response="Obsessed with your style game! 🔥 The structured blazer creates such a powerful silhouette, and those high-waisted trousers are absolutely perfect for your frame. The minimalist vibe you're channeling is totally on-trend for 2024! Since you asked for suggestions, I'm thinking we could elevate this even further with some contemporary accessories. A delicate layered necklace would add just the right amount of sparkle, and swapping those shoes for a pair of trending platform loafers would give you that fashion-forward edge while maintaining the polished look.",
    Recommendations=[
        Clothing(
            Item="14K Gold Plated Layered Necklace Set, Dainty Paperclip Chain with Cuban Link Chain, 16-18 inch Adjustable Length, Perfect for Layering",
            Amazon_Search="Womens dainty layered necklace set 14k gold plated paperclip chain contemporary minimalist jewelry 2024 trend adjustable length professional wear"
        ),
        Clothing(
            Item="Women's Platform Loafers, Genuine Leather, Chunky Lug Sole, Square Toe, Black, Gold Hardware, Winter 2024 Style",
            Amazon_Search="Womens platform loafers genuine leather chunky sole square toe black gold hardware professional trending 2024 winter footwear"
        )
    ]
)

Output the Recommendations object as a JSON string, ensuring all entries follow current fashion trends and availability."""

client = OpenAI()


@app.route("/sms", methods=['POST'])
def sms_reply():
    # Extract incoming message information
    db.create_all()
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
                resp.message(f"{clothing_items.Response} You can view the outfit on the Wha7 app. Join the waitlist at https://www.wha7.com/f/5f804b34-9f3a-4bd6-a9e5-bf21e2a9018d")
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

def format_phone_number(phone_number):
    phone_number = phone_number.strip().replace("-", "").replace("(", "").replace(")", "").replace(" ", "").replace("+1", "")
    if not phone_number.startswith("+1"):
        phone_number = "+1" + phone_number
    return phone_number

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
            max_tokens=5000,
        )
        return response.choices[0].message.parsed
    except Exception as e:
        print(f"Error analyzing image with OpenAI: {e}")
        return None   
def analyze_image_with_openai(base64_image,text="",true_prompt=prompt,format=Outfits):
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
            max_tokens=5000,
        )
        return response.choices[0].message.parsed
    except Exception as e:
        print(f"Error analyzing image with OpenAI: {e}")
        return None

def process_response(base64_image, from_number=None, text="", prompt_text=prompt, format=Outfits, instagram_username=None, video=False):
    if base64_image:
        base64_image_data = f"data:image/jpeg;base64,{base64_image}"
        clothing_items = analyze_image_with_openai(base64_image_data, text, prompt_text, format)
        if format == Outfits and video == False:
            database_commit(clothing_items, from_number, base64_image_data, instagram_username)
    else:
        clothing_items = analyze_text_with_openai(text=text, true_prompt=prompt_text, format=format)      
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

def get_recommendation_id(item_description):
    flask_api_url = "https://access.wha7.com/rag_search"  # Replace with your actual URL
    response = requests.post(flask_api_url, json={"item_description": item_description})
    if response.status_code == 200:
        return response.json()["item_id"]  # Assuming your API returns the item_id
    else:
        # Handle error (e.g., log the error, return a default value)
        return "Error"

def database_commit(clothing_items, from_number, base64_image_data=None, instagram_username=None):
    with app.app_context():
        Session = session_factory()
        try:
            # First check if there's an existing record with this Instagram username
            phone = None
            if instagram_username:
                phone = Session.query(PhoneNumber).filter_by(instagram_username=instagram_username).first()
            
            # If no record found by Instagram username, try finding by phone number
            if not phone and from_number:
                phone = Session.query(PhoneNumber).filter_by(phone_number=from_number).first()
            
            # If still no record found, create a new one
            if not phone:
                phone = PhoneNumber(
                    phone_number=from_number,
                    instagram_username=instagram_username
                )
                Session.add(phone)
                Session.commit()
            else:
                # Update existing record if needed
                if instagram_username and not phone.instagram_username:
                    phone.instagram_username = instagram_username
                    Session.commit()
                elif from_number and not phone.phone_number:
                    phone.phone_number = from_number
                    Session.commit()

            # Create a new Outfit
            outfit = Outfit(phone_id=phone.id, image_data=base64_image_data, description="Outfit from image")
            Session.add(outfit)
            Session.commit()
                    
            if clothing_items.Article is not None:
                for item in clothing_items.Article:
                    new_item = Item(
                        outfit_id=outfit.id, 
                        description=item.Item, 
                        search=item.Amazon_Search, 
                        processed_at=None
                    )
                    Session.add(new_item)
                    Session.commit()
            else:
                print("No items found in clothing_items.Article")
        finally:
            Session.close()

def get_unread_messages():
    """Fetch unread direct messages"""
    try:
        url = f"https://graph.facebook.com/v18.0/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/messages"
        params = {
            'access_token': INSTAGRAM_ACCESS_TOKEN,
            'fields': 'message,from,attachments'
        }
        response = requests.get(url, params=params)
        return response.json().get('data', [])
    except Exception as e:
        print(f"Error fetching messages: {e}")
        return []

def send_instagram_reply(user_id, message):
    """Send reply to Instagram user"""
    try:
        url = f"https://graph.facebook.com/v18.0/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/messages"
        data = {
            'recipient': {'id': user_id},
            'message': {'text': message},
            'access_token': INSTAGRAM_ACCESS_TOKEN
        }
        response = requests.post(url, json=data)
        return response.json()
    except Exception as e:
        print(f"Error sending reply: {e}")
        return None

@app.route("/instagram_webhook", methods=['GET'])
def verify_webhook():
    """Handle the initial webhook verification from Instagram"""
    # Get verify token and challenge from the request
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    # Check if mode and token are in the request
    if mode and token:
        # Check the mode and token sent match your verify token
        if mode == 'subscribe' and token == WEBHOOK_VERIFY_TOKEN:
            # Respond with the challenge token from the request
            print("WEBHOOK_VERIFIED")
            return challenge
        else:
            # Respond with '403 Forbidden' if verify tokens do not match
            print("Verification failed - token mismatch")
            return jsonify({'error': 'Verification failed'}), 403

    print("Invalid verification request")
    return jsonify({'error': 'Invalid verification request'}), 400

@app.route("/instagram_webhook", methods=['POST'])
def handle_instagram_messages():
    """Handle incoming Instagram messages webhook"""
    try:
        webhook_data = request.json
        print("1. Webhook received")
        print(f"Received webhook data: {json.dumps(webhook_data, indent=2)}")

        if webhook_data.get('object') == 'instagram' and webhook_data.get('entry'):
            print("2. Valid Instagram webhook")
            
            for entry in webhook_data['entry']:
                print("3. Processing entry")
                
                messaging_list = entry.get('messaging', [])
                if not messaging_list:
                    print("No messaging field found in entry")
                    continue
                    
                for messaging in messaging_list:
                        
                    # Extract sender ID
                    sender_id = messaging.get('sender', {}).get('id')
                    if sender_id and sender_id != "17841416291146051":
                        # Fetch the username using the sender ID
                        sender_username = get_username(sender_id)
                        if sender_username:
                            print(f"Sender ID: {sender_id}, Username: {sender_username}")
                        else:
                            print(f"Could not fetch username for Sender ID: {sender_id}")
                    else:
                        print("No sender ID found in the messaging item.")
                        continue
                    print(f"5. Found sender ID: {sender_id} with username: {sender_username}")

                    # Extract message content
                    message = messaging.get('message', {})
                    if not message:
                        print("No message content found")
                        continue

                    attachments = message.get('attachments', [])
                    if not attachments:
                        print("No attachments found")
                        reply = send_graph_api_reply(sender_id, "Please send a screenshot of a TikTok or Reel. You can access outfits you've already shared on our app or after signing up via https://www.wha7.com/f/5f804b34-9f3a-4bd6-a9e5-bf21e2a9018d")
                        continue

                    # Process the first attachment
                    attachment = attachments[0]
                    media_type = attachment.get('type', '')
                    media_url = attachment.get('payload', {}).get('url')
                    
                    if not media_url:
                        continue
                    try:
                        # Check if the media is a video/reel
                        if media_type in ['video', 'ig_reel']:
                            send_graph_api_reply(sender_id,"🎬 Exciting reel spotted! Let's see what we've got...")

                            reply = process_reels_with_clothing_detection(media_url, sender_username,sender_id)

                        else:
                            # Handle image processing as before
                            media_response = requests.get(media_url)
                            print(f"9. Media fetch status: {media_response.status_code}")
                            send_graph_api_reply(sender_id,"Post recieved. Processing now. Please wait...")
                            
                            if media_response.status_code == 200:
                                image_content = media_response.content
                                send_graph_api_reply(sender_id,"📸 Capturing your moment...")
                                base64_image = base64.b64encode(image_content).decode('utf-8')
                                send_graph_api_reply(sender_id,"✨ Photo received! Working some magic ⚡")

                                try:
                                    clothing_items = process_response(
                                        base64_image, 
                                        None, 
                                        "", 
                                        instagram_username=sender_username
                                    )
                                    send_graph_api_reply(sender_id,"🎨 Almost ready to share your masterpiece! 🌟")

                                    if hasattr(clothing_items, 'Purpose'):
                                        if clothing_items.Purpose == 1:
                                            reply = f"{clothing_items.Response} We found the following items:"
                                            for items in clothing_items.Article:
                                                reply += f"\n - {items.Item}"
                                            reply += "\n \n You can view the outfit on the Wha7 app. Download from the App Store!"
                                        elif clothing_items.Purpose == 2:
                                            reply = clothing_items.Response
                                        else:
                                            reply = "I'm sorry, I'm not sure how to respond to that. Can you retry?"
                                        
                                        response = send_graph_api_reply(sender_id, reply)
                                        print(f"12. Final response: {response}")
                                except Exception as e:
                                    print(f"Error in processing response: {e}")
                                    send_graph_api_reply(sender_id, "Sorry, I had trouble processing your image. Please try again.")
                            else:
                                print(f"Media fetch failed with status {media_response.status_code}")
                                send_graph_api_reply(sender_id, "Sorry, I couldn't access your image. Please try sending it again.")
                    except Exception as e:
                        print(f"Error processing media: {e}")
                        send_graph_api_reply(sender_id, "Sorry, there was an error processing your media. Please try again.")

        return jsonify({'status': 'success'}), 200
    
    except Exception as e:
        print(f"Error in webhook handler: {str(e)}")
        return jsonify({'error': str(e)}), 500

def send_graph_api_reply(user_id, message):
    """Send reply using Instagram Graph API"""
    try:
        url = "https://graph.instagram.com/v12.0/me/messages"
        headers = {
            'Authorization': f'Bearer {INSTAGRAM_ACCESS_TOKEN}'
        }
        data = {
            'recipient': {'id': user_id},
            'message': {'text': message}
        }
        response = requests.post(url, headers=headers, json=data)
        response_json = response.json()
        return response_json
    except Exception as e:
        print(f"Error sending message: {str(e)}")
        raise

def get_username(sender_id):
    """Fetch the username associated with the sender ID."""
    url = f"{GRAPH_API_URL}/{sender_id}"
    params = {
        "fields": "username",
        "access_token": INSTAGRAM_ACCESS_TOKEN
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        return data.get("username")
    else:
        print(f"Failed to fetch username for sender_id {sender_id}. Error: {response.text}")
        return None



def resize_frame_with_aspect_ratio(frame, target_width=640):
    """
    Resize frame while maintaining aspect ratio
    """
    height, width = frame.shape[:2]
    aspect_ratio = width / height
    target_height = int(target_width / aspect_ratio)
    return cv2.resize(frame, (target_width, target_height))




@contextmanager
def session_scope():
    """
    Context manager for database sessions that handles commits and rollbacks automatically.
    Ensures proper resource cleanup even if exceptions occur.
    """
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("Database transaction failed", exc_info=True)
        raise
    finally:
        session.close()

def check_memory_usage() -> bool:
    """
    Monitor memory usage and return True if it exceeds the threshold.
    This helps prevent out-of-memory errors during processing.
    """
    process = psutil.Process()
    memory_info = process.memory_info()
    if memory_info.rss > MEMORY_THRESHOLD:
        logger.warning(f"Memory usage exceeding threshold: {memory_info.rss / (1024*1024):.2f} MB")
        return True
    return False

def process_single_frame(frame_data: Tuple[int, bytes, dict]) -> Optional[dict]:
    """
    Process a single frame with error handling and memory monitoring.
    Returns processed frame data or None if processing fails.
    """
    idx, frame, params = frame_data
    try:
        check_memory_usage()
        
        # Process frame for clothing detection
        processing_frame = resize_frame_with_aspect_ratio(frame, target_width=640)
        _, clothing_boxes = params['clothing_detector'].process_frame(processing_frame)
        
        # Calculate clothing area ratio
        frame_area = processing_frame.shape[0] * processing_frame.shape[1]
        clothing_area = sum(w * h for _, _, w, h in clothing_boxes)
        clothing_area_ratio = clothing_area / frame_area
        
        if clothing_area_ratio >= params['clothing_area_threshold']:
            success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if success:
                base64_image = f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"
                return {
                    'index': idx,
                    'base64_image': base64_image,
                    'clothing_boxes': clothing_boxes
                }
    except Exception as e:
        logger.error(f"Error processing frame {idx}", exc_info=True)
    
    return None

def process_frames_parallel(frames: List[bytes], params: dict) -> List[dict]:
    """
    Process multiple frames in parallel using a thread pool.
    Includes memory monitoring and error handling.
    """
    frame_data = [(idx, frame, params) for idx, frame in enumerate(frames)]
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(executor.map(process_single_frame, frame_data))
    
    return [r for r in results if r is not None]

def process_reels_with_clothing_detection(reel_url: str, instagram_username: str, sender_id: str) -> str:
    """
    Process Instagram reels by extracting meaningful frames and analyzing them directly with OpenAI Vision API.
    This simplified version removes the intermediate clothing detection step and focuses on smart frame sampling.
    """
    try:
        logger.info(f"Starting reel processing for user: {instagram_username}")
        
        # Download video with progress tracking
        response = requests.get(reel_url, stream=True, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to download reel: {response.status_code}")
            return "Sorry, I couldn't access the reel. Please try again."

        # Save to temporary file while tracking download progress
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
            temp_file_path = temp_file.name

        try:
            # Open video and extract basic information
            video = cv2.VideoCapture(temp_file_path)
            if not video.isOpened():
                logger.error("Failed to open video file")
                return "Sorry, I couldn't process the reel. Please try again."

            # Get video metadata
            total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = video.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps
            
            logger.info(f"Video stats - Duration: {duration:.2f}s, Frames: {total_frames}, FPS: {fps}")

            # Smart frame sampling strategy
            frames_to_analyze = []
            previous_frame_gray = None
            frame_count = 0
            min_frame_difference = 0.3  # Threshold for considering frames different enough
            max_frames = 8  # Maximum number of frames to analyze
            
            while frame_count < total_frames and len(frames_to_analyze) < max_frames:
                ret, frame = video.read()
                if not ret:
                    break

                # Sample frames based on video duration
                if duration <= 15:  # Short video
                    sample_interval = int(fps)  # Sample once per second
                else:
                    sample_interval = int(fps * 1.5)  # Sample every 1.5 seconds

                if frame_count % sample_interval == 0:
                    # Convert to grayscale for comparison
                    current_frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    
                    # Check if frame is different enough from previous frame
                    should_process = True
                    if previous_frame_gray is not None:
                        similarity = ssim(previous_frame_gray, current_frame_gray)
                        should_process = similarity < (1 - min_frame_difference)
                        logger.info(f"Frame {frame_count} similarity with previous: {similarity:.3f}")

                    if should_process:
                        # Enhance frame quality
                        enhanced_frame = frame.copy()
                        # Basic image enhancement
                        enhanced_frame = cv2.convertScaleAbs(enhanced_frame, alpha=1.1, beta=10)
                        
                        # Store frame information
                        success, buffer = cv2.imencode('.jpg', enhanced_frame)
                        if success:
                            base64_image = base64.b64encode(buffer).decode('utf-8')
                            frames_to_analyze.append({
                                'base64_image': base64_image,
                                'frame_number': frame_count,
                                'timestamp': frame_count / fps
                            })
                            previous_frame_gray = current_frame_gray
                
                frame_count += 1

            logger.info(f"Selected {len(frames_to_analyze)} frames for analysis")

            # Process frames and store results
            all_responses = []
            
            # Database operations
            with session_scope() as session:
                # Handle phone number record
                phone = session.query(PhoneNumber).filter_by(instagram_username=instagram_username).first()
                if not phone:
                    phone = PhoneNumber(instagram_username=instagram_username)
                    session.add(phone)
                    session.flush()

                # Store video content
                video_content = open(temp_file_path, 'rb').read()
                base64_video = f"data:video/mp4;base64,{base64.b64encode(video_content).decode('utf-8')}"
                
                outfit = Outfit(
                    phone_id=phone.id,
                    image_data=base64_video,
                    description="Reel content"
                )
                session.add(outfit)
                session.flush()

                # Process each selected frame
                send_graph_api_reply(sender_id, "🎯 Processing your fashion content! This might take a moment...")

                for idx, frame_data in enumerate(frames_to_analyze, 1):
                    try:
                        # Process frame with OpenAI Vision API
                        clothing_items = process_response(
                            base64_image=frame_data['base64_image'].split('data:image/jpeg;base64,')[1],
                            instagram_username=instagram_username,
                            video=True
                        )
                        
                        if hasattr(clothing_items, 'Purpose') and clothing_items.Purpose == 1:
                            outfit_response = f"\nOutfit {idx} (at {frame_data['timestamp']:.1f}s):\n{clothing_items.Response}\nItems found:"
                            
                            for item in clothing_items.Article:
                                outfit_response += f"\n- {item.Item}"
                                new_item = Item(
                                    outfit_id=outfit.id,
                                    description=item.Item,
                                    search=item.Amazon_Search
                                )
                                session.add(new_item)
                            
                            all_responses.append(outfit_response)
                            
                    except Exception as e:
                        logger.error(f"Error processing frame {idx}", exc_info=True)
                        continue

            # Prepare response
            if all_responses:
                final_reply = f"I found {len(all_responses)} different outfits in your reel:"
                send_graph_api_reply(sender_id, final_reply)
                for response in all_responses:
                    send_graph_api_reply(sender_id, response)
                send_graph_api_reply(sender_id, "You can view all outfits on the Wha7 app. Download from the App Store!")
                return final_reply
            else:
                return "I couldn't identify any distinct outfits in the reel. Please try again with clearer footage."

        finally:
            # Clean up resources
            if 'video' in locals():
                video.release()
            if os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.error(f"Failed to delete temporary file: {temp_file_path}", exc_info=True)

    except Exception as e:
        logger.error("Error processing reel", exc_info=True)
        return "Sorry, I encountered an error while processing your reel. Please try again."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)