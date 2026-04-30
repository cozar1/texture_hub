from flask import Flask, render_template, request
import sqlite3

app = Flask(__name__)
user_id = None

def query(query, param=(), commit=False):
    with sqlite3.connect("database.db") as conn:
        cur = conn.cursor()
        cur.execute(query, param)
        if commit:
            conn.commit()
            return cur.lastrowid
        else:
            return cur.fetchall()

@app.route('/')
def home():
    global user_id

    textures = query("SELECT * FROM Texture")
    return render_template('home.html', textures=textures, user_id=user_id)

@app.route('/signup',methods=["POST","GET"])
def signup():
    global user_id
    error = None

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username and password:
            usernames = query("SELECT user_name FROM user")
            if (username,) in usernames:
                error = "There is Already an Account with this Username"
            else:
                query('''INSERT INTO user (user_name, user_password, user_rating)
                    VALUES (?, ?, ?)''',(username,password,0))
                
                _user_id = query("SELECT user_id FROM user WHERE user_name = ?",(username,))
                user_id = _user_id

                return app.redirect("/")


    return render_template('signup.html', error=error)

@app.route('/login',methods=["POST","GET"])
def login():
    global user_id
    error = None

    if request.method == 'POST':
        print("pos")
        username = request.form.get('username')
        password = request.form.get('password')

        if username and password:
            usernames = query("SELECT user_name FROM User")
            if (username,) in usernames:
                if password == query("SELECT user_password FROM User WHERE user_name = ?",(username,))[0][0]:
                    print("Logged in as "+str(username))

                    _user_id = query("SELECT user_id FROM user WHERE user_name = ?",(username,))
                    user_id = _user_id

                    return app.redirect("/")
                else:
                    error = "Username or Password is Incorrect"

            else:
                error = "Username isn't Registered with any Account"


    return render_template('login.html', error=error)

app.run(debug=True)
