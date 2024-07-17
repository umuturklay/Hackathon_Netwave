from flask import Flask, request, render_template, jsonify
import requests

app = Flask(__name__)

ORS_API_KEY = '5b3ce3597851110001cf62484ac78e931ea441b196dcbc5f471384d2'

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


if __name__ == '__main__':
    app.run(debug=True)
