import os
import time
from functools import wraps
from bson.objectid import ObjectId
from flask import Flask, Response, flash, redirect, render_template, request, session, url_for
from pymongo import MongoClient
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY')
if not app.secret_key:
    raise RuntimeError('FLASK_SECRET_KEY environment variable is required.')

# Directory setup for uploaded images
UPLOAD_FOLDER = os.path.join('static', 'images')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------------------------------------------------
# MONGODB ATLAS CONFIGURATION
# ---------------------------------------------------------
MONGO_URI = os.environ.get('MONGO_URI')
if not MONGO_URI:
    raise RuntimeError('MONGO_URI environment variable is required.')

client = MongoClient(MONGO_URI)
db = client['ooty_feeds_db']

# Collections
destinations_col = db['destinations']
resorts_col = db['resorts']
reviews_col = db['reviews']
messages_col = db['messages']
credentials_col = db['credentials']
contact_col = db['contact']
real_estate_col = db['real_estate']
transport_col = db['transportation']


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
    creds = credentials_col.find_one()
    if creds:
        return creds

    default_creds = {
        'username': os.environ.get('ADMIN_USERNAME'),
        'password': os.environ.get('ADMIN_PASSWORD'),
    }
    if not all(default_creds.values()):
        raise RuntimeError(
            'Set ADMIN_USERNAME and ADMIN_PASSWORD before the first admin login.'
        )
    credentials_col.insert_one(default_creds)
    return default_creds


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
    real_estate = list(real_estate_col.find())
    transportation = list(transport_col.find())
    return render_template(
        'index.html',
        destinations=destinations,
        hotels=hotels,
        reviews=reviews,
        contact_info=contact_info,
        real_estate=real_estate,
        transportation=transportation,
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
    real_estate_count = real_estate_col.count_documents({})
    transport_count = transport_col.count_documents({})

    return render_template(
        'admin-dashboard.html',
        destinations_count=destinations_count,
        hotels_count=hotels_count,
        messages_count=messages_count,
        real_estate_count=real_estate_count,
        transport_count=transport_count,
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



# ---------------------------------------------------------
# REAL ESTATE & TRANSPORTATION MANAGEMENT
# ---------------------------------------------------------
def save_listing_image(file):
    """Save an uploaded listing image using a unique, safe filename."""
    if not file or not file.filename:
        return ''
    filename = f"uploaded_{time.time_ns()}_{secure_filename(file.filename)}"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return filename


@app.route('/admin/real-estate', methods=['GET', 'POST'])
@login_required
def admin_real_estate():
    if request.method == 'POST':
        new_property = {
            'title': (request.form.get('title') or '').strip(),
            'listing_type': (request.form.get('listing_type') or '').strip(),
            'property_type': (request.form.get('property_type') or '').strip(),
            'price': (request.form.get('price') or '').strip(),
            'location': (request.form.get('location') or '').strip(),
            'description': (request.form.get('description') or '').strip(),
            'contact_no': (request.form.get('contact_no') or '').strip(),
            'image_filename': save_listing_image(request.files.get('image')),
        }
        real_estate_col.insert_one(new_property)
        flash('Property added successfully!', 'success')
        return redirect(url_for('admin_real_estate'))

    properties = list(real_estate_col.find())
    return render_template('admin-real-estate.html', properties=properties)


@app.route('/admin/real-estate/delete/<string:prop_id>')
@login_required
def delete_real_estate(prop_id):
    if ObjectId.is_valid(prop_id):
        real_estate_col.delete_one({'_id': ObjectId(prop_id)})
    elif prop_id.isdigit():
        real_estate_col.delete_one({'id': int(prop_id)})
    flash('Property deleted successfully!', 'success')
    return redirect(url_for('admin_real_estate'))


@app.route('/admin/transportation', methods=['GET', 'POST'])
@login_required
def admin_transportation():
    if request.method == 'POST':
        new_vehicle = {
            'vehicle_name': (request.form.get('vehicle_name') or '').strip(),
            'category': (request.form.get('category') or '').strip(),
            'fuel_type': (request.form.get('fuel_type') or '').strip(),
            'price_rate': (request.form.get('price_rate') or '').strip(),
            'contact_no': (request.form.get('contact_no') or '').strip(),
            'image_filename': save_listing_image(request.files.get('image')),
        }
        transport_col.insert_one(new_vehicle)
        flash('Vehicle added successfully!', 'success')
        return redirect(url_for('admin_transportation'))

    vehicles = list(transport_col.find())
    return render_template('admin-transportation.html', vehicles=vehicles)


@app.route('/admin/transportation/delete/<string:trans_id>')
@login_required
def delete_transportation(trans_id):
    if ObjectId.is_valid(trans_id):
        transport_col.delete_one({'_id': ObjectId(trans_id)})
    elif trans_id.isdigit():
        transport_col.delete_one({'id': int(trans_id)})
    flash('Vehicle deleted successfully!', 'success')
    return redirect(url_for('admin_transportation'))


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
# GOOGLE SITE VERIFICATION & ROBOTS ROUTE
# ---------------------------------------------------------
@app.route('/googleafecd3723199f7ac.html')
def google_verification():
    return "google-site-verification: googleafecd3723199f7ac.html"


@app.route('/robots.txt')
def robots():
    content = "User-agent: *\nAllow: /\n"
    return Response(content, mimetype='text/plain')


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5000)