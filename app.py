import os
import uuid

from flask import Flask, render_template, request, redirect, send_file, session, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from sqlalchemy import func

app = Flask(__name__)
app.secret_key = 'replace-this-with-a-secure-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

STATIC_IMAGES_DIR = os.path.join(app.root_path, 'static', 'images')
DEFAULT_TEXTURE_URL = '/static/images/texture.png'
ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}


def get_current_user():
    user_id = session.get('user_id')
    if user_id is None:
        return None
    return User.query.get(user_id)


@app.template_filter('texture_url')
def texture_image_url(address):
    """Serve DB path under static/images/; fall back if file missing."""
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


# --- Models ---

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

class Collection(db.Model):
    __tablename__ = 'Collection'
    collection_id = db.Column(db.Integer, primary_key=True)
    collection_name = db.Column(db.String(80), unique=True, nullable=False)
    collection_user_id = db.Column(db.String(120), nullable=False)
    collection_rating = db.Column(db.Integer, default=0)

class Texture_Collection(db.Model):
    __tablename__ = 'Texture_Collection'
    texture_collection_id = db.Column(db.Integer, primary_key= True)
    texture_id = db.Column(db.Integer, foreign_key= True)
    collection_id = db.Column(db.Integer, foreign_key= True)


# --- Routes ---

@app.route('/',methods=["POST", "GET"])
def home():
    # Prefer query-string filters (GET) so the URL is shareable/bookmarkable,
    # but also accept POST payloads to keep older forms working.
    src = request.args if request.method == 'GET' else request.form
    name_q = (src.get('name') or '').strip()
    user_q = (src.get('user') or '').strip()
    sort = (src.get('sort') or 'new').strip().lower()

    q = db.session.query(Texture).outerjoin(User, User.user_id == Texture.texture_user_id)

    if name_q:
        like = f"%{name_q.lower()}%"
        q = q.filter(func.lower(Texture.texture_name).like(like))

    if user_q:
        like = f"%{user_q.lower()}%"
        q = q.filter(func.lower(User.user_name).like(like))

    if sort == 'name':
        q = q.order_by(Texture.texture_name.asc(), Texture.texture_id.desc())
    elif sort == 'uploader':
        q = q.order_by(User.user_name.asc(), Texture.texture_id.desc())
    else:  # default: newest first
        q = q.order_by(Texture.texture_id.desc())

    textures = q.all()

    return render_template(
        'home.html',
        user=get_current_user(),
        textures=textures,
        filters={'name': name_q, 'user': user_q, 'sort': sort},
        result_count=len(textures),
    )

@app.route('/texture/<texture_id>', methods=["POST", "GET"])
def texture(texture_id):
    texture = Texture.query.filter_by(texture_id=texture_id).first()
    uploaded_user = User.query.filter_by(user_id=texture.texture_user_id).first()
    return render_template('texture.html', user=get_current_user(), texture=texture, uploaded_user=uploaded_user)


@app.route('/signup', methods=["POST", "GET"])
def signup():
    error = None

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username and password:
            if User.query.filter_by(user_name=username).first():
                error = "There is Already an Account with this Username"
            elif User.query.filter_by(user_password=password).first():
                existing = User.query.filter_by(user_password=password).first()
                error = f"User {existing.user_name} Already has this password"
            else:
                new_user = User(user_name=username, user_password=password, user_rating=0)
                db.session.add(new_user)
                db.session.commit()
                session['user_id'] = new_user.user_id
                return redirect("/")
        else:
            error = "Please enter a Username & Password"

    return render_template('signup.html', error=error)


@app.route('/login', methods=["POST", "GET"])
def login():
    error = None

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username and password:
            _user = User.query.filter_by(user_name=username).first()
            if _user:
                if password == _user.user_password:
                    print("Logged in as " + username)
                    session['user_id'] = _user.user_id
                    return redirect("/")
                else:
                    error = "Username or Password is Incorrect"
            else:
                error = "Username isn't Registered with any Account"
        else:
            error = "Please enter a Username & Password"

    return render_template('login.html', error=error)

@app.route('/logout', methods=["POST", "GET"])
def logout():
    session['user_id'] = None
    return redirect("/")


@app.route('/user/<username>')
def user_profile(username):
    profile_user = User.query.filter_by(user_name=username).first()
    if profile_user is None:
        abort(404)

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
        collections=collections
    )


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    user = get_current_user()
    if user is None:
        return redirect('/login')

    error = None

    if request.method == 'POST':
        display_name = (request.form.get('display_name') or '').strip()
        file = request.files.get('image')

        if not display_name:
            error = 'Please enter a display name.'
        elif not file or file.filename == '':
            error = 'Please choose an image file.'
        elif Texture.query.filter_by(texture_name=display_name).first():
            error = 'That display name is already taken.'
        else:
            original = secure_filename(file.filename)
            ext = os.path.splitext(original)[1].lower()
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                error = 'Allowed types: PNG, JPEG, GIF, WebP.'
            else:
                os.makedirs(STATIC_IMAGES_DIR, exist_ok=True)
                stored_name = f'{uuid.uuid4().hex}{ext}'
                dest = os.path.join(STATIC_IMAGES_DIR, stored_name)
                file.save(dest)
                url_path = f'/static/images/{stored_name}'
                texture = Texture(
                    texture_name=display_name,
                    texture_address=url_path,
                    texture_user_id=user.user_id,
                )
                db.session.add(texture)
                db.session.commit()
                return redirect('/')

    return render_template('upload.html', user=user, error=error)

@app.route('/create_collection', methods=['GET', 'POST'])
def create_collection():
    user = get_current_user()
    if user is None:
        return redirect('/login')

    if request.method == 'POST':
        display_name = (request.form.get('display_name') or '').strip()

        if display_name:
            collection = Collection(collection_name = display_name, collection_user_id = user.user_id)
            db.session.add(collection)
            db.session.commit()

        return redirect('/')

    return render_template('create_collection.html', user=user)

@app.route('/collection/<_collection_id>', methods=['GET', 'POST'])
def collection(_collection_id):
    user = get_current_user()


    collection = Collection.query.filter_by(collection_id = _collection_id).one()
    collection_user = User.query.filter_by(user_id = collection.collection_user_id).one()

    return render_template('collection.html', user=user, collection=collection, collection_user=collection_user)

@app.route('/download/<int:texture_id>', methods=['GET', 'POST'])
def download_image(texture_id):
    texture = Texture.query.filter_by(texture_id=texture_id).first()
    if not texture:
        return "Texture not found", 404

    # Extract filename from the stored path
    if texture.texture_address.startswith('/static/images/'):
        filename = texture.texture_address[len('/static/images/'):]
    else:
        filename = os.path.basename(texture.texture_address)
    
    file_path = os.path.join(STATIC_IMAGES_DIR, filename)
    if not os.path.isfile(file_path):
        return "File not found", 404
    
    return send_file(file_path, as_attachment=True, download_name=texture.texture_name)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)