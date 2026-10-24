from flask import Flask, render_template, request, redirect, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv
from functools import wraps
from datetime import datetime

load_dotenv()

app = Flask(__name__)
secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    raise RuntimeError("SECRET_KEY must be configured")

app.config["SECRET_KEY"] = secret_key
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024
db_url = os.environ.get('DATABASE_URL', 'sqlite:///site.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url

db = SQLAlchemy(app)
# render_as_batch lets Alembic alter constraints on SQLite during local development
migrate = Migrate(app, db, render_as_batch=True)
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 🔐 ADD YOUR CLOUDINARY KEYS HERE
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET")
)

# ---------------- MODELS ----------------

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    subscription_tier = db.Column(db.String(50), default='Free')
    profile_pic = db.Column(db.String(500), nullable=True)
    theme_color = db.Column(db.String(50), default='#00E5FF')

class Movie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    category = db.Column(db.String(100))
    video_url = db.Column(db.String(500))
    thumbnail = db.Column(db.String(500))
    subtitle = db.Column(db.String(500))

class WatchHistory(db.Model):
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "movie_id",
            name="uq_watch_history_user_movie",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    movie_id = db.Column(
        db.Integer,
        db.ForeignKey("movie.id"),
        nullable=False,
    )
    timestamp = db.Column(db.Float, default=0.0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

class MyList(db.Model):
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "movie_id",
            name="uq_mylist_user_movie",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    movie_id = db.Column(
        db.Integer,
        db.ForeignKey("movie.id"),
        nullable=False,
    )
    added_date = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------- LOGIN ----------------

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------- ROUTES ----------------

@app.template_filter('quality_filter')
def quality_filter(url, user):
    if not url or not user: return url
    tier = 'Premium' if getattr(user, 'is_admin', False) else getattr(user, 'subscription_tier', 'Free')
    if "res.cloudinary.com" in url and "/upload/" in url:
        if tier == 'Free':
            return url.replace("/upload/", "/upload/c_scale,w_640/")
        elif tier == 'Basic':
            return url.replace("/upload/", "/upload/c_scale,w_1280/")
    return url

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
            flash("You do not have permission to access the admin portal.", "danger")
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    q = request.args.get("q")
    
    if q:
        movies = Movie.query.filter(Movie.title.contains(q)).all()
        return render_template("index.html", movies=movies, q=q)
        
    movies = Movie.query.all()
    continue_watching = []
    recommended = []
    mylist_movies = []
    mylist_ids = []
    
    if current_user.is_authenticated:
        # My List Data
        mylist_items = MyList.query.filter_by(user_id=current_user.id).order_by(MyList.added_date.desc()).all()
        for item in mylist_items:
            m = Movie.query.get(item.movie_id)
            if m:
                mylist_movies.append(m)
                mylist_ids.append(m.id)

        # Watch Tracking Data
        history = WatchHistory.query.filter_by(user_id=current_user.id).order_by(WatchHistory.last_updated.desc()).all()
        watched_movie_ids = []
        watched_cats = {}
        
        for h in history:
            m = Movie.query.get(h.movie_id)
            if m:
                watched_movie_ids.append(m.id)
                watched_cats[m.category] = watched_cats.get(m.category, 0) + 1
                
                # Active sessions > 2 seconds
                if h.timestamp > 2:
                    continue_watching.append({"movie": m, "timestamp": h.timestamp})
                    
        # Algorithm: Highest watched category, excluding already watched
        if watched_cats:
            top_cat = max(watched_cats, key=watched_cats.get)
            recommended = Movie.query.filter(Movie.category == top_cat, ~Movie.id.in_(watched_movie_ids)).limit(6).all()
            
        # Fallback to general unwatched movies
        if not recommended:
            recommended = Movie.query.filter(~Movie.id.in_(watched_movie_ids)).limit(6).all()
            
    return render_template("index.html", movies=movies, continue_watching=continue_watching, recommended=recommended, mylist_movies=mylist_movies, mylist_ids=mylist_ids)


# ---------- AUTH ----------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        existing_user = User.query.filter_by(username=request.form['username']).first()
        if existing_user:
            flash("Username already exists.", "danger")
            return redirect('/register')

        user = User(
            name=request.form['name'],
            username=request.form['username'],
            password=generate_password_hash(request.form['password'])
        )
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. Please log in.", "success")
        return redirect('/login')

    return render_template("register.html")


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()

        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            flash(f"Welcome back, {user.name}!", "success")
            return redirect('/')
        else:
            flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect('/')


# ---------- PROFILE ----------

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_profile':
            current_user.name = request.form.get('name', current_user.name)
            pic = request.files.get('profile_pic')
            if pic and pic.filename != '':
                try:
                    upload = cloudinary.uploader.upload(pic, resource_type="image")
                    current_user.profile_pic = upload['secure_url']
                except Exception as e:
                    flash(f"Error uploading image: {str(e)}", "danger")
            db.session.commit()
            flash("Profile updated successfully.", "success")
            
        elif action == 'update_subscription':
            new_tier = request.form.get('subscription_tier')
            if new_tier in ['Free', 'Basic', 'Premium']:
                current_user.subscription_tier = new_tier
                db.session.commit()
                flash(f"Subscription upgraded to {new_tier} plan!", "success")
                
        elif action == 'update_theme':
            new_color = request.form.get('theme_color')
            if new_color:
                current_user.theme_color = new_color
                db.session.commit()
                flash("Theme color updated!", "success")

        return redirect('/profile')

    return render_template("profile.html")


# ---------- API & TRACKING ----------

@app.route('/api/progress', methods=['POST'])
@login_required
def update_progress():
    data = request.json
    movie_id = data.get('movie_id')
    timestamp = data.get('timestamp')
    if movie_id and timestamp is not None:
        history = WatchHistory.query.filter_by(user_id=current_user.id, movie_id=movie_id).first()
        if not history:
            history = WatchHistory(user_id=current_user.id, movie_id=movie_id)
            db.session.add(history)
        history.timestamp = float(timestamp)
        history.last_updated = datetime.utcnow()
        db.session.commit()
    return {"status": "ok"}

@app.route('/api/mylist/toggle', methods=['POST'])
@login_required
def toggle_mylist():
    data = request.json
    movie_id = data.get('movie_id')
    
    if not movie_id:
        return {"error": "Missing movie_id"}, 400
        
    item = MyList.query.filter_by(user_id=current_user.id, movie_id=movie_id).first()
    if item:
        db.session.delete(item)
        db.session.commit()
        return {"status": "removed"}
    else:
        new_item = MyList(user_id=current_user.id, movie_id=movie_id)
        db.session.add(new_item)
        db.session.commit()
        return {"status": "added"}


# ---------- WATCH ----------

@app.route('/watch/<int:id>')
@login_required
def watch(id):
    movie = Movie.query.get_or_404(id)
    history = WatchHistory.query.filter_by(user_id=current_user.id, movie_id=id).first()
    start_time = history.timestamp if history else 0.0
    return render_template("watch.html", movie=movie, start_time=start_time)


# ---------- ADMIN CMS ----------

@app.route('/admin')
@login_required
@admin_required
def admin():
    movies = Movie.query.order_by(Movie.id.desc()).all()
    return render_template("admin.html", movies=movies)

@app.route('/admin/upload', methods=['POST'])
@login_required
@admin_required
def admin_upload():
    video = request.files.get('video')
    thumb = request.files.get('thumbnail')
    sub = request.files.get('subtitle')
    
    if not video or not thumb:
        return {"error": "Video and Thumbnail files are both required."}, 400
        
    try:
        import tempfile
        fd, temp_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        
        try:
            video.save(temp_path)
            video_upload = cloudinary.uploader.upload_large(temp_path, resource_type="video", chunk_size=20000000)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
        thumb_upload = cloudinary.uploader.upload(thumb, resource_type="image")
        
        sub_url = None
        if sub and sub.filename != '':
            sub_upload = cloudinary.uploader.upload(sub, resource_type="raw")
            sub_url = sub_upload['secure_url']

        movie = Movie(
            title=request.form.get('title', 'Unknown Title'),
            category=request.form.get('category', 'Uncategorized'),
            video_url=video_upload['secure_url'],
            thumbnail=thumb_upload['secure_url'],
            subtitle=sub_url
        )
        db.session.add(movie)
        db.session.commit()
        return {"message": "Movie uploaded successfully!"}
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/admin/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def admin_delete(id):
    movie = Movie.query.get_or_404(id)
    db.session.delete(movie)
    db.session.commit()
    flash(f"Movie '{movie.title}' deleted from catalog.", "success")
    return redirect('/admin')

@app.route('/admin/edit/<int:id>', methods=['POST'])
@login_required
@admin_required
def admin_edit(id):
    movie = Movie.query.get_or_404(id)
    movie.title = request.form.get('title', movie.title)
    movie.category = request.form.get('category', movie.category)
    
    thumb = request.files.get('thumbnail')
    if thumb and thumb.filename != '':
        try:
            upload = cloudinary.uploader.upload(thumb, resource_type="image")
            movie.thumbnail = upload['secure_url']
        except Exception as e:
            flash(f"Error generating thumbnail: {str(e)}", "danger")
            
    db.session.commit()
    flash(f"Metadata for '{movie.title}' updated.", "success")
    return redirect('/admin')


# ---------- RUN ----------

if __name__ == "__main__":
    app.run(debug=True)