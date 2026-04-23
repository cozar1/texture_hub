from flask import Flask, render_template
import sqlite3

app = Flask(__name__)

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
    return render_template('home.html')

app.run(debug=True)
