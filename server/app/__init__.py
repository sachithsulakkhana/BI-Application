from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
import hashlib
from flask_jwt_extended import JWTManager, create_access_token
import os
from dotenv import load_dotenv
import numpy as np
from bson import json_util

# Load environment variables
load_dotenv()

def create_app():
    app = Flask(__name__)
    # Use an environment variable for the JWT secret key
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET', 'mytoken')
    jwt = JWTManager(app)
    CORS(app)

    # Retrieve MongoDB URL from environment variables
    mongo_url = os.getenv('MONGO_URL')
    if not mongo_url:
        raise EnvironmentError("MONGO_URL not found in environment variables.")

    try:
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
        client.server_info()  # Attempt to connect and force a server call
        db = client.get_default_database()  # Get the default database
        app.logger.info("Successfully connected to MongoDB")
    except ServerSelectionTimeoutError as e:
        app.logger.error("Database connection failed.", exc_info=True)
        raise e

    # Function to predict sales using moving average
    def predict_sales(historical_data):
        sales = np.array([data['sales'] for data in historical_data])
        alpha = 0.3  # Smoothing factor; this can be adjusted to weight recent sales more or less heavily
        smoothed_sales = sales[0]  # Initialize with the first data point
        for sale in sales[1:]:
            smoothed_sales = alpha * sale + (1 - alpha) * smoothed_sales  # Apply exponential smoothing

        predicted_sales = [smoothed_sales] * 5  # Predict the next 5 months based on the smoothed value
        return predicted_sales

    @app.route('/test_db_connection')
    def test_db_connection():
        return jsonify(message="Successfully connected to the database."), 200

    @app.route('/login', methods=['POST'])
    def login():
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')  # No need to encode password
        if not email or not password:
            return jsonify({"error": "Missing email or password"}), 400

        user_collection = db['users']
        user = user_collection.find_one({"email": email, "password": password})  # Check if user exists with provided email and password
        if user:
            access_token = create_access_token(identity=str(user['_id']))
            return jsonify(access_token=access_token, name=user['name']), 200
        else:
            return jsonify({"error": "Invalid email or password"}), 401

    @app.route('/fetch_chart_data', methods=['GET'])
    def fetch_chart_data():
        country = request.args.get('country')
        product_id = request.args.get('product_id')
        products_collection = db['products']
        
        # Retrieve historical sales data
        historical_data = list(products_collection.find({"country": country, "product_id": product_id}))
        
        # Perform prediction for the next 5 months using moving average
        predicted_sales = predict_sales(historical_data)
        
        # Combine historical data with predictions
        combined_data = combine_data(historical_data, predicted_sales)
        
        # Convert combined_data to JSON using json_util
        json_data = json_util.dumps(combined_data)
        
        return json_data, 200, {'Content-Type': 'application/json'}

    def combine_data(historical_data, predicted_sales):
        # Combine historical data with predictions
        combined_data = []
        for data in historical_data:
            # Convert ObjectId to string
            data['_id'] = str(data['_id'])
            combined_data.append(data)

        # Add predictions to the combined data
        for idx, data in enumerate(combined_data):
            data['prediction'] = predicted_sales[idx] if idx < len(predicted_sales) else None

        return combined_data

    @app.route('/register', methods=['POST'])
    def register():
        data = request.get_json()
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        password = data.get('password')
        if not name or not email or not phone or not password:
            return jsonify({"error": "Missing fields"}), 400

        user_collection = db['users']
        if user_collection.find_one({"email": email}):
            return jsonify({"error": "Email already registered"}), 400

        user_id = user_collection.insert_one({
            "name": name,
            "email": email,
            "phone": phone,
            "password": password,  # Store the password as provided
            "role": "user",
            "status": "pending"
        }).inserted_id
        return jsonify({"message": "User registered successfully", "user_id": str(user_id)}), 201

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
