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



prompt = """You are the best clothes finder in the world. When people share photos of outfits with you, you identify each individual item in the outfit. For each item, you provide:

- **Item**: The name of the clothing item.
- **Amazon_Search**: A detailed search query string that can be used on Amazon to find that exact item.


In your Amazon_search details, include key details such as gender, color, shape, cut, material, pattern, and branding. You add so much detail that your searches result in the exact items that are in the images that were shared with you. Your outputs should follow this format:

```
Item: [Item Name]
Amazon_Search: [Search Query String]
```

**Examples:**

```
Item: Black Fleece Jacket
Amazon_Search: men's black fleece jacket zip-up high collar sherpa relaxed fit outdoor casual

Item: White T-Shirt
Amazon_Search: basic classic white t-shirt regular fit crew neck soft fabric layers well under jacket
```

**Other**
```
No Amazon URL data
No pricing data
Nothing outside of the specific format
```

"""

client = OpenAI()

@app.route("/sms", methods=['POST'])
def sms_reply():
    # Extract incoming message information
    from_number = request.form.get('From')
    media_url = request.form.get('MediaUrl0')  # This will be the first image URL


    if media_url:
        print(f"TWILIO_ACCOUNT_SID: {TWILIO_ACCOUNT_SID}")
        print(f"TWILIO_AUTH_TOKEN: {TWILIO_AUTH_TOKEN}")
        print(f"API_KEY: {API_KEY}")
        print(f"EBAY_AFFILIATE_ID: {EBAY_AFFILIATE_ID}")
        print(f"EBAY_APP_ID: {EBAY_APP_ID}")
        print(f"EBAY_DEV_ID: {EBAY_DEV_ID}")
        print(f"EBAY_CERT_ID: {EBAY_CERT_ID}")

        
        response = requests.get(media_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))

# Check the response to ensure it was successful
        print("Response status code:")
        print(response.status_code)
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
            ebay_access_token = ebay_oauth_flow()
            # Search for the top ebay links for each detected clothing item
            
            
            
            for item in clothing_items.Article:
                links[item.Item] = search_ebay(item.Amazon_Search,ebay_access_token)
                    
            print(links)
            

            # Construct a response message with the links for each clothing item
            resp = MessagingResponse()
            for item, urls in links.items():
                message = f"Top links for {item}:\n" 
                resp.message(message)
                for url in urls:
                    resp.message(url)
                #time.sleep(3)
                
            #return str(resp)
            return str(resp)
        else:
            return "Error: Unable to fetch the image."
    else:
        # Respond if no media is sent
        resp = MessagingResponse()
        resp.message("Please send a screenshot of a TikTok or Reel.")
        return str(resp)

def analyze_image_with_openai(base64_image):
    # Example of using OpenAI to generate a response about clothing items
    # Assuming OpenAI GPT-4 can analyze text data about images (would need further development for visual analysis)
    #print(base64_image)
    response = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
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
        endpoint = f"{EBAY_ENDPOINT}{url_query}&limit=3"
        response = requests.get(
            endpoint,
            headers=headers
        )
        response.raise_for_status()  # Raise an HTTPError for bad responses
        response_data = response.json()
        items = response_data.get("itemSummaries", [])
        links = [item.get("itemWebUrl") for item in items]
        return links
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        return ["HTTP error occurred"]
    except Exception as err:
        print(f"Other error occurred: {err}")
        return ["An error occurred"]

if __name__ == "__main__":
    app.run(debug=True)
