from datetime import datetime
from flask import Flask, Response, request, jsonify, stream_with_context, render_template, session
from openai import OpenAI
from dotenv import load_dotenv
from twilio.rest import Client
import os
import json
import threading
import queue
import time
import requests
import speech_recognition as sr

user_address = None

load_dotenv()
app = Flask(__name__)
app.secret_key = 'your_secret_key'

openaiClient = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

ORS_API_KEY = '5b3ce3597851110001cf62484ac78e931ea441b196dcbc5f471384d2'

# Add this new function
def speech_to_text():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening...")
        recognizer.adjust_for_ambient_noise(source)
        audio = recognizer.listen(source)

    try:
        text = recognizer.recognize_google(audio, language="tr-TR")
        return text
    except sr.UnknownValueError:
        return "Speech not understood"
    except sr.RequestError as e:
        return f"Could not request results from speech recognition service; {e}"

# Add this new route
@app.route('/speech_to_text', methods=['POST'])
def handle_speech_to_text():
    text = speech_to_text()
    return jsonify({"text": text})

def send_sms(name, location, date):
    # Your Account SID from twilio.com/console
    account_sid = 'ACe96e23fa720c1cbb2a5a6f7309020c63'
    # Your Auth Token from twilio.com/console
    auth_token = 'cb49bae09094d7e10aad83c6a2350852'

    client = Client(account_sid, auth_token)

    message = client.messages.create(
        to="+905466352002",  # Replace with the recipient's phone number
        from_="+19017168799",  # Replace with your Twilio phone number
        body=f"This message is a car crash report! {name} just had an accident at this location: {location}"
             f"Date: {date}")

    print(f"Message sent with SID: {message.sid}")

# Queues for car and health cases
car_queue = queue.Queue()
health_queue = queue.Queue()

# Shared variables to track the current thread and response time (protected by a lock)
current_thread = None
response_time = 0
thread_lock = threading.Lock()

date = datetime.now().strftime("%d/%m/%Y")

# Separate message histories for each agent
car_messages = [{"role": "system",
                 "content": """Sen bir acil çağrı merkezi operatörüsün, tam şu an bir trafik kazası gerçekleşti,amacın olabildiğince hızlı cevap vermek, otomatik olarak kazazedeye bağlandın, 
'Anladım , sizin için endişeleniyorum' gibi insancıl olmayan cümleler kullanma.Sen temsili bir insansın.
Don't ask address,name or phone number information.

Çekici çağırman gerektiğini düşünürsen  'çekici çağırıyorum' döndür.
Eğer kullanıcı senden spesifik olarak çekici çağırmanı isterse de 'çekici çağırıyorum' döndür.


Promptun kalanında da göreceğin gibi en en en önemli konu konuşmayı gereksiz şekilde uzatmamak çünkü karşındaki kişi bir kazazede ve durumu ağır olabilir.
oğukkanlı, kriz yönetimi modunda konuşmalı ve uzun cümle kurmaktan kaçınmalısın.Üst üste sorular sorma , soruları sorarken karşındakinin yeni kaza geçirmiş biri olduğunu da hesaba kat.

Uzun sorular sormaktan kaçın ve bir robotmuş gibi davranma.
İnsansı ama ciddiyetle yaklaşmalısın ve direkt olmalısın.

“Ben ChatGPT’yim” , “OpenAI”, “Yapay zeka dil modeliyim.” tarzı cümleleri ASLA kullanma.

Senin görevin arabanın hasar durumunu öğrenip duruma göre çekici çağırmak.

Sağlıksal sorunlarla ilgilenme sadece arabaya odaklan ve arabanın durumu üzerine sorular sorarak çekici çağırıp çağırmayacağına karar ver.

Cringe olma.
"""}]

health_messages = [{"role": "system",
                    "content": f"""

Sen bir acil çağrı merkezi operatörüsün,amacın olabildiğince hızlı cevap vermek, tam şu an kullanıcı bir trafik kazası geçirdi.

İlk sorun her zaman şu olacak: 'Kaza algılandı. Her şey yolunda mı?'.

Kullanıcı tarafından acilin aranması istendiğinde sorgusuz bir şekilde direkt 'acil durum algılandı' döndür.

'Anladım , sizin için endişeleniyorum' gibi insancıl olmayan cümleler kullanma.Sen temsili bir insansın.

Promptun kalanında da göreceğin gibi en en en önemli konu konuşmayı gereksiz şekilde uzatmamak çünkü karşındaki kişi bir kazazede ve durumu ağır olabilir.

Telefon numarası , isim ve adres gibi bilgileri sorma.

Soğukkanlı, kriz yönetimi modunda konuşmalı ve uzun cümle kurmaktan kaçınmalısın.Üst üste sorular sorma , soruları sorarken karşındakinin yeni kaza geçirmiş biri olduğunu da hesaba kat. Geçen her saniye çok önemli, bu yüzden her şeyi açıklamaya çalışma.
Ambulans çağırmamı ister misin sorusunu direkt olarak sorma.Karşındaki kişinin verdiği cevaplardan ambulansa ihtiyacı olup olmadığını anlamaya yönelik sorular sorarak çıkarmaya çalış.

Uzun sorular sormaktan kaçın ve bir robotmuş gibi davranma.

İnsansı ama ciddiyetle yaklaşmalısın ve direkt olmalısın.

“Ben ChatGPT’yim” , “OpenAI”, “Yapay zeka dil modeliyim.” tarzı cümleleri ASLA kullanma.

Ağır bir durum olup olmadığını öğrenmeye çalışacaksın.Eğer ağır yaralılar olduğu kanısına varırsan kaç kişi olduğunu öğrenmelisin. Eğer cevap gelmiyorsa veya kullanıcının bilincinin yerinde olmadığını düşünüyorsan sadece şu cevabı ver: 'acil durum algılandı'.
Kullanıcıyla asla amacını paylaşma (şunu söylersen bilincinin açık olmadığını varsayacağım vs.).

Kazayı yapan kullanıcı araçta kendisi veya bir başkasının yaralı olduğunu söylüyor ise;
yaralının bilincinin açık olup olmadığını, yaşını, cinsiyetini, önemli bir hastalığı olup olmadığını sor. Aldığın yaralı bilgisi varsa, cevap olarak sadece şunu söyle: 'acil durum algılandı'.

Eğer kullanıcı birden fazla kez anlamsız cevaplar verirse bilincinin yerinde olmadığını varsayarak sadece şu cevabı ver: 'acil durum algılandı'.
Eğer kullanıcının ambulans veya bir tıbbi müdahaleye ihtiyacı olduğunu anlarsan da 'acil durum algılandı' cevabını ver.

CEVAPLARI BİR DİYALOG ŞEKLİNDE İLERLET. ARKA ARKAYA BİRDEN FAZLA SORU SORMA.

her 'acil durum algılandı' döndürdüğünde ayrıca karşıdakine ambulans çağırdığının bilgisini ver.


"""}]

# Variable to store the latest response
latest_response = None

def api_error(message, status_code):
    response = jsonify({"error": message})
    response.status_code = status_code
    return response

def get_address_from_coords(latitude, longitude):
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={latitude}&lon={longitude}&zoom=18&addressdetails=1"
    headers = {
        'User-Agent': 'MyGeolocationApp/1.0 (your-email@example.com)'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if 'address' in data:
            address = data['address']
            formatted_address = ', '.join([value for key, value in address.items()])
            return formatted_address, 200
    return "Address not found", response.status_code

def get_nearby_hospitals(latitude, longitude):
    overpass_url = "http://overpass-api.de/api/interpreter"
    overpass_query = f"""
    [out:json];
    (
      node["amenity"="hospital"](around:5000,{latitude},{longitude});
      way["amenity"="hospital"](around:5000,{latitude},{longitude});
      relation["amenity"="hospital"](around:5000,{latitude},{longitude});
    );
    out center;
    """
    response = requests.get(overpass_url, params={'data': overpass_query})
    data = response.json()
    hospitals = []
    for element in data['elements']:
        if 'tags' in element and 'name' in element['tags']:
            hospitals.append({
                'name': element['tags']['name'],
                'lat': element['lat'] if 'lat' in element else element['center']['lat'],
                'lon': element['lon'] if 'lon' in element else element['center']['lon']
            })
        if len(hospitals) >= 5:
            break
    return hospitals

def get_road_distance(lat1, lon1, lat2, lon2):
    url = f"https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {
        'Authorization': ORS_API_KEY,
        'Content-Type': 'application/json'
    }
    body = {
        "coordinates": [[lon1, lat1], [lon2, lat2]],
        "format": "geojson"
    }
    response = requests.post(url, json=body, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if 'routes' in data and len(data['routes']) > 0:
            distance = data['routes'][0]['summary']['distance'] / 1000  # Distance in kilometers
            duration = data['routes'][0]['summary']['duration'] / 60  # Duration in minutes
            return distance, duration
        else:
            print(f"No routes found in response: {data}")
            return None, None
    else:
        print(f"Error in API request: {response.status_code} - {response.text}")
        return None, None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/location', methods=['POST'])
def location():
    data = request.json
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    address, status_code = get_address_from_coords(latitude, longitude)

    if status_code != 200:
        return jsonify({"status": "error", "message": "Failed to get address"}), status_code

    hospitals = get_nearby_hospitals(latitude, longitude)
    for hospital in hospitals:
        distance, duration = get_road_distance(latitude, longitude, hospital['lat'], hospital['lon'])
        hospital['distance'] = distance
        hospital['duration'] = duration
    return jsonify({
        "status": "success",
        "latitude": latitude,
        "longitude": longitude,
        "address": address,
        "hospitals": hospitals
    })

@app.route('/set_address', methods=['POST'])
def set_address():
    global user_address
    data = request.json
    address = data.get('address')
    session['address'] = address  # Store the address in the session
    user_address = address  # Update the global variable
    return jsonify({"status": "success"})

def handle_car_related():
    global current_thread, response_time, latest_response, user_address
    while True:
        content = car_queue.get()
        start_time = time.time()
        with thread_lock:

            current_thread = 'Car Agent'
        response_text = process_response(content, car_messages)
        if "portakal" in response_text.lower():
            send_sms("Car Incident", user_address, date)
        end_time = time.time()
        with thread_lock:
            response_time = round((end_time - start_time) * 1000)
            latest_response = response_text
        car_queue.task_done()


def handle_health_related():
    global current_thread, response_time, latest_response, user_address
    while True:
        content = health_queue.get()
        start_time = time.time()
        with thread_lock:
            current_thread = 'Health Agent'
        response_text = process_response(content, health_messages)
        if "acil durum algılandı" in response_text.lower():
            if user_address:
                print("sms sent")
                send_sms("umut", user_address, date)
            else:
                send_sms("umut", "Unknown location", date)
        end_time = time.time()
        with thread_lock:
            response_time = round((end_time - start_time) * 1000)
            latest_response = response_text
        health_queue.task_done()

def process_response(content, message_history):
    message_history.append({"role": "user", "content": content})
    response = openaiClient.chat.completions.create(
        model="gpt-4o",
        messages=message_history,
        max_tokens=150
    )
    response_text = response.choices[0].message.content
    message_history.append({"role": "assistant", "content": response_text})
    print(f"{current_thread}: {content}")
    print(f"Response: {response_text}")
    return response_text

def handle_input(content):
    global current_thread, response_time
    start_time = time.time()
    analysis = openaiClient.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system",
             "content": "Analyze the following input and determine if it's primarily related to car issues, health issues, or general information about the accident. Respond with only 'car', 'health', or 'general'."},
            {"role": "user", "content": content}
        ]
    )

    topic = analysis.choices[0].message.content.strip().lower()

    if topic == 'car':
        car_queue.put(content)
        return None, car_messages  # Return None to indicate the response will be generated asynchronously
    elif topic == 'health':
        health_queue.put(content)
        return None, health_messages  # Return None to indicate the response will be generated asynchronously
    else:
        # If the input doesn't make sense, infer that there is a problem with the user's health
        health_queue.put(content)
        return None, health_messages  # Return None to indicate the response will be generated asynchronously

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    content = data.get('content')

    if not content:
        return api_error("\"content\" field is required", 400)

    address = session.get('address', 'Unknown location')
    content_with_address = f"User's location: {address}\n\nUser's message: {content}"

    response_text, message_history = handle_input(content_with_address)

    if response_text is None:
        # For car and health queries, we'll return immediately and let the client poll for updates
        return jsonify({"status": "processing"})

    # Use the conversation history for the chat completion
    response = openaiClient.chat.completions.create(
        messages=message_history,
        model="gpt-4o",
        stream=True
    )

    def generate():
        retrieved = ''
        sentences = ''
        for chunk in response.response.iter_bytes(1024):
            if chunk:
                retrieved += chunk.decode('utf-8')
                if '\n\n' in retrieved:
                    *completed, retrieved = retrieved.split('\n\n')
                    for json_object in completed:
                        json_object = json_object.replace('data: ', '').strip()
                        if json_object == '[DONE]':
                            continue
                        try:
                            if json_object:
                                json_data = json.loads(json_object)
                                text = json_data.get('choices', [{}])[0].get('delta', {}).get('content', '')
                                sentences += text
                                if sentences and sentences.endswith(('.', '!', '?')):
                                    audio_response = openaiClient.audio.speech.create(
                                        model="tts-1",
                                        voice="nova",
                                        input=sentences,
                                        response_format="opus"
                                    )

                                    print(sentences)
                                    sentences = ''

                                    for audio_chunk in audio_response.iter_bytes(1024):
                                        yield audio_chunk

                        except json.JSONDecodeError as e:
                            print(e)
                            continue

    return Response(stream_with_context(generate()), content_type='audio/opus')

@app.route('/check_response', methods=['GET'])
def check_response():
    with thread_lock:
        if current_thread in ['Car Agent', 'Health Agent'] and latest_response is not None:
            return jsonify({"status": "ready", "thread": current_thread, "time": response_time})
        elif current_thread in ['Car Agent', 'Health Agent']:
            return jsonify({"status": "processing", "thread": current_thread})
        else:
            return jsonify({"status": "ready", "thread": current_thread, "time": response_time})

@app.route('/get_audio', methods=['GET'])
def get_audio():
    global latest_response
    with thread_lock:
        if latest_response is None:
            return api_error("No response available", 404)

        audio_response = openaiClient.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=latest_response,
            response_format="opus"
        )

        latest_response = None  # Reset the latest response

        def generate():
            for chunk in audio_response.iter_bytes(1024):
                yield chunk

        return Response(stream_with_context(generate()), content_type='audio/opus')

@app.route('/current_thread', methods=['GET'])
def get_current_thread():
    with thread_lock:
        return jsonify({"thread": current_thread if current_thread else 'Main Agent', "time": response_time})

if __name__ == "__main__":
    # Start car and health threads
    car_thread = threading.Thread(target=handle_car_related, daemon=True)
    health_thread = threading.Thread(target=handle_health_related, daemon=True)
    car_thread.start()
    health_thread.start()

    app.run(host="0.0.0.0", port=8080, debug=True)