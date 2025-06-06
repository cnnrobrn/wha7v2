# Framework imports
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Third-party imports
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from pydantic import BaseModel
import requests
import json
import base64
import os
import urllib.parse
import psycopg2
from datetime import datetime, timezone
from dotenv import load_dotenv
import cv2
import numpy as np
from io import BytesIO
from PIL import Image
import requests
from skimage.metrics import structural_similarity as ssim
import tempfile
import os

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

prompt = """Identify all clothing and accessory items in an image with detailed characteristics, ensuring no item is missed.

For each identified item, provide:
- **Item**: Detailed item name with visible characteristics.
- **Amazon_Search**: Specific search string with essential details for exact matching.

Include details where applicable:
- Gender (men's, women's, etc.)
- Size and age group
- Color, pattern, material, and texture
- Design elements (fit, cut, closures, etc.)
- Brand information
- Occasion and style
- Accessory specifics (for jewelry, bags, shoes, watches)

# Output Format
Provide identified items and optimized Amazon search strings. 

# Examples
- **Item**: Men's Nike Running Jacket
  **Amazon_Search**: mens nike running jacket black full zip lightweight

- **Item**: Women's Tiffany Pendant
  **Amazon_Search**: womens tiffany pendant sterling silver chain classic design

# Notes
Ensure complete identification and description of each item’s characteristics."""

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
            max_tokens=5000,
        )
        return response.choices[0].message.parsed
    except Exception as e:
        print(f"Error analyzing image with OpenAI: {e}")
        return None
def process_response(base64_image, from_number, text, prompt_text=prompt, format=Outfits, instagram_username=None):
    if base64_image:
        base64_image_data = f"data:image/jpeg;base64,{base64_image}"
        clothing_items = analyze_image_with_openai(base64_image_data, text, prompt_text, format)
        if format == Outfits:
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
                        description=item.Amazon_Search, 
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
                    print("4. Processing messaging item")

                    # Extract sender ID
                    sender_id = messaging.get('sender', {}).get('id')
                    if sender_id:
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
                            send_graph_api_reply(sender_id,"🎬 Exciting reel spotted! Let's see what we've got...")

                            reply = process_reels(media_url, sender_username,sender_id)
                            print(f"11. Sending final reply for video: {reply}")

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
                                    print("10. Image processed successfully")
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

                                        print(f"11. Sending final reply: {reply}")
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
        print(f"Sending message to {user_id}: {message}")
        response = requests.post(url, headers=headers, json=data)
        response_json = response.json()
        print(f"Instagram API response: {response_json}")
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

def process_reels(reel_url, instagram_username, sender_id):
    try:
        response = requests.get(reel_url, stream=True, timeout=10)
        if response.status_code != 200:
            return "Sorry, I couldn't access the reel. Please try again."

        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
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
            send_graph_api_reply(sender_id,"🎯 Target acquired! Processing your awesome content 🔄")
            for idx, base64_image in enumerate(unique_frames):
                try:
                    clothing_items = process_response(
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
            send_graph_api_reply(sender_id,"⚡ Almost there! (Beta feature - might see some déjà vu content! 😉)")
            if all_responses:
                final_reply = f"I found {len(all_responses)} different outfits in your reel:"
                send_graph_api_reply(sender_id, final_reply)
                for item in all_responses:
                    send_graph_api_reply(sender_id,item)
                send_graph_api_reply(sender_id, "You can view all outfits on the Wha7 app. Download from the App Store!")
                return final_reply
            else:
                final_reply = "I couldn't identify any distinct outfits in the reel. Please try again with clearer footage."
                send_graph_api_reply(sender_id, final_reply)
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
