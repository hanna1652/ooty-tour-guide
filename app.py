import os
import time
from functools import wraps
from bson.objectid import ObjectId
from flask import Flask, flash, redirect, render_template, request, session, url_for
from pymongo import MongoClient
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'ooty_feeds_secret_key'  # Needed for flash messages & sessions

# Directory setup for uploaded images
UPLOAD_FOLDER = os.path.join('static', 'images')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------------------------------------------------
# MONGODB ATLAS CONFIGURATION
# ---------------------------------------------------------
# Replace <db_password> with your actual database user password
MONGO_URI = os.environ.get(
    'MONGO_URI',
    'mongodb+srv://hh7158798_db_user:OotyPass123@ooty-feeds.0grjfne.mongodb.net/?appName=Ooty-feeds',
)

client = MongoClient(MONGO_URI)
db = client['ooty_feeds_db']

# Collections
destinations_col = db['destinations']
resorts_col = db['resorts']
reviews_col = db['reviews']
messages_col = db['messages']
credentials_col = db['credentials']
contact_col = db['contact']


# ---------------------------------------------------------
# HELPER FUNCTIONS FOR MONGODB
# ---------------------------------------------------------
def get_contact_info():
    default_contact = {
        'whatsapp_number': '919942697002',
        'phone_numbers': '+91 99426 97002 or +91 84899 91619',
        'email': 'yourguide@ootyfeeds.com',
        'location': 'Ooty, The Nilgiris, Tamil Nadu',
        'full_address': (
            'Elk Hill Rd, behind Eye foundation, Nondimedu, Ooty, Tamil Nadu'
            ' 643001'
        ),
        'available_hours': 'Every day, 8 AM – 9 PM',
        'whatsapp_message': "Hi, I'm interested in planning a trip to Ooty.",
    }
    contact = contact_col.find_one()
    if not contact:
        contact_col.insert_one(default_contact)
        return default_contact
    return contact


def save_contact_info(contact_data):
    contact_col.delete_many({})  # Ensure single document configuration
    contact_col.insert_one(contact_data)


def get_admin_credentials():
    default_creds = {'username': 'admin', 'password': 'password123'}
    creds = credentials_col.find_one()
    if not creds:
        credentials_col.insert_one(default_creds)
        return default_creds
    return creds


def save_admin_credentials(creds):
    credentials_col.delete_many({})  # Ensure single credentials document
    credentials_col.insert_one(creds)


# Decorator to protect admin routes
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('Please log in to access the admin area.', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)

    return decorated_function


# ---------------------------------------------------------
# PUBLIC MAIN ROUTE
# ---------------------------------------------------------
@app.route('/')
def home():
    destinations = list(destinations_col.find())
    hotels = list(resorts_col.find())
    reviews = list(reviews_col.find())
    contact_info = get_contact_info()
    return render_template(
        'index.html',
        destinations=destinations,
        hotels=hotels,
        reviews=reviews,
        contact_info=contact_info,
    )


# ---------------------------------------------------------
# PUBLIC FORM SUBMISSIONS
# ---------------------------------------------------------
@app.route('/contact', methods=['POST'])
def contact():
    name = request.form.get('name')
    phone = request.form.get('phone')
    email = request.form.get('email')
    message = request.form.get('message')

    clean_phone = ''.join(filter(str.isdigit, phone or ''))
    if len(clean_phone) == 10:
        clean_phone = '91' + clean_phone

    messages_col.insert_one({
        'name': name,
        'phone': clean_phone if clean_phone else phone,
        'email': email,
        'message': message,
        'date': time.strftime('%Y-%m-%d %H:%M:%S'),
    })

    flash(
        'Thank you for contacting us! We will get back to you shortly.',
        'success',
    )
    return redirect(url_for('home'))


@app.route('/add-review', methods=['POST'])
def add_review():
    author = request.form.get('author')
    rating = request.form.get('rating', '5')
    comment = request.form.get('comment')

    if author and comment:
        reviews_col.insert_one({
            'author': author,
            'rating': int(rating),
            'comment': comment,
            'date': time.strftime('%Y-%m-%d %H:%M:%S'),
        })
        flash('Thank you for your review!', 'success')
    else:
        flash('Please fill in all fields before submitting.', 'danger')

    return redirect(url_for('home'))


# ---------------------------------------------------------
# ADMIN AUTHENTICATION & SETTINGS
# ---------------------------------------------------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = (request.form.get('password') or '').strip()

        creds = get_admin_credentials()

        if username == creds.get('username') and password == creds.get(
            'password'
        ):
            session['admin_logged_in'] = True
            flash('Logged in successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('admin-login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin_login'))


@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    creds = get_admin_credentials()

    if request.method == 'POST':
        current_password = (
            request.form.get('current_password') or ''
        ).strip()
        new_username = (request.form.get('new_username') or '').strip()
        new_password = (request.form.get('new_password') or '').strip()

        if current_password != creds.get('password'):
            flash('Incorrect current password.', 'danger')
        elif not new_username or not new_password:
            flash('Username and Password fields cannot be empty.', 'danger')
        else:
            save_admin_credentials({
                'username': new_username,
                'password': new_password,
            })
            flash('Credentials updated successfully!', 'success')
            return redirect(url_for('admin_settings'))

    return render_template(
        'admin-settings.html', current_username=creds.get('username')
    )


@app.route('/admin/contact', methods=['GET', 'POST'])
@login_required
def admin_contact():
    contact_info = get_contact_info()

    if request.method == 'POST':
        raw_whatsapp = (
            (request.form.get('whatsapp_number') or '')
            .strip()
            .replace('+', '')
            .replace(' ', '')
        )

        updated_contact = {
            'whatsapp_number': raw_whatsapp,
            'phone_numbers': (request.form.get('phone_numbers') or '').strip(),
            'email': (request.form.get('email') or '').strip(),
            'location': (request.form.get('location') or '').strip(),
            'full_address': (request.form.get('full_address') or '').strip(),
            'available_hours': (
                request.form.get('available_hours') or ''
            ).strip(),
            'whatsapp_message': (
                request.form.get('whatsapp_message') or ''
            ).strip(),
        }

        save_contact_info(updated_contact)
        flash('Contact details updated successfully!', 'success')
        return redirect(url_for('admin_contact'))

    return render_template('admin-contact.html', contact_info=contact_info)


# ---------------------------------------------------------
# ADMIN DASHBOARD & MANAGEMENT ROUTES
# ---------------------------------------------------------
@app.route('/admin')
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    destinations_count = destinations_col.count_documents({})
    hotels_count = resorts_col.count_documents({})
    messages_count = messages_col.count_documents({})

    return render_template(
        'admin-dashboard.html',
        destinations_count=destinations_count,
        hotels_count=hotels_count,
        messages_count=messages_count,
    )


@app.route('/admin/destinations', methods=['GET', 'POST'])
@login_required
def admin_destinations():
    if request.method == 'POST':
        file = request.files.get('image')
        filename = 'Estate1main.jpeg'
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        new_destination = {
            'name': request.form.get('name'),
            'category': request.form.get('category'),
            'description': request.form.get('description'),
            'best_time': request.form.get('best_time', ''),
            'entry_fee': request.form.get('entry_fee', ''),
            'distance': request.form.get('distance', ''),
            'opening_hours': request.form.get('opening_hours', ''),
            'featured': True if request.form.get('featured') else False,
            'image_filename': filename,
            'badges': request.form.getlist('badges'),
        }

        destinations_col.insert_one(new_destination)
        flash('Destination added successfully!', 'success')
        return redirect(url_for('admin_destinations'))

    destinations = list(destinations_col.find())
    return render_template(
        'admin-destinations.html', destinations=destinations
    )


@app.route('/admin/destinations/delete/<string:dest_id>')
@login_required
def delete_destination(dest_id):
    try:
        destinations_col.delete_one({'_id': ObjectId(dest_id)})
    except Exception:
        destinations_col.delete_one({'id': int(dest_id)})
    flash('Destination deleted successfully!', 'success')
    return redirect(url_for('admin_destinations'))


@app.route('/admin/hotels', methods=['GET', 'POST'])
@login_required
def admin_hotels():
    if request.method == 'POST':
        file = request.files.get('image')
        filename = 'hotel5.jpeg'
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        new_hotel = {
            'name': request.form.get('name'),
            'category': request.form.get('category'),
            'description': request.form.get('description'),
            'rating': request.form.get('rating', '4.5'),
            'price_range': request.form.get('price_range', ''),
            'location': request.form.get('location', ''),
            'featured': True if request.form.get('featured') else False,
            'amenities': request.form.getlist('amenities'),
            'image_filename': filename,
        }

        resorts_col.insert_one(new_hotel)
        flash('Hotel/Resort added successfully!', 'success')
        return redirect(url_for('admin_hotels'))

    hotels = list(resorts_col.find())
    return render_template('admin-hotels.html', hotels=hotels)


@app.route('/admin/hotels/delete/<string:hotel_id>')
@login_required
def delete_hotel(hotel_id):
    try:
        resorts_col.delete_one({'_id': ObjectId(hotel_id)})
    except Exception:
        resorts_col.delete_one({'id': int(hotel_id)})
    flash('Hotel deleted successfully!', 'success')
    return redirect(url_for('admin_hotels'))


@app.route('/admin/messages')
@login_required
def admin_messages():
    messages = list(messages_col.find())
    return render_template('admin-messages.html', messages=messages)


@app.route('/admin/messages/delete/<string:msg_id>')
@login_required
def delete_message(msg_id):
    try:
        messages_col.delete_one({'_id': ObjectId(msg_id)})
    except Exception:
        messages_col.delete_one({'id': int(msg_id)})
    flash('Message deleted successfully!', 'success')
    return redirect(url_for('admin_messages'))


@app.route('/admin/reviews')
@login_required
def admin_reviews():
    reviews = list(reviews_col.find())
    return render_template('admin-reviews.html', reviews=reviews)


@app.route('/admin/reviews/delete/<string:review_id>')
@login_required
def delete_review(review_id):
    try:
        reviews_col.delete_one({'_id': ObjectId(review_id)})
    except Exception:
        reviews_col.delete_one({'id': int(review_id)})
    flash('Review deleted successfully!', 'success')
    return redirect(url_for('admin_reviews'))


# ---------------------------------------------------------
# GOOGLE SITE VERIFICATION ROUTE
# ---------------------------------------------------------
@app.route('/googleafecd3723199f7ac.html')
def google_verification():
    return "google-site-verification: googleafecd3723199f7ac.html"


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5000)