from flask import Flask, render_template, request, redirect, url_for, current_app, session, flash
import sqlite3
import os
from dotenv import load_dotenv
from functools import wraps
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def login_required(f):
    # Decorator to check if user is logged in
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs) # Returns original function if logged in
    return decorated_function

def get_recent_books(limit=6):
    '''
    Get the most recent books from the database
    limit: number of books to return
    returns: list of books
    '''
    conn = get_db_connection()
    books = conn.execute('''
        SELECT b.*, u.name as owner_name 
        FROM Books b
        JOIN Users u ON b.user_id = u.user_id
        WHERE b.availability = 'available'
        ORDER BY b.date_posted DESC
        LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return books

def get_top_users(limit=4):
    '''
    Get the top users from the database
    limit: number of users to return
    returns: list of users
    '''
    conn = get_db_connection()
    users = conn.execute('''
        SELECT u.*, 
               COALESCE(AVG(r.rating), 0) as rating,
               COUNT(r.review_id) as review_count
        FROM Users u
        LEFT JOIN Reviews r ON u.user_id = r.user_id
        GROUP BY u.user_id
        ORDER BY rating DESC, review_count DESC
        LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return users

@app.route('/')
def index():
    '''
    Redirect to home page if user is logged in
    Else, redirect to login page
    '''
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('home'))

@app.route('/home')
@login_required
def home():
    recent_books = get_recent_books()
    top_users = get_top_users()
    return render_template('home.html', recent_books=recent_books, top_users=top_users)

@app.route('/browse')
@login_required
def browse_books():
    return render_template('browse_books.html')

@app.route('/my-books')
@login_required
def my_books():
    return render_template('my_books.html')

@app.route('/messages')
@login_required
def messages():
    return render_template('messages.html')

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        location = request.form.get('location', '')

        # Validate form data
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))
        
        conn = get_db_connection()
        
        # Check if email already exists
        existing_user = conn.execute('SELECT * FROM Users WHERE email = ?', (email,)).fetchone()
        if existing_user:
            flash('Email already registered.', 'danger')
            conn.close()
            return redirect(url_for('register'))
        
        # Hash the password
        hashed_password = generate_password_hash(password)
        
        # Insert new user
        conn.execute('''
            INSERT INTO Users (name, email, password, location)
            VALUES (?, ?, ?, ?)
        ''', (name, email, hashed_password, location))
        
        conn.commit()
        conn.close()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        remember = True if request.form.get('remember') else False
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM Users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['user_id']
            session['name'] = user['name']
            if remember:
                session.permanent = True
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# ... rest of your routes ...

if __name__ == '__main__':
    app.run(debug=True)
