import os
import logging
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import config
from pymongo import MongoClient
from datetime import datetime, timedelta
import urllib.parse  # For URL encoding MongoDB password
from upload import upload_file, upload_to_cloud_storage  # Import the upload_file function from upload.py
import hashlib
from flask_caching import Cache
from bson import ObjectId
from google.cloud import storage


# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)

# Set up logging configuration
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("pymongo")
logger.setLevel(logging.CRITICAL)

# Set session timeout
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=5)

# MongoDB connection setup
db_password = urllib.parse.quote("your-db-password")  # URL encode the password
uri = f"mongodb+srv://saisrinivas300:{db_password}@llmcluster.tudpm.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(uri)  # MongoDB client
db = client['llmdb']  # Database name
collection = db['llmcluster']  # Collection name
collection2 = db["llmusers"]

# Cache configuration for file uploads
cache_config = {
    "CACHE_TYPE": "SimpleCache",  # Use SimpleCache for local development
    "CACHE_DEFAULT_TIMEOUT": 300,  # Cache timeout in seconds
}
app.config.from_mapping(cache_config)  # Apply the cache configuration
cache = Cache(app)


def check_mongo_connection():
    """Checks the MongoDB connection."""
    try:
        client.admin.command('ping')
        logger.info("MongoDB connection is successful")
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        return jsonify({'error': 'MongoDB connection failed'}), 500

@app.route('/')
def index():
    result = check_mongo_connection()
    if result:
        return result
    return render_template('index.html')

@app.route('/admin')
def admin():
    if 'user' not in session or session['user'] != "admin":
        logger.warning("User not in session or User is not admin")
        return redirect(url_for('login'))
    users = list(db.llmusers.find())  # Fetch users
    summariesdata = list(db.llmcluster.find())  # Fetch summaries
    logger.info(f"Fetched {len(users)} users and {len(summariesdata)} summaries from DB")
    return render_template('admin.html', users=users, summaries=summariesdata)

@app.route('/delete_user/<user_id>', methods=['POST'])
def delete_user(user_id):
    # if 'user' not in session or session['user'] != "admin":
    #     return redirect(url_for('login'))
    
    try:
        # Convert user_id to ObjectId
        user_id = ObjectId(user_id)
    except Exception as e:
        logger.error(f"Error converting user_id to ObjectId: {e}")
        return redirect(url_for('admin'))
    
    # Delete the user from the database
    result = db.llmusers.delete_one({'_id': user_id})
    
    if result.deleted_count > 0:
        logger.info(f"User with ID {user_id} deleted from DB")
    else:
        logger.warning(f"No user found with ID {user_id}")
    
    return redirect(url_for('admin'))

@app.route('/update_user/<user_id>', methods=['GET', 'POST'])
def update_user(user_id):
    # if 'user' not in session or session['user'] != "admin":
    #     return redirect(url_for('login'))
    
    try:
        # Convert user_id to ObjectId
        user_id = ObjectId(user_id)
    except Exception as e:
        logger.error(f"Error converting user_id to ObjectId: {e}")
        return redirect(url_for('admin'))
    
    # Fetch the user details
    user = db.llmusers.find_one({'_id': user_id})  
    if not user:
        logger.warning(f"User with ID {user_id} not found")
        return redirect(url_for('admin'))
    
    if request.method == 'POST':
        # Get the updated user details from the form
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Hash the password (optional: use bcrypt for stronger hashing)
        hashed_password = hashlib.md5(password.encode('utf-8')).hexdigest()
        
        updated_data = {
            'username': username,
            'email': email,
            'password': hashed_password
        }
        
        # Update the user in the database
        result = db.llmusers.update_one({'_id': user_id}, {'$set': updated_data})
        
        if result.matched_count > 0:
            logger.info(f"User with ID {user_id} successfully updated")
        else:
            logger.warning(f"User update failed for user_id: {user_id}")
        
        return redirect(url_for('admin'))
    
    return render_template('update_user.html', user=user)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    # if 'user' not in session:
    #     logger.warning("User not in session")
    #     return redirect(url_for('login'))
    username = request.args.get('username')
    if request.method == 'POST':
        logger.info("File upload initiated")
        return upload_file(client, cache, username)
    user_records = list(db.llmcluster.find({"user": username}))
    logger.info(f"Fetched {len(user_records)} records for user: {username}")

    return render_template("upload.html", user_records=user_records , username=username)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Hash the password using MD5
        password = hashlib.md5(password.encode('utf-8')).hexdigest()

        user = collection2.find_one({"username": username}) 
        if user and user['password'] == password:
            session['user'] = username
            session.permanent = True
            logger.info(f"Session created for user: {username}")

            if username == "admin":
                return redirect(url_for("admin"))
            return redirect(url_for('upload', username=username))
        else:
            logger.warning('Username or password incorrect')
            return redirect(url_for('login'))
    
    return render_template("login.html")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        hashed_password = hashlib.md5(password.encode('utf-8')).hexdigest()

        if username == "admin":
            logger.warning("User trying admin username")
            return redirect(url_for('signup'))

        user_details = {
            "username": username,
            "email": email,
            "password": hashed_password
        }
        try:
            collection2.insert_one(user_details)
            logger.info(f"User {username} created")
        except Exception as e:
            logger.error(f"Error inserting user into MongoDB: {e}")
            return redirect(url_for('signup'))
        return redirect(url_for('login'))
    
    return render_template("signup.html")

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    logger.info("User logged out")
    return render_template('index.html')

if __name__ == "__main__":
    logger.info("Starting Flask application...")
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG_MODE)
