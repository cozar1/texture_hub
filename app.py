"""Flask application for uploading, browsing and collecting textures.

Provides user accounts, texture uploads, collections of textures, and
simple view/download tracking.
"""

import os
import uuid
from functools import wraps

from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    send_file,
    session,
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import delete, func
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

# ========== Config ==========
app = Flask(__name__)
app.secret_key = "replace-this-with-a-secure-secret"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

# ========== Directories ==========
STATIC_IMAGES_DIR = os.path.join(app.root_path, "static", "images")
DEFAULT_TEXTURE_URL = "/static/images/texture.png"
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}

# Character limits shared by the signup/login/upload/collection forms.
NAME_MIN_LENGTH = 5
NAME_MAX_LENGTH = 20
CREDENTIAL_MAX_LENGTH = 20
TAGS_MAX_LENGTH = 100


def get_current_user():
    """Return the ``User`` tied to the current session, or ``None``."""
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return User.query.get(user_id)


@app.template_filter("texture_url")
def texture_image_url(address):
    """Resolve a stored texture address to a safe static URL.

    Falls back to ``DEFAULT_TEXTURE_URL`` if the address is empty, points
    outside ``static/images/``, or the file no longer exists on disk.
    """
    if not address:
        return DEFAULT_TEXTURE_URL
    addr = str(address).strip().replace("\\", "/")
    if addr.startswith("/static/images/"):
        rel = addr[len("/static/images/"):]
    elif addr.startswith("static/images/"):
        rel = addr[len("static/images/"):]
    else:
        rel = os.path.basename(addr)

    rel = os.path.basename(rel)
    if not rel or rel.startswith("."):
        return DEFAULT_TEXTURE_URL

    full = os.path.join(STATIC_IMAGES_DIR, rel)
    if os.path.isfile(full):
        return f"/static/images/{rel}"
    return DEFAULT_TEXTURE_URL


# ========== Models ==========
class User(db.Model):  # pylint: disable=too-few-public-methods
    """A registered account."""

    __tablename__ = "User"
    user_id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(80), unique=True, nullable=False)
    user_password = db.Column(db.String(120), nullable=False)
    user_rating = db.Column(db.Integer, default=0)


class Texture(db.Model):  # pylint: disable=too-few-public-methods
    """An uploaded texture image and its metadata."""

    __tablename__ = "Texture"
    texture_id = db.Column(db.Integer, primary_key=True)
    texture_name = db.Column(db.String(80), unique=True, nullable=False)
    texture_address = db.Column(db.String(120), nullable=False)
    texture_user_id = db.Column(db.Integer, default=0)
    texture_tags = db.Column(db.String(200), nullable=True)


class Collection(db.Model):  # pylint: disable=too-few-public-methods
    """A named grouping of textures owned by a user."""

    __tablename__ = "Collection"
    collection_id = db.Column(db.Integer, primary_key=True)
    collection_name = db.Column(db.String(80), unique=True, nullable=False)
    collection_user_id = db.Column(db.String(120), nullable=False)
    collection_rating = db.Column(db.Integer, default=0)


class TextureCollection(db.Model):  # pylint: disable=too-few-public-methods
    """Join table linking a texture to a collection."""

    __tablename__ = "Texture_Collection"
    texture_collection_id = db.Column(db.Integer, primary_key=True)
    texture_id = db.Column(db.Integer, db.ForeignKey("Texture.texture_id"))
    collection_id = db.Column(
        db.Integer, db.ForeignKey("Collection.collection_id")
    )


class TextureViews(db.Model):  # pylint: disable=too-few-public-methods
    """Records a single user's view of a texture."""

    __tablename__ = "Texture_Views"
    texture_views_id = db.Column(db.Integer, primary_key=True)
    texture_id = db.Column(db.Integer, db.ForeignKey("Texture.texture_id"))
    user_id = db.Column(db.Integer, db.ForeignKey("User.user_id"))


class TextureDownloads(db.Model):  # pylint: disable=too-few-public-methods
    """Records a single user's download of a texture."""

    __tablename__ = "Texture_Downloads"
    texture_downloads_id = db.Column(db.Integer, primary_key=True)
    texture_id = db.Column(db.Integer, db.ForeignKey("Texture.texture_id"))
    user_id = db.Column(db.Integer, db.ForeignKey("User.user_id"))


# ========== Error Handling ==========
def render_error(message, status_code=400):
    """Render the shared error page with the given message and status."""
    return render_template("error.html", error=message), status_code


@app.errorhandler(Exception)
def handle_exception(error):
    """Translate unhandled exceptions into a friendly error page."""
    if isinstance(error, HTTPException):
        code = error.code
        if code == 404:
            message = "That page doesn't exist."
        elif code == 401:
            message = "Please log in to continue."
        elif code == 403:
            message = "You don't have permission to do that."
        elif code == 413:
            message = "That file is too large to upload."
        else:
            message = error.description
        return render_error(message, code)

    app.logger.exception(error)
    return render_error("An internal server error occurred.", 500)


# ========== Helper Functions ==========
def login_required(view):
    """Decorator that redirects to ``/login`` when no user is signed in.

    On success, the current ``User`` is passed as the first positional
    argument to the wrapped view.
    """

    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return redirect("/login")
        return view(user, *args, **kwargs)

    return wrapped


def get_or_404(model, **filters):
    """Return the matching row, or abort with a 404 if none exists."""
    obj = model.query.filter_by(**filters).first()
    if obj is None:
        abort(404)
    return obj


def record_exists(model, **filters):
    """Return whether a row matching ``filters`` exists for ``model``."""
    return model.query.filter_by(**filters).first() is not None


def get_or_none(model, **filters):
    """Return the matching row, or ``None`` if none exists."""
    return model.query.filter_by(**filters).first()


def cascade_delete(mapping):
    """Delete rows across several tables in one transaction.

    ``mapping`` is an iterable of ``(model, column, value)`` tuples; every
    row where ``column == value`` is removed from ``model``.
    """
    for model, column, value in mapping:
        db.session.execute(delete(model).where(column == value))
    db.session.commit()


def record_once(model, **filters):
    """Insert a row for ``model`` if one matching ``filters`` doesn't exist."""
    already_exists = model.query.filter_by(**filters).first() is not None
    if not already_exists:
        db.session.add(model(**filters))
        db.session.commit()


# ========== Home page helpers ==========
def _get_page_config(page):
    """Return the item list and field names that ``page`` browses.

    Page 0 browses textures, page 1 browses collections; any other value
    yields an empty, fieldless configuration.
    """
    if page == 0:
        return Texture.query.all(), "texture_name", "texture_tags", "texture_user_id"
    if page == 1:
        return Collection.query.all(), "collection_name", None, "collection_user_id"
    return [], None, None, None


def _get_filter_params():
    """Read the search/tags/user/sort filter params for the current request."""
    source = request.form if request.method == "POST" else request.args
    return {
        "search": source.get("search", "").strip(),
        "tags": source.get("tags", "").strip(),
        "user": source.get("user", "").strip(),
        "sort": source.get("sort", ""),
    }


def _filter_by_name(page_items, name_field, search_query):
    """Keep items whose ``name_field`` contains ``search_query`` (case-insensitive)."""
    if not search_query or len(search_query) >= NAME_MAX_LENGTH:
        return page_items
    lower_search = search_query.lower()
    return [
        item
        for item in page_items
        if lower_search in (getattr(item, name_field, "") or "").lower()
    ]


def _filter_by_owner(page_items, owner_field, user_query):
    """Keep items owned by the user named ``user_query``."""
    if not (user_query and owner_field) or len(user_query) >= NAME_MAX_LENGTH:
        return page_items
    owner = get_or_none(User, user_name=user_query)
    if not owner:
        return []
    return [
        item for item in page_items if getattr(item, owner_field, None) == owner.user_id
    ]


def _filter_by_tags(page_items, tags_field, tag_query):
    """Keep items that share at least one tag with the comma-separated ``tag_query``."""
    if not (tags_field and tag_query) or len(tag_query) >= NAME_MAX_LENGTH:
        return page_items

    selected_tags = [tag.strip().lower() for tag in tag_query.split(",") if tag.strip()]
    matched = []
    for item in page_items:
        raw_tags = getattr(item, tags_field, "") or ""
        item_tags = [tag.strip().lower() for tag in raw_tags.split(",") if tag.strip()]
        if any(tag in item_tags for tag in selected_tags):
            matched.append(item)
    return matched


def _get_texture_counts():
    """Return ``(view_counts, download_counts)`` dicts keyed by texture id."""
    view_counts = dict(
        db.session.query(
            TextureViews.texture_id,
            func.count(TextureViews.texture_views_id),  # pylint: disable=not-callable
        )
        .group_by(TextureViews.texture_id)
        .all()
    )
    download_counts = dict(
        db.session.query(
            TextureDownloads.texture_id,
            func.count(  # pylint: disable=not-callable
                TextureDownloads.texture_downloads_id
            ),
        )
        .group_by(TextureDownloads.texture_id)
        .all()
    )
    return view_counts, download_counts


def _by_download_count(download_counts):
    """Return a sort key function ranking items by download count."""
    def key(item):
        return download_counts.get(getattr(item, "texture_id", None), 0)
    return key


def _by_view_count(view_counts):
    """Return a sort key function ranking items by view count."""
    def key(item):
        return view_counts.get(getattr(item, "texture_id", None), 0)
    return key


def _by_name(name_field):
    """Return a sort key function ranking items alphabetically by name."""
    def key(item):
        return (getattr(item, name_field, "") or "").lower()
    return key


def _sort_items(items, sort, name_field, view_counts, download_counts):
    """Sort ``items`` per the requested ``sort`` mode."""
    if sort == "downloads":
        return sorted(items, key=_by_download_count(download_counts), reverse=True)
    if sort == "ascending":
        return sorted(items, key=_by_name(name_field))
    if sort == "descending":
        return sorted(items, key=_by_name(name_field), reverse=True)
    # Default: most viewed first.
    return sorted(items, key=_by_view_count(view_counts), reverse=True)


# ========== Routes ==========
@app.route("/")
def index():
    """Redirect the root URL to the default textures page."""
    return redirect("/0")


@app.route("/<int:page>", methods=["POST", "GET"])
def home(page=0):
    """Browse textures (page 0) or collections (page 1) with filters/sort."""
    page_items, name_field, tags_field, owner_field = _get_page_config(page)
    params = _get_filter_params()

    filtered_items = _filter_by_name(page_items, name_field, params["search"])
    filtered_items = [
        item for item in filtered_items
        if item in _filter_by_owner(page_items, owner_field, params["user"])
    ]
    filtered_items = [
        item for item in filtered_items
        if item in _filter_by_tags(page_items, tags_field, params["tags"])
    ]

    if page == 0:
        view_counts, download_counts = _get_texture_counts()
    else:
        view_counts, download_counts = {}, {}

    filtered_items = _sort_items(
        filtered_items, params["sort"], name_field, view_counts, download_counts
    )

    return render_template(
        "home.html",
        user=get_current_user(),
        items=filtered_items,
        page=page,
        search_query=params["search"],
        tag_query=params["tags"],
        user_query=params["user"],
    )


def _update_texture_collections(texture_id, user):
    """Handle the add/remove-from-collection form on the texture page."""
    action = request.form.get("action")
    collection_id = request.form.get("collection")

    if not collection_id:
        return redirect("/create_collection")

    # Only allow modifying a collection the current user actually owns.
    owns_collection = record_exists(
        Collection, collection_id=collection_id, collection_user_id=user.user_id
    )
    if not owns_collection:
        abort(403)

    if action == "add":
        db.session.add(
            TextureCollection(texture_id=texture_id, collection_id=collection_id)
        )
    elif action == "remove":
        TextureCollection.query.filter_by(
            texture_id=texture_id, collection_id=collection_id
        ).delete()

    db.session.commit()
    return None


@app.route("/texture/<texture_id>", methods=["POST", "GET"])
@login_required
def texture_detail(user, texture_id):
    """Show a texture's details and manage its collection membership."""
    collections = Collection.query.filter_by(collection_user_id=user.user_id).all()

    texture_obj = get_or_404(Texture, texture_id=texture_id)
    uploaded_user = get_or_404(User, user_id=texture_obj.texture_user_id)

    if request.method == "POST":
        redirect_response = _update_texture_collections(texture_id, user)
        if redirect_response is not None:
            return redirect_response

    in_collections = {
        row.collection_id
        for row in TextureCollection.query.filter_by(texture_id=texture_id).all()
    }
    collections_contained = {
        c.collection_id: (c.collection_id in in_collections) for c in collections
    }

    already_viewed = record_exists(
        TextureViews, texture_id=texture_id, user_id=user.user_id
    )
    if not already_viewed:
        record_once(TextureViews, texture_id=texture_id, user_id=user.user_id)

    views = TextureViews.query.filter_by(texture_id=texture_id).count()
    downloads = TextureDownloads.query.filter_by(texture_id=texture_id).count()

    return render_template(
        "texture.html",
        user=user,
        texture=texture_obj,
        uploaded_user=uploaded_user,
        collections=collections,
        collections_contained=collections_contained,
        views=views,
        downloads=downloads,
    )


@app.route("/collection/<_collection_id>", methods=["GET", "POST"])
@login_required
def collection_detail(user, _collection_id):
    """Show a collection and the textures it contains."""
    collection_obj = Collection.query.filter_by(collection_id=_collection_id).one()
    collection_user = User.query.filter_by(
        user_id=collection_obj.collection_user_id
    ).one()

    texture_links = TextureCollection.query.filter_by(
        collection_id=collection_obj.collection_id
    ).all()
    textures = [
        Texture.query.filter_by(texture_id=link.texture_id).one()
        for link in texture_links
    ]

    return render_template(
        "collection.html",
        user=user,
        collection=collection_obj,
        collection_user=collection_user,
        textures=textures,
    )


@app.route("/signup", methods=["POST", "GET"])
def signup():
    """Create a new account with a unique username and hashed password."""
    error = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not (username and password):
            error = "Please enter a Username & Password"
        elif len(username) > CREDENTIAL_MAX_LENGTH or len(password) > CREDENTIAL_MAX_LENGTH:
            error = "Username or Password is Too Long"
        elif record_exists(User, user_name=username):
            error = "There is Already an Account with this Username"
        else:
            hashed_password = generate_password_hash(password)
            new_user = User(
                user_name=username, user_password=hashed_password, user_rating=0
            )
            db.session.add(new_user)
            db.session.commit()
            session["user_id"] = new_user.user_id
            return redirect("/")

    return render_template("signup.html", error=error)


@app.route("/login", methods=["POST", "GET"])
def login():
    """Authenticate a user, upgrading legacy plaintext passwords on the fly."""
    error = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not (username and password):
            error = "Please enter a Username & Password"
        elif len(username) > CREDENTIAL_MAX_LENGTH or len(password) > CREDENTIAL_MAX_LENGTH:
            error = "Username or Password is Too Long"
        else:
            found_user = get_or_none(User, user_name=username)
            if found_user and check_password_hash(found_user.user_password, password):
                session["user_id"] = found_user.user_id
                return redirect("/")
            if found_user and password == found_user.user_password:
                # Legacy plaintext account: upgrade it to a hashed password.
                found_user.user_password = generate_password_hash(password)
                db.session.commit()
                session["user_id"] = found_user.user_id
                return redirect("/")
            error = "Username or Password is Incorrect"

    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST", "GET"])
def logout():
    """Clear the current session."""
    session["user_id"] = None
    return redirect("/")


@app.route("/user/<username>")
def user_profile(username):
    """Show a user's profile, textures and collections."""
    profile_user = get_or_404(User, user_name=username)

    textures = Texture.query.filter_by(texture_user_id=profile_user.user_id).all()
    collections = Collection.query.filter_by(
        collection_user_id=profile_user.user_id
    ).all()

    return render_template(
        "user.html",
        user=get_current_user(),
        profile_user=profile_user,
        follower_count=367,
        joined_display="1/05/2026",
        texture_count_display="3,546",
        collection_count_display="742",
        texture_more_total=13357,
        collection_more_total=13357,
        textures=textures,
        collections=collections,
        owner=profile_user == get_current_user(),
    )


def _validate_upload(display_name, texture_tags, file):
    """Return an error string for the upload form, or ``None`` if it's valid."""
    has_file = bool(file and file.filename)
    ext = os.path.splitext(secure_filename(file.filename))[1].lower() if has_file else ""

    checks = (
        (not display_name, "Please enter a display name."),
        (
            len(display_name) > NAME_MAX_LENGTH or len(display_name) < NAME_MIN_LENGTH,
            "Name Must be Between 5 and 20 Characters Long",
        ),
        (len(texture_tags) > TAGS_MAX_LENGTH, "Tags Must be Less Than 100 Characters Long"),
        (not has_file, "Please choose an image file."),
        (
            has_file and record_exists(Texture, texture_name=display_name),
            "That display name is already taken.",
        ),
        (has_file and ext not in ALLOWED_IMAGE_EXTENSIONS, "Allowed types: PNG, JPEG, JPG"),
    )

    for failed, message in checks:
        if failed:
            return message
    return None


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload(user):
    """Handle uploading a new texture image and its metadata."""
    error = None

    if request.method == "POST":
        display_name = (request.form.get("display_name") or "").strip()
        file = request.files.get("image")
        texture_tags = request.form.get("tags", "").strip()

        error = _validate_upload(display_name, texture_tags, file)
        if error is None:
            os.makedirs(STATIC_IMAGES_DIR, exist_ok=True)
            ext = os.path.splitext(secure_filename(file.filename))[1].lower()
            stored_name = f"{uuid.uuid4().hex}{ext}"
            file.save(os.path.join(STATIC_IMAGES_DIR, stored_name))

            new_texture = Texture(
                texture_name=display_name,
                texture_address=f"/static/images/{stored_name}",
                texture_user_id=user.user_id,
                texture_tags=texture_tags,
            )
            db.session.add(new_texture)
            db.session.commit()
            return redirect("/")

    return render_template("upload.html", user=user, error=error)


@app.route("/create_collection", methods=["GET", "POST"])
@login_required
def create_collection(user):
    """Handle creating a new, empty collection owned by the current user."""
    error = None

    if request.method == "POST":
        display_name = (request.form.get("display_name") or "").strip()

        if len(display_name) > NAME_MAX_LENGTH or len(display_name) < NAME_MIN_LENGTH:
            error = "Name Must Be Between 5 and 20 Characters Long"
        elif display_name:
            new_collection = Collection(
                collection_name=display_name, collection_user_id=user.user_id
            )
            db.session.add(new_collection)
            db.session.commit()
            return redirect("/")

    return render_template("create_collection.html", user=user, error=error)


@app.route("/delete_texture/<int:texture_id>", methods=["GET", "POST"])
@login_required
def delete_texture(user, texture_id):
    """Delete a texture and its related view/download/collection rows."""
    texture_obj = get_or_404(Texture, texture_id=texture_id)
    if texture_obj.texture_user_id != user.user_id:
        return redirect("/")

    cascade_delete(
        [
            (TextureViews, TextureViews.texture_id, texture_id),
            (TextureDownloads, TextureDownloads.texture_id, texture_id),
            (TextureCollection, TextureCollection.texture_id, texture_id),
            (Texture, Texture.texture_id, texture_id),
        ]
    )
    return redirect("/")


@app.route("/delete_collection/<int:collection_id>", methods=["GET", "POST"])
@login_required
def delete_collection(user, collection_id):
    """Delete a collection and its texture memberships."""
    collection_obj = get_or_404(Collection, collection_id=collection_id)
    if collection_obj.collection_user_id != user.user_id:
        return redirect("/")

    cascade_delete(
        [
            (Collection, Collection.collection_id, collection_id),
            (TextureCollection, TextureCollection.collection_id, collection_id),
        ]
    )
    return redirect("/")


@app.route("/download/<int:texture_id>", methods=["GET", "POST"])
@login_required
def download_image(user, texture_id):
    """Send the stored image file for a texture and record the download."""
    texture_obj = get_or_404(Texture, texture_id=texture_id)

    if texture_obj.texture_address.startswith("/static/images/"):
        filename = texture_obj.texture_address[len("/static/images/"):]
    else:
        filename = os.path.basename(texture_obj.texture_address)

    file_path = os.path.join(STATIC_IMAGES_DIR, filename)
    if not os.path.isfile(file_path):
        return "File not found", 404

    already_downloaded = record_exists(
        TextureDownloads, texture_id=texture_id, user_id=user.user_id
    )
    if not already_downloaded:
        record_once(TextureDownloads, texture_id=texture_id, user_id=user.user_id)

    ext = os.path.splitext(filename)[1]
    download_name = secure_filename(texture_obj.texture_name) + ext

    return send_file(file_path, as_attachment=True, download_name=download_name)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)