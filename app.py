from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
import openai
import os
import json

app = Flask(__name__)

# Configure OpenAI API key
openai.api_key = os.environ.get('OPENAI_API_KEY')

@app.route("/sms", methods=['POST'])
def sms_reply():
    # Extract incoming message information
    from_number = request.form.get('From')
    media_url = request.form.get('MediaUrl0')  # This will be the first image URL

    if media_url:
        print(from_number, media_url)

        # Download the image from Twilio
        image_data = requests.get(media_url).content

        # Analyze the image using OpenAI to determine clothing items
        clothing_items = analyze_image_with_openai(image_data)

        # Search for the top Amazon links for each detected clothing item
        #links = {}
        #for item in clothing_items:
        #    links[item] = search_amazon(item)

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
    response = openai.Completion.create(
        engine="gpt-4o-latest",
        prompt="I'd like to break down the articles of clothing in this image into amazon queries with extreme levels of specificity so that the same product can be found through amazon. Here is the image data: [image bytes here]",
        max_tokens=200,
        n=1,
        stop=None,
        temperature=0.7
    )
    
    # Parse the structured response from OpenAI
    structured_response = response.choices[0].text.strip()
    
    # Example structured response parsing (this will depend on the actual response format)
    # Assuming the response is a JSON string
    response_data = json.loads(structured_response)
    
    clothing_items = []
    for item in response_data.get("items", []):
        clothing_items.append(item["query"])
    
    return clothing_items

def search_amazon(query):
    # Placeholder function to search Amazon and return top 3 links
    # Ideally, this would call the Amazon Product Advertising API or use some scraping method.
    return [f"https://www.amazon.com/s?k={query}&page={i}" for i in range(1, 4)]

if __name__ == "__main__":
    app.run(debug=True)
