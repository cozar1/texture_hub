import os
import uuid

from flask import Flask, render_template, request, redirect, send_file, session, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename
from sqlalchemy import func, delete
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash

## ========== Config ==========
app = Flask(__name__)
app.secret_key = 'replace-this-with-a-secure-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

## ========== Directories ==========
STATIC_IMAGES_DIR = os.path.join(app.root_path, 'static', 'images')
DEFAULT_TEXTURE_URL = '/static/images/texture.png'
ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg'}

## Gets the current user logged in to the session
def get_current_user(): 
    user_id = session.get('user_id')
    if user_id is None:
        return None
    return User.query.get(user_id)

## Serve DB path under static/images/; fall back if file missing.
@app.template_filter('texture_url')
def texture_image_url(address):
    if not address:
        return DEFAULT_TEXTURE_URL
    addr = str(address).strip().replace('\\', '/')
    if addr.startswith('/static/images/'):
        rel = addr[len('/static/images/') :]
    elif addr.startswith('static/images/'):
        rel = addr[len('static/images/') :]
    else:
        rel = os.path.basename(addr)

    rel = os.path.basename(rel)
    if not rel or rel.startswith('.'):
        return DEFAULT_TEXTURE_URL

    full = os.path.join(STATIC_IMAGES_DIR, rel)
    if os.path.isfile(full):
        return f'/static/images/{rel}'
    return DEFAULT_TEXTURE_URL


## ========== Models ==========
class User(db.Model):
    __tablename__ = 'User'
    user_id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(80), unique=True, nullable=False)
    user_password = db.Column(db.String(120), nullable=False)
    user_rating = db.Column(db.Integer, default=0)

class Texture(db.Model):
    __tablename__ = 'Texture'
    texture_id = db.Column(db.Integer, primary_key=True)
    texture_name = db.Column(db.String(80), unique=True, nullable=False)
    texture_address = db.Column(db.String(120), nullable=False)
    texture_user_id = db.Column(db.Integer, default=0)
    texture_tags = db.Column(db.String(200), nullable=True)

class Collection(db.Model):
    __tablename__ = 'Collection'
    collection_id = db.Column(db.Integer, primary_key=True)
    collection_name = db.Column(db.String(80), unique=True, nullable=False)
    collection_user_id = db.Column(db.String(120), nullable=False)
    collection_rating = db.Column(db.Integer, default=0)

class Texture_Collection(db.Model):
    __tablename__ = 'Texture_Collection'
    texture_collection_id = db.Column(db.Integer, primary_key=True)
    texture_id = db.Column(db.Integer, db.ForeignKey('Texture.texture_id'))
    collection_id = db.Column(db.Integer, db.ForeignKey('Collection.collection_id'))

class Texture_Views(db.Model):
    __tablename__ = 'Texture_Views'
    texture_views_id = db.Column(db.Integer, primary_key=True)
    texture_id = db.Column(db.Integer, db.ForeignKey('Texture.texture_id'))
    user_id = db.Column(db.Integer, db.ForeignKey('User.user_id'))

class Texture_Downloads(db.Model):
    __tablename__ = 'Texture_Downloads'
    texture_downloads_id = db.Column(db.Integer, primary_key=True)
    texture_id = db.Column(db.Integer, db.ForeignKey('Texture.texture_id'))
    user_id = db.Column(db.Integer, db.ForeignKey('User.user_id'))

## ========== Routes ==========
# Error Execeptions
def render_error(message, status_code=400):
    return render_template('error.html', error=message), status_code

@app.errorhandler(404)
def not_found_error(error):
    return render_error('Page not found.', 404)

@app.errorhandler(500)
def internal_error(error):
    return render_error('An internal server error occurred.', 500)

@app.errorhandler(Exception)
def handle_exception(error):
    if isinstance(error, HTTPException):
        return render_error(error.description, error.code)
    return render_error(str(error), 500)

# Rediracts to the default textures page 
@app.route('/')
def route():
    return redirect('/0')

# Home page is determined by 1 or 2 where 1 == textures and 2 == collection
# This simplifies code as most functionality is shared across both
@app.route('/<int:page>', methods=["POST", "GET"])
def home(page=0):
    if page == 0: # Textures Page
        page_items = Texture.query.all()
        name_field = 'texture_name'
        tags_field = 'texture_tags'
        owner_field = 'texture_user_id'
    elif page == 1: # Colections Page
        page_items = Collection.query.all()
        name_field = 'collection_name'
        tags_field = None
        owner_field = 'collection_user_id'
    else: # Error exeption
        page_items = []
        name_field = None
        tags_field = None
        owner_field = None


    ## Filtering
    ## Gets selected filtering options
    if request.method == 'POST':
        # Pull filter/sort params from form body on POST
        sort = request.form.get('sort', '')
        search_query = request.form.get('search', '').strip()
        tag_query = request.form.get('tags', '').strip()
        user_query = request.form.get('user', '').strip()
    else:
        # Pull filter/sort params from query string on GET
        search_query = request.args.get('search', '').strip()
        tag_query = request.args.get('tags', '').strip()
        user_query = request.args.get('user', '').strip()
        sort = request.args.get('sort', '')


    # --- Filter by name (search box) ---
    # Only apply the filter if there's a query and it's under 20 chars;
    # otherwise fall back to the full unfiltered list.
    if search_query and len(search_query) < 20:
        lower_search = search_query.lower()
        matched_by_name = [
            item for item in page_items
            if lower_search in (getattr(item, name_field, '') or '').lower()
        ]
    else:
        matched_by_name = page_items

    # --- Filter by uploader/owner username ---
    # Look up the User by name, then keep only items whose owner field
    # (texture_user_id / collection_user_id) matches that user's id.
    if user_query and owner_field and len(user_query) < 20:
        owner = User.query.filter_by(user_name=user_query).first()
        if owner:
            matched_by_user = [
                item for item in page_items
                if getattr(item, owner_field, None) == owner.user_id
            ]
        else:
            # No such user -> no matches
            matched_by_user = []
    else:
        matched_by_user = page_items

    # --- Filter by tags (textures only; tags_field is None for collections) ---
    # Splits the query into individual tags, splits each item's stored tag
    # string the same way, and keeps items with at least one overlapping tag.
    if tags_field and tag_query and len(tag_query) < 20:
        selected_tags = [
            tag.strip().lower()
            for tag in tag_query.split(',')
            if tag.strip()
        ]
        matched_by_tags = []
        for item in page_items:
            raw_tags = getattr(item, tags_field, '') or ''
            item_tag_list = [
                tag.strip().lower()
                for tag in raw_tags.split(',')
                if tag.strip()
            ]
            if any(tag in item_tag_list for tag in selected_tags):
                matched_by_tags.append(item)
    else:
        matched_by_tags = page_items

    # --- Combine all three filters (AND logic) ---
    # An item only survives if it appears in all three matched lists.
    filtered_items = [
        item for item in page_items
        if item in matched_by_name and item in matched_by_tags and item in matched_by_user
    ]


    # --- Precompute view/download counts from the join tables ---
    # These only make sense for Textures (page == 0); Texture_Views and
    # Texture_Downloads both key off texture_id, not collection_id.
    if page == 0:
        view_counts = dict(
            db.session.query(
                Texture_Views.texture_id,
                func.count(Texture_Views.texture_views_id)
            )
            .group_by(Texture_Views.texture_id)
            .all()
        )
        download_counts = dict(
            db.session.query(
                Texture_Downloads.texture_id,
                func.count(Texture_Downloads.texture_downloads_id)
            )
            .group_by(Texture_Downloads.texture_id)
            .all()
        )
    else:
        # Collections have no view/download tracking, so counts are empty
        view_counts = {}
        download_counts = {}


    # --- Sorting ---
    match sort:
        case 'Downloads': 
            # Look up each item's download count from the precomputed dict,
            # defaulting to 0 for items with no recorded downloads
            filtered_items = sorted(
                filtered_items,
                key=lambda item: download_counts.get(getattr(item, 'texture_id', None), 0),
                reverse=True
            )
        case 'ascending':
            # A-Z by name field
            filtered_items = sorted(
                filtered_items,
                key=lambda item: (getattr(item, name_field, '') or '').lower()
            )
        case 'descending':
            # Z-A by name field
            filtered_items = sorted(
                filtered_items,
                key=lambda item: (getattr(item, name_field, '') or '').lower(),
                reverse=True
            )
        case _:  ## Default 'Views'
            # Look up each item's view count from the precomputed dict,
            # defaulting to 0 for items with no recorded views
            filtered_items = sorted(
                filtered_items,
                key=lambda item: view_counts.get(getattr(item, 'texture_id', None), 0),
                reverse=True
            )

    return render_template(
        'home.html',
        user=get_current_user(),
        items=filtered_items,
        page=page,
        search_query=search_query,
        tag_query=tag_query,
        user_query=user_query
    )

@app.route('/texture/<texture_id>', methods=["POST", "GET"])
def texture(texture_id):
    # Users must be logged in to view textures
    user = get_current_user()
    if user is None:
        return redirect('/login')

    # Fetches users collections to be used for the 'add to collection' drop-down
    collections = Collection.query.filter_by(collection_user_id=user.user_id).all()

    texture = Texture.query.filter_by(texture_id=texture_id).first()
    uploaded_user = User.query.filter_by(user_id=texture.texture_user_id).first()

    # Handles adding and removing the texture from collection
    # - Makes sure only owned user can modify
    if texture.texture_user_id == user.user_id:
        if request.method == "POST":
            action = request.form.get("action")
            collection_id = request.form.get("collection")

            if collection_id:
                if action == "add":
                        tc = Texture_Collection(texture_id=texture_id, collection_id=collection_id)
                        db.session.add(tc)   

                elif action == "remove":
                    Texture_Collection.query.filter_by(
                        texture_id=texture_id,
                        collection_id=collection_id
                    ).delete()                    
            else:
                # if the user has no collection, takes them to the create collection page
                return redirect('/create_collection')

            db.session.commit()

    # collection_ids that already contain this texture
    in_collections = {
        row.collection_id
        for row in Texture_Collection.query.filter_by(texture_id=texture_id).all()
    }

    # keyed by collection_id (ints), not str(c) — much easier to use in JS
    collections_contained = {
        c.collection_id: (c.collection_id in in_collections)
        for c in collections
    }

    # Handles users only accounting for 1 view per texture
    already_viewed = Texture_Views.query.filter_by(
        texture_id=texture_id,
        user_id=user.user_id
    ).first() is not None

    if not already_viewed:
        tv = Texture_Views(texture_id=texture_id, user_id=user.user_id)
        db.session.add(tv)
        db.session.commit()  # commit here, or bundle with your other commit below

    views = Texture_Views.query.filter_by(texture_id=texture_id).count()
    downloads = Texture_Downloads.query.filter_by(texture_id=texture_id).count()

    return render_template(
        'texture.html',
        user=user,
        texture=texture,
        uploaded_user=uploaded_user,
        collections=collections,
        collections_contained=collections_contained,
        views = views,
        downloads=downloads,
    )

# Collection page where the collections textures are rendered
@app.route('/collection/<_collection_id>', methods=['GET', 'POST'])
def collection(_collection_id):
    user = get_current_user()
    if user is None:
        return redirect('/login')

    collection = Collection.query.filter_by(collection_id = _collection_id).one() # gets singular collection
    collection_user = User.query.filter_by(user_id = collection.collection_user_id).one() # gets collection users
     
    texture_ids = Texture_Collection.query.filter_by(collection_id = collection.collection_id).all() # gets texture_ids
    textures = [Texture.query.filter_by(texture_id = tc.texture_id).one() for tc in texture_ids] # gets textures

    return render_template(
        'collection.html', 
        user=user, 
        collection=collection, 
        collection_user=collection_user, 
        textures=textures)

# Signup page where users create a new account
# - Handles username and password max & min lengths
# - Handles only allowing unique usernames
@app.route('/signup', methods=["POST", "GET"])
def signup():
    error = None

    if request.method == 'POST':
        # Gets the username and password from the page form
        username = request.form.get('username')
        password = request.form.get('password')

        if username and password:
            if len(username) > 20 or len(password) > 20: # username and password max & min lengths
                error = "Username or Password is Too Long"
            else:
                if User.query.filter_by(user_name=username).first(): # only allowing unique usernames
                    error = "There is Already an Account with this Username"
                else:
                    # Creates the user in the database
                    hashed_password = generate_password_hash(password)
                    new_user = User(user_name=username, user_password=hashed_password, user_rating=0)
                    db.session.add(new_user)
                    db.session.commit()
                    session['user_id'] = new_user.user_id
                    return redirect("/")
        else:
            error = "Please enter a Username & Password"

    return render_template('signup.html', error=error)

# Login page where users login to their exsisting account
# - Handles username and password max & min lengths
# - Handles uername or password incorrect warning
# - Handles user sessions
@app.route('/login', methods=["POST", "GET"])
def login():
    error = None

    if request.method == 'POST':
        # Gets the username and password from the page form
        username = request.form.get('username')
        password = request.form.get('password')

        if username and password:
            if len(username) > 20 or len(password) > 20: # username and password max & min lengths
                error = "Username or Password is Too Long"
            else:
                # uername or password incorrect warning
                _user = User.query.filter_by(user_name=username).first()
                if _user:
                    if check_password_hash(_user.user_password, password):
                        session['user_id'] = _user.user_id
                        return redirect("/")
                    elif password == _user.user_password:  # legacy plaintext fallback
                        _user.user_password = generate_password_hash(password)
                        db.session.commit()
                        session['user_id'] = _user.user_id
                        return redirect("/")
                    else:
                        error = "Username or Password is Incorrect"
        else:
            error = "Please enter a Username & Password"

    return render_template('login.html', error=error)


# Simple route to logout the user and clears the user session
@app.route('/logout', methods=["POST", "GET"])
def logout():
    session['user_id'] = None
    return redirect("/")

# User page where they can see their user texture and collections and manage their profile
# - Shows Users Textures
# - Shows users Collections
# - Handles logged in user and external users
@app.route('/user/<username>')
def user_profile(username):
    profile_user = User.query.filter_by(user_name=username).first()
    if profile_user is None: # Makes sure user_id exists
        abort(404)

    # Fetches users textures and collection
    textures = Texture.query.filter_by(texture_user_id=profile_user.user_id).all()
    collections = Collection.query.filter_by(collection_user_id = profile_user.user_id).all()

    return render_template(
        'user.html',
        user=get_current_user(),
        profile_user=profile_user,
        follower_count=367,
        joined_display='1/05/2026',
        texture_count_display='3,546',
        collection_count_display='742',
        texture_more_total=13357,
        collection_more_total=13357,
        textures=textures,
        collections=collections,
        owner = profile_user == get_current_user()
    )


# Upload page where users upload a texture
# - Handles only allowing specific file types
# - Handles Min & Max name characters
# - Handles CSV Tags
# - Handles saving iamges to internal storage & Database
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    user = get_current_user()
    if user is None: # Makes sure user_id exists
        return redirect('/login')

    error = None

    if request.method == 'POST':
        # Gets the form data
        display_name = (request.form.get('display_name') or '').strip()
        file = request.files.get('image')
        texture_tags = request.form.get('tags', '').strip()

        if len(display_name) > 20 or len(display_name) < 5: ## Character limits
            error = "Name Must be Between 5 and 20 Characters Long"
        elif len(texture_tags) > 100: ## Tag character limit
             error = "Tags Must be Less Than 100 Characters Long"
        elif not display_name: # Must be display name
            error = 'Please enter a display name.'
        elif not file or file.filename == '': # Must be an image file
            error = 'Please choose an image file.'
        elif Texture.query.filter_by(texture_name=display_name).first(): # Must have unique name
            error = 'That display name is already taken.'
        else:

            original = secure_filename(file.filename)
            ext = os.path.splitext(original)[1].lower()
            if ext not in ALLOWED_IMAGE_EXTENSIONS: # Makes sure file type is valid
                error = 'Allowed types: PNG, JPEG, JPG'
            else:
                # all condition met and adds to database
                os.makedirs(STATIC_IMAGES_DIR, exist_ok=True)
                stored_name = f'{uuid.uuid4().hex}{ext}'
                dest = os.path.join(STATIC_IMAGES_DIR, stored_name)
                file.save(dest) # Saves file to directory
                url_path = f'/static/images/{stored_name}'
                texture = Texture(
                    texture_name=display_name,
                    texture_address=url_path,
                    texture_user_id=user.user_id,
                    texture_tags=texture_tags
                )
                db.session.add(texture)
                db.session.commit()
                return redirect('/')

    return render_template(
        'upload.html', 
        user=user, 
        error=error
        )

# Create colection Page  where users create collection
# - Handles Min & Max name characters
@app.route('/create_collection', methods=['GET', 'POST'])
def create_collection():
    error = None
    user = get_current_user()
    if user is None: # Makes sure user_id exists
        return redirect('/login')

    if request.method == 'POST':
        # Gets the display name from the form
        display_name = (request.form.get('display_name') or '').strip()

        if len(display_name) > 20 or len(display_name) < 5: # Character limit
            error = "Name Must Be Between 5 and 20 Characters Long"

        elif display_name:
            # All conditions met, Creating new collection associated with the users profile
            collection = Collection(collection_name = display_name, collection_user_id = user.user_id)
            db.session.add(collection)
            db.session.commit()

            return redirect('/')

    return render_template('create_collection.html', user=user, error=error)

# Delete Texture
# - Deltes all instances of a texture through all relevant tables
@app.route('/delete_texture/<int:texture_id>', methods=['GET', 'POST'])
def delete_texture(texture_id):
    db.session.execute(delete(Texture_Views).where(Texture_Views.texture_id == texture_id))
    db.session.execute(delete(Texture_Downloads).where(Texture_Downloads.texture_id == texture_id))
    db.session.execute(delete(Texture_Collection).where(Texture_Collection.texture_id == texture_id))
    db.session.execute(delete(Texture).where(Texture.texture_id == texture_id))
    db.session.commit()

    return redirect("/")

# Delete Collection
# - Deltes all instances of a collection through all relevant tables
@app.route('/delete_collection/<int:collection_id>', methods=['GET', 'POST'])
def delete_collection(collection_id):
    db.session.execute(delete(Collection).where(Collection.collection_id == collection_id))
    db.session.execute(delete(Texture_Collection).where(Texture_Collection.collection_id == collection_id))
    db.session.commit()

    return redirect("/")

# Download Image route where it downloads the image of the selected texture page
# - Handles fetching download from server storage
# - Handles Texture Downloads Stat
@app.route('/download/<int:texture_id>', methods=['GET', 'POST'])
def download_image(texture_id):
    user = get_current_user()
    if user is None: # Makes sure user_id exists
        return redirect('/login')

    texture = Texture.query.filter_by(texture_id=texture_id).first()
    if not texture: # Handles no texture error
        return "Texture not found", 404

    # Makes sure valid user is deleting
    if texture.texture_user_id != user.user_id:
         return redirect('/')

    # Extract filename from the stored path
    if texture.texture_address.startswith('/static/images/'):
        filename = texture.texture_address[len('/static/images/'):]
    else:
        filename = os.path.basename(texture.texture_address)
    
    file_path = os.path.join(STATIC_IMAGES_DIR, filename)
    if not os.path.isfile(file_path):
        return "File not found", 404



    # Texture Downloads Stat
    already_downloaded = Texture_Downloads.query.filter_by(
        texture_id=texture_id,
        user_id=user.user_id
    ).first() is not None


    if not already_downloaded:
        td = Texture_Downloads(texture_id=texture_id, user_id=user.user_id)
        db.session.add(td)
        db.session.commit() 

    # Sends file to users device
    return send_file(file_path, as_attachment=True, download_name=texture.texture_name)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)