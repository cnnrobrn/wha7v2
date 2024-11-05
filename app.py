from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
from openai import OpenAI
import os
import json
import base64
import os
from dotenv import load_dotenv


app = Flask(__name__)



# Configure OpenAI API key
load_dotenv()
API_KEY=os.getenv('OPENAI_API_KEY')

client = OpenAI(
)

@app.route("/sms", methods=['POST'])
def sms_reply():
    # Extract incoming message information
    from_number = request.form.get('From')
    media_url = request.form.get('MediaUrl0')  # This will be the first image URL

    if media_url:
        print(from_number, media_url)

        # Download the image from Twilio
        image_data = requests.get(media_url).content
        
                # Convert image data to base64
        base64_image = base64.b64encode(image_data).decode('utf-8')

        # Prefix the base64 data for proper embedding
        base64_image_data = f"data:image/jpeg;base64,{base64_image}"

        # Analyze the image using OpenAI to determine clothing items
        clothing_items = analyze_image_with_openai(base64_image_data)

        # Search for the top Amazon links for each detected clothing item
        links = {}
        for item in clothing_items:
            links[item] = search_amazon(item)

        # Construct a response message with the links for each clothing item
        #resp = MessagingResponse()
        #for item, urls in links.items():
        #    message = f"Top links for {item}:\n" + "\n".join(urls)
        #    resp.message(message)

        #return str(resp)
        return(from_number, str(image_data))
    else:
        # Respond if no media is sent
        resp = MessagingResponse()
        resp.message("Please send a screenshot of a TikTok or Reel.")
        return str(resp)

def analyze_image_with_openai(image_data):
    # Example of using OpenAI to generate a response about clothing items
    # Assuming OpenAI GPT-4 can analyze text data about images (would need further development for visual analysis)
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Break down the following clothing items into specific Amazon search queries?",
                    },
                    {
                        "type": "image_data",
                        "image_data": {
                            "data": image_data
                        },
                    },
                ],
            }
        ],
        max_tokens=300,
    )

    print(response.choices[0]["message"]["content"])
    return response.choices[0]["message"]["content"]

def search_amazon(query):
    results= [f"https://www.amazon.com/s?k={query}&page={i}" for i in range(1, 4)]
    print(results)
    return results

if __name__ == "__main__":
    app.run(debug=True)
