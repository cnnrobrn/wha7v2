# Framework imports
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from datetime import datetime

# Third-party imports
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from pydantic import BaseModel
import requests
import json
import base64
import os
import urllib.parse
from datetime import datetime, timezone
from dotenv import load_dotenv
import cv2
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim
import tempfile
import asyncio
import aiohttp

# wha7_models imports (updated for async)

# Create FastAPI app
app = FastAPI()

# Add CORS middleware
app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

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
WEBHOOK_VERIFY_TOKEN = os.getenv('WEBHOOK_VERIFY_TOKEN')
GRAPH_API_URL = "https://graph.instagram.com/v12.0"

# SQLAlchemy setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Define your database models here (same as your wha7_models.py)
class PhoneNumber(Base):
    __tablename__ = "phone_numbers"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, index=True)
    instagram_username = Column(String, unique=True, index=True, nullable=True)
    is_activated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    outfits = relationship("Outfit", back_populates="phone")
    referral_codes = relationship("ReferralCode", back_populates="phone")

class Outfit(Base):
    __tablename__ = "outfits"
    id = Column(Integer, primary_key=True, index=True)
    phone_id = Column(Integer, ForeignKey("phone_numbers.id"))
    image_data = Column(String)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    phone = relationship("PhoneNumber", back_populates="outfits")
    items = relationship("Item", back_populates="outfit")

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True, index=True)
    outfit_id = Column(Integer, ForeignKey("outfits.id"))
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    outfit = relationship("Outfit", back_populates="items")
    links = relationship("Link", back_populates="item")

class Link(Base):
    __tablename__ = "links"
    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id"))
    photo_url = Column(String, nullable=True)
    url = Column(String)
    price = Column(String, nullable=True)
    title = Column(String, nullable=True)
    rating = Column(String, nullable=True)
    reviews_count = Column(String, nullable=True)
    merchant_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    item = relationship("Item", back_populates="links")

class ReferralCode(Base):
    __tablename__ = "referral_codes"
    id = Column(Integer, primary_key=True, index=True)
    phone_id = Column(Integer, ForeignKey("phone_numbers.id"))
    code = Column(String, unique=True, index=True)
    used_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    phone = relationship("PhoneNumber", back_populates="referral_codes")

class Referral(Base):
    __tablename__ = "referrals"
    id = Column(Integer, primary_key=True, index=True)
    referrer_id = Column(Integer, ForeignKey("phone_numbers.id"))
    referred_id = Column(Integer, ForeignKey("phone_numbers.id"))
    code_used = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)


# Your pydantic models remain the same
class Clothing(BaseModel):
    Item: str
    Amazon_Search: str

class Recommendations(BaseModel):
    Response: str
    Recommendations: list[Clothing]

class Outfits(BaseModel):
    Outfits: str
    Response: str
    Purpose: int
    Article: list[Clothing]

EBAY_ENDPOINT = "https://api.ebay.com/buy/browse/v1/item_summary/search?q="

prompt = """You are the world's premier fashion and accessories finder, specializing in exact item identification. When analyzing outfit photos, you identify every single component with precise, searchable detail.

For each identified item, provide:

Item: Exhaustively detailed item name including all visible characteristics
Amazon_Search: Ultra-specific search string optimized for exact item matching

ALL ARTICLES OF CLOTHING IN THE IMAGE MUST BE IDENTIFIED. THIS INCLUDES OTHERS IN THE PHOTO.

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


@app.post("/sms", response_class=HTMLResponse)  # Changed to HTMLResponse for Twilio
async def sms_reply(request: Request):
    """
    Handles incoming SMS messages with images, processes them, and sends a reply.
    """
    form = await request.form()
    from_number = form.get('From')
    media_url = form.get('MediaUrl0')
    text = form.get('Body')

    if media_url:
        try:
            response = requests.get(media_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
            response.raise_for_status()  # Raise an exception for bad status codes
            image_content = response.content
            base64_image = base64.b64encode(image_content).decode('utf-8')
            clothing_items = await process_response(base64_image, from_number, text)

            # Construct response message
            resp = MessagingResponse()
            if clothing_items.Purpose == 1:
                resp.message(f"{clothing_items.Response} You can view the outfit on the Wha7 app. Join the waitlist at https://www.wha7.com/f/5f804b34-9f3a-4bd6-a9e5-bf21e2a9018d")
            elif clothing_items.Purpose == 2:
                resp.message(f"{clothing_items.Response}")
            elif clothing_items.Purpose == 3:
                resp.message("I'm sorry, I'm not sure how to respond to that. Can you retry?")
            return str(resp)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching image: {e}")
            return HTTPException(status_code=500, detail="Error fetching image")

    else:
        resp = MessagingResponse()
        resp.message("Please send a screenshot of a TikTok or Reel. You can access outfits you've already shared on our app or after signing up via https://www.wha7.com/f/5f804b34-9f3a-4bd6-a9e5-bf21e2a9018d")
        return str(resp)
        
@app.post("/ios/consultant")
async def ios_consultant(request: Request):
    """
    Handles requests from iOS app for fashion recommendations.
    """
    data = await request.json()
    image_content = data.get('image_content')
    text = data.get('text')
    from_number = format_phone_number(data.get('from_number'))
    clothing_items = await process_response(
        image_content, from_number, text, prompt_text=recommendation_prompt, format=Recommendations
    )
    return JSONResponse(
        content={
            "response": clothing_items.Response,
            "recommendations": [
                {
                    "Item": article.Item,
                    "Amazon_Search": article.Amazon_Search,
                    "Recommendation_ID": await get_recommendation_id(article.Item),
                }
                for article in (clothing_items.Recommendations or [])
            ],
        }
    )


@app.post("/ios")
async def ios_image(request: Request, background_tasks: BackgroundTasks):
    """
    Handles image uploads from iOS app and processes them in the background.
    """
    data = await request.json()
    image_content = data.get('image_content')
    from_number = format_phone_number(data.get('from_number'))
    # Run database commit in the background
    background_tasks.add_task(process_response, image_content, from_number, text=None) 
    return JSONResponse(content={"status": "success"})

def format_phone_number(phone_number):
    phone_number = phone_number.strip().replace("-", "").replace("(", "").replace(")", "").replace(" ", "").replace("+1", "")
    if not phone_number.startswith("+1"):
        phone_number = "+1" + phone_number
    return phone_number

async def analyze_text_with_openai(text=None, true_prompt=prompt, format=Outfits):
    """
    Analyzes text using OpenAI and returns a structured response.
    """
    try:
        response = await client.beta.chat.completions.acreate(  # Use acreate for async
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at structured data extraction. You will be given a photo and should convert it into the given structure.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": true_prompt},
                        {"type": "text", "text": f"The user sent the following text: {text}"},
                    ],
                },
            ],
            response_format=format,
            max_tokens=5000,
        )
        return response.choices[0].message.parsed
    except Exception as e:
        print(f"Error analyzing text with OpenAI: {e}")
        return None
    
async def analyze_image_with_openai(base64_image=None, text=None, true_prompt=prompt, format=Outfits):
    """
    Analyzes an image using OpenAI and returns a structured response.
    """
    try:
        response = await client.beta.chat.completions.acreate(  # Use acreate for async
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at structured data extraction. You will be given a photo and should convert it into the given structure.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": true_prompt},
                        {"type": "text", "text": f"The user sent the following text: {text}"},
                        {
                            "type": "image_url",
                            "image_url": {"url": base64_image},
                        },
                    ],
                },
            ],
            response_format=format,
            max_tokens=5000,
        )
        return response.choices[0].message.parsed
    except Exception as e:
        print(f"Error analyzing image with OpenAI: {e}")
        return None

async def process_response(base64_image, from_number, text, prompt_text=prompt, format=Outfits, instagram_username=None):
    """
    Processes image or text data, analyzes it with OpenAI, and optionally saves to the database.
    """
    if base64_image:
        base64_image_data = f"data:image/jpeg;base64,{base64_image}"
        clothing_items = await analyze_image_with_openai(base64_image_data, text, prompt_text, format)
        if format == Outfits:
            await database_commit(clothing_items, from_number, base64_image_data, instagram_username)
    else:
        clothing_items = await analyze_text_with_openai(text=text, true_prompt=prompt_text, format=format)
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
async def database_commit(clothing_items, from_number, base64_image_data=None, instagram_username=None):
    """
    Saves the processed outfit and item information to the database asynchronously.
    """
    async with async_session_factory() as session:
        try:
            phone = None
            if instagram_username:
                phone = await session.execute(
                    select(PhoneNumber).where(PhoneNumber.instagram_username == instagram_username)
                )
                phone = phone.scalars().first()

            if not phone and from_number:
                phone = await session.execute(
                    select(PhoneNumber).where(PhoneNumber.phone_number == from_number)
                )
                phone = phone.scalars().first()

            if not phone:
                phone = PhoneNumber(
                    phone_number=from_number,
                    instagram_username=instagram_username
                )
                session.add(phone)
                await session.commit()
            else:
                if instagram_username and not phone.instagram_username:
                    phone.instagram_username = instagram_username
                    await session.commit()
                elif from_number and not phone.phone_number:
                    phone.phone_number = from_number
                    await session.commit()

            outfit = Outfit(phone_id=phone.id, image_data=base64_image_data, description="Outfit from image")
            session.add(outfit)
            await session.commit()

            if clothing_items.Article is not None:
                for item in clothing_items.Article:
                    new_item = Item(
                        outfit_id=outfit.id,
                        description=item.Item,
                        search=item.Amazon_Search,
                        processed_at=None
                    )
                    session.add(new_item)
                    await session.commit()
            else:
                print("No items found in clothing_items.Article")

        except Exception as e:
            print(f"Error committing to database: {e}")
            raise HTTPException(status_code=500, detail="Error saving data")


# --- Async versions of Instagram functions ---


async def get_unread_messages():
    """Fetch unread direct messages"""
    try:
        url = f"https://graph.facebook.com/v18.0/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/messages"
        params = {
            'access_token': INSTAGRAM_ACCESS_TOKEN,
            'fields': 'message,from,attachments'
        }
        response = requests.get(url, params=params)  # This remains synchronous for now
        return response.json().get('data', [])
    except Exception as e:
        print(f"Error fetching messages: {e}")
        return []


async def send_instagram_reply(user_id, message):
    """Send reply to Instagram user"""
    try:
        url = f"https://graph.facebook.com/v18.0/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/messages"
        data = {
            'recipient': {'id': user_id},
            'message': {'text': message},
            'access_token': INSTAGRAM_ACCESS_TOKEN
        }
        response = requests.post(url, json=data)  # This remains synchronous for now
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

    print(f"Received verification request - Mode: {mode}, Token: {token}, Challenge: {challenge}")

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
@app.post("/instagram_webhook")  # Changed to FastAPI decorator
async def handle_instagram_messages(request: Request):  # Added async def
    """Handle incoming Instagram messages webhook"""
    try:
        webhook_data = await request.json()  # Use await for async request parsing
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
                    print("4. Processing messaging item")

                    # Extract sender ID
                    sender_id = messaging.get('sender', {}).get('id')
                    if sender_id:
                        # Fetch the username using the sender ID
                        sender_username = get_username(sender_id)  # This function needs to be async
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
                        reply = await send_graph_api_reply(sender_id, "Please send a screenshot of a TikTok or Reel. You can access outfits you've already shared on our app or after signing up via https://www.wha7.com/f/5f804b34-9f3a-4bd6-a9e5-bf21e2a9018d")  # Use await here
                        print(f"Default message response: {reply}")
                        continue

                    # Process the first attachment
                    attachment = attachments[0]
                    media_type = attachment.get('type', '')
                    media_url = attachment.get('payload', {}).get('url')

                    if not media_url:
                        print("No media URL found in attachment")
                        continue

                    print(f"8. Processing media URL: {media_url}")
                    print(f"Media type: {media_type}")

                    try:
                        # Check if the media is a video/reel
                        if media_type in ['video', 'ig_reel']:
                            print("Processing video/reel content")
                            await send_graph_api_reply(sender_id, "Reel received. Processing now. Please wait...")  # Use await here
                            reply = await process_reels(media_url, sender_username, sender_id)  # Use await here
                            print(f"11. Sending final reply for video: {reply}")

                        else:
                            # Handle image processing as before
                            media_response = requests.get(media_url)  # This should ideally be async
                            print(f"9. Media fetch status: {media_response.status_code}")
                            await send_graph_api_reply(sender_id, "Post received. Processing now. Please wait...")  # Use await here

                            if media_response.status_code == 200:
                                image_content = media_response.content
                                base64_image = base64.b64encode(image_content).decode('utf-8')

                                try:
                                    clothing_items = await process_response(  # Use await here
                                        base64_image,
                                        None,
                                        "",
                                        instagram_username=sender_username
                                    )
                                    print("10. Image processed successfully")

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

                                        print(f"11. Sending final reply: {reply}")
                                        response = await send_graph_api_reply(sender_id, reply)  # Use await here
                                        print(f"12. Final response: {response}")
                                except Exception as e:
                                    print(f"Error in processing response: {e}")
                                    await send_graph_api_reply(sender_id, "Sorry, I had trouble processing your image. Please try again.")  # Use await here
                            else:
                                print(f"Media fetch failed with status {media_response.status_code}")
                                await send_graph_api_reply(sender_id, "Sorry, I couldn't access your image. Please try sending it again.")  # Use await here
                    except Exception as e:
                        print(f"Error processing media: {e}")
                        await send_graph_api_reply(sender_id, "Sorry, there was an error processing your media. Please try again.")  # Use await here

        return JSONResponse(content={'status': 'success'}, status_code=200)  # Changed to FastAPI response

    except Exception as e:
        print(f"Error in webhook handler: {str(e)}")
        return JSONResponse(content={'error': str(e)}, status_code=500)  # Changed to FastAPI response

async def send_graph_api_reply(user_id, message):
    """Send reply using Instagram Graph API asynchronously."""
    url = "https://graph.instagram.com/v12.0/me/messages"
    headers = {
        'Authorization': f'Bearer {INSTAGRAM_ACCESS_TOKEN}'
    }
    data = {
        'recipient': {'id': user_id},
        'message': {'text': message}
    }
    print(f"Sending message to {user_id}: {message}")
    async with aiohttp.ClientSession() as session:  # Use aiohttp for async request
        async with session.post(url, headers=headers, json=data) as response:
            response_json = await response.json()  # Asynchronously get JSON response
            print(f"Instagram API response: {response_json}")
            return response_json


async def get_username(sender_id):
    """Fetch the username associated with the sender ID asynchronously."""
    url = f"{GRAPH_API_URL}/{sender_id}"
    params = {
        "fields": "username",
        "access_token": INSTAGRAM_ACCESS_TOKEN
    }
    async with aiohttp.ClientSession() as session:  # Use aiohttp for async request
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()  # Asynchronously get JSON response
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

async def process_reels(reel_url, instagram_username, sender_id):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(reel_url, timeout=10) as response:
                if response.status != 200:
                    return "Sorry, I couldn't access the reel. Please try again."

                with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                    async for chunk in response.content.iter_chunked(8192):
                        if chunk:
                            temp_file.write(chunk)
                    temp_file_path = temp_file.name

        try:
            video = cv2.VideoCapture(temp_file_path)
            if not video.isOpened():
                return "Sorry, I couldn't process the reel. Please try again."

            fps = min(video.get(cv2.CAP_PROP_FPS), 30)
            total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
            max_frames_to_process = min(total_frames, 300)
            frame_interval = int(fps * 2)
            similarity_threshold = 0.80

            unique_frames = []
            previous_frame = None
            frame_count = 0
            max_unique_frames = 5

            while video.isOpened() and frame_count < max_frames_to_process and len(unique_frames) < max_unique_frames:
                ret, frame = video.read()
                if not ret:
                    break

                if frame_count % frame_interval == 0:
                    # Resize for comparison while maintaining aspect ratio
                    processing_frame = resize_frame_with_aspect_ratio(frame, target_width=640)
                    gray_frame = cv2.cvtColor(processing_frame, cv2.COLOR_BGR2GRAY)

                    is_unique = True
                    if previous_frame is not None:
                        if previous_frame.shape != gray_frame.shape:
                            gray_frame = cv2.resize(gray_frame, previous_frame.shape[::-1])
                        similarity = ssim(previous_frame, gray_frame)
                        is_unique = similarity < similarity_threshold

                    if is_unique:
                        # Store original frame (not the resized version) in base64
                        success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                        if success:
                            base64_image = base64.b64encode(buffer).decode('utf-8')
                            unique_frames.append(base64_image)
                            previous_frame = gray_frame

                frame_count += 1

            video.release()

            # Process frames with error handling for each
            all_responses = []
            for idx, base64_image in enumerate(unique_frames):
                try:
                    clothing_items = await process_response(
                        base64_image,
                        None,
                        "",
                        instagram_username=instagram_username
                    )

                    if hasattr(clothing_items, 'Purpose') and clothing_items.Purpose == 1:
                        outfit_response = f"\nOutfit {idx + 1}:\n{clothing_items.Response}\nItems found:"
                        for item in clothing_items.Article:
                            outfit_response += f"\n- {item.Item}"
                        all_responses.append(outfit_response)
                except Exception as e:
                    print(f"Error processing frame {idx}: {str(e)}")
                    continue

            # Clean up
            os.unlink(temp_file_path)

            if all_responses:
                final_reply = f"I found {len(all_responses)} different outfits in your reel:"
                await send_graph_api_reply(sender_id, final_reply)  # Add await here
                for item in all_responses:
                    await send_graph_api_reply(sender_id, item)  # Add await here
                await send_graph_api_reply(sender_id, "You can view all outfits on the Wha7 app. Download from the App Store!")  # Add await here
                return final_reply
            else:
                final_reply = "I couldn't identify any distinct outfits in the reel. Please try again with clearer footage."
                await send_graph_api_reply(sender_id, final_reply)  # Add await here
            return final_reply

        finally:
            if 'video' in locals():
                video.release()
            if os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass

    except Exception as e:
        print(f"Error processing reel: {str(e)}")
        return "Sorry, I encountered an error while processing your reel. Please try again."

    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)