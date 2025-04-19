from flask import Flask, render_template, request, redirect, url_for, current_app, session, flash, jsonify
import sqlite3
import os
from dotenv import load_dotenv
from functools import wraps
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import time

# Load SECRET_KEY from .env file
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

def get_recent_books(limit=3):
    '''
    Get the most recent books from the database
    limit: number of books to return (default: 3)
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

def get_top_users(limit=3):
    '''
    Get the top users from the database
    limit: number of users to return
    returns: list of users
    '''
    conn = get_db_connection()
    users = conn.execute('''
        SELECT u.*, 
               COALESCE(AVG(r.rating), 0) as avg_rating,
               COUNT(r.review_id) as review_count
        FROM Users u
        LEFT JOIN Reviews r ON u.user_id = r.user_id
        GROUP BY u.user_id
        ORDER BY avg_rating DESC, review_count DESC
        LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return users

def search_books(query=None, course_code=None, subject=None, page=1, per_page=9):
    '''
    Search books based on various criteria
    query: search term for title, author, or ISBN
    course_code: specific course code
    subject: book subject
    page: page number for pagination
    per_page: number of results per page
    returns: tuple of (books, total_count)
    '''
    conn = get_db_connection()
    
    base_query = '''
        SELECT b.*, u.name as owner_name 
        FROM Books b
        JOIN Users u ON b.user_id = u.user_id
        WHERE b.availability = 'available'
    '''
    
    conditions = []
    params = []
    
    if query:
        conditions.append('''
            (b.title LIKE ? OR 
             b.author LIKE ? OR 
             b.isbn LIKE ?)
        ''')
        search_term = f'%{query}%'
        params.extend([search_term, search_term, search_term])
    
    if course_code:
        conditions.append('b.course_code = ?')
        params.append(course_code)
    
    if subject:
        conditions.append('b.subject = ?')
        params.append(subject)
    
    if conditions:
        base_query += ' AND ' + ' AND '.join(conditions)
    
    count_query = f'SELECT COUNT(*) as total FROM ({base_query})'
    total_count = conn.execute(count_query, params).fetchone()['total']
    
    base_query += ' ORDER BY b.date_posted DESC LIMIT ? OFFSET ?'
    params.extend([per_page, (page - 1) * per_page])
    
    books = conn.execute(base_query, params).fetchall()
    conn.close()
    
    return books, total_count

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
    '''
    Display the home page
    Grabs listing of 3 most recent books and top 3 users
    '''
    recent_books = get_recent_books(3)  # Get 3 most recent books
    top_users = get_top_users()
    return render_template('home.html', recent_books=recent_books, top_users=top_users)

@app.route('/browse')
@login_required
def browse_books():
    '''
    Display the browse books page
    Grabs listing of all available books
    '''
    page = request.args.get('page', 1, type=int)
    per_page = 12  # Number of books per page
    
    conn = get_db_connection()
    
    # Get total count of available books
    total_count = conn.execute('''
        SELECT COUNT(*) as count 
        FROM Books 
        WHERE availability = 'available'
    ''').fetchone()['count']
    
    # Calculate total pages
    total_pages = (total_count + per_page - 1) // per_page
    
    # Get books for current page
    books = conn.execute('''
        SELECT b.*, u.name as owner_name 
        FROM Books b
        JOIN Users u ON b.user_id = u.user_id
        WHERE b.availability = 'available'
        ORDER BY b.date_posted DESC
        LIMIT ? OFFSET ?
    ''', (per_page, (page - 1) * per_page)).fetchall()
    
    conn.close()
    
    return render_template('browse_books.html', 
                         books=books,
                         page=page,
                         total_pages=total_pages,
                         total_count=total_count)

@app.route('/my-books')
@login_required
def my_books():
    '''
    Display the my books page
    Grabs listing of books owned by the user and books borrowed by the user
    '''
    conn = get_db_connection()
    
    books_lending = conn.execute('''
        SELECT * FROM Books 
        WHERE user_id = ? 
        ORDER BY date_posted DESC
    ''', (session['user_id'],)).fetchall()
    
    books_borrowing = conn.execute('''
        SELECT b.*, u.name as lender_name, u.user_id as lender_id
        FROM Books b
        JOIN Users u ON b.user_id = u.user_id
        JOIN BorrowedBooks bb ON b.book_id = bb.book_id
        WHERE bb.borrower_id = ? AND bb.return_date IS NULL
        ORDER BY bb.borrow_date DESC
    ''', (session['user_id'],)).fetchall()
    
    # Get pending borrow requests for books owned by the user
    pending_requests = conn.execute('''
        SELECT br.*, b.title, b.book_id, u.name as borrower_name
        FROM BorrowRequests br
        JOIN Books b ON br.book_id = b.book_id
        JOIN Users u ON br.borrower_id = u.user_id
        WHERE b.user_id = ? AND br.status = 'pending'
        ORDER BY br.request_date DESC
    ''', (session['user_id'],)).fetchall()
    
    conn.close()
    return render_template('my_books.html', 
                         books_lending=books_lending, 
                         books_borrowing=books_borrowing,
                         pending_requests=pending_requests)

@app.route('/messages')
@login_required
def messages():
    '''
    Display the messages page
    Grabs listing of all users the current user has conversations with
    Functions as a chat interface
    '''
    conn = get_db_connection()
    
    # Get all users the current user has conversations with
    chats = conn.execute('''
        SELECT DISTINCT u.user_id, u.name, u.profile_image,
               (SELECT m.message_id 
                FROM Messages m 
                WHERE (m.sender_id = ? AND m.receiver_id = u.user_id) 
                   OR (m.sender_id = u.user_id AND m.receiver_id = ?)
                ORDER BY m.timestamp DESC 
                LIMIT 1) as last_message_id,
               (SELECT m.content 
                FROM Messages m 
                WHERE (m.sender_id = ? AND m.receiver_id = u.user_id) 
                   OR (m.sender_id = u.user_id AND m.receiver_id = ?)
                ORDER BY m.timestamp DESC 
                LIMIT 1) as last_message_preview
        FROM Messages m
        JOIN Users u ON (m.sender_id = u.user_id AND m.receiver_id = ?)
                    OR (m.sender_id = ? AND m.receiver_id = u.user_id)
        WHERE u.user_id != ?
        GROUP BY u.user_id
        ORDER BY last_message_id DESC
    ''', (session['user_id'], session['user_id'], 
          session['user_id'], session['user_id'],
          session['user_id'], session['user_id'],
          session['user_id'])).fetchall()
    
    # Get the current chat user and messages if specified
    current_chat_user = None
    chat_messages = []
    message_id = request.args.get('message_id', type=int)
    user_id = request.args.get('user_id', type=int)
    
    if user_id:
        # Get user details for new chat
        current_chat_user = conn.execute('''
            SELECT user_id, name, profile_image 
            FROM Users 
            WHERE user_id = ?
        ''', (user_id,)).fetchone()
        
        if current_chat_user:
            # Get messages for this user
            chat_messages = conn.execute('''
                SELECT m.*, 
                       sender.name as sender_name, sender.profile_image as sender_image,
                       receiver.name as receiver_name, receiver.profile_image as receiver_image
                FROM Messages m
                JOIN Users sender ON m.sender_id = sender.user_id
                JOIN Users receiver ON m.receiver_id = receiver.user_id
                WHERE (m.sender_id = ? AND m.receiver_id = ?)
                   OR (m.sender_id = ? AND m.receiver_id = ?)
                ORDER BY m.timestamp ASC
            ''', (session['user_id'], user_id, user_id, session['user_id'])).fetchall()
    elif message_id:
        # Get the user for the selected message
        message = conn.execute('''
            SELECT sender_id, receiver_id 
            FROM Messages 
            WHERE message_id = ? AND (sender_id = ? OR receiver_id = ?)
        ''', (message_id, session['user_id'], session['user_id'])).fetchone()
        
        if message:
            other_user_id = message['sender_id'] if message['sender_id'] != session['user_id'] else message['receiver_id']
            current_chat_user = conn.execute('''
                SELECT user_id, name, profile_image 
                FROM Users 
                WHERE user_id = ?
            ''', (other_user_id,)).fetchone()
            
            if current_chat_user:
                # Get messages for this user
                chat_messages = conn.execute('''
                    SELECT m.*, 
                           sender.name as sender_name, sender.profile_image as sender_image,
                           receiver.name as receiver_name, receiver.profile_image as receiver_image
                    FROM Messages m
                    JOIN Users sender ON m.sender_id = sender.user_id
                    JOIN Users receiver ON m.receiver_id = receiver.user_id
                    WHERE (m.sender_id = ? AND m.receiver_id = ?)
                       OR (m.sender_id = ? AND m.receiver_id = ?)
                    ORDER BY m.timestamp ASC
                ''', (session['user_id'], other_user_id, other_user_id, session['user_id'])).fetchall()
    
    conn.close()
    return render_template('messages.html', 
                         chats=chats,
                         current_chat_user=current_chat_user,
                         chat_messages=chat_messages)

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    '''
    Send a message to a user
    '''
    if request.method == 'POST':
        recipient_id = request.form.get('recipient_id')
        content = request.form.get('content')
        
        if not recipient_id or not content:
            flash('Please fill in all fields.', 'danger')
            return redirect(url_for('messages'))
        
        conn = get_db_connection()
        
        # Check if recipient exists
        recipient = conn.execute('SELECT user_id FROM Users WHERE user_id = ?', (recipient_id,)).fetchone()
        if not recipient:
            flash('Recipient not found.', 'danger')
            conn.close()
            return redirect(url_for('messages'))
        
        # Insert the message
        conn.execute('''
            INSERT INTO Messages (sender_id, receiver_id, content, timestamp)
            VALUES (?, ?, ?, datetime('now'))
        ''', (session['user_id'], recipient_id, content))
        conn.commit()
        
        # Get the message ID for redirection
        message = conn.execute('''
            SELECT message_id 
            FROM Messages 
            WHERE sender_id = ? AND receiver_id = ? 
            ORDER BY timestamp DESC 
            LIMIT 1
        ''', (session['user_id'], recipient_id)).fetchone()
        
        conn.close()
        
        return redirect(url_for('messages', message_id=message['message_id']))

@app.route('/profile')
@login_required
def profile():
    conn = get_db_connection()
    
    # Get user's basic info and review stats
    user = conn.execute('''
        SELECT u.*, 
               COALESCE(AVG(r.rating), 0) as rating,
               COUNT(r.review_id) as review_count
        FROM Users u
        LEFT JOIN Reviews r ON u.user_id = r.user_id
        WHERE u.user_id = ?
        GROUP BY u.user_id
    ''', (session['user_id'],)).fetchone()
    
    # Get total books count separately
    total_books = conn.execute('''
        SELECT COUNT(*) as count
        FROM Books
        WHERE user_id = ?
    ''', (session['user_id'],)).fetchone()
    
    # Add total_books to user dict
    user = dict(user)
    user['total_books'] = total_books['count']
    
    recent_books = conn.execute('''
        SELECT * FROM Books 
        WHERE user_id = ? 
        ORDER BY date_posted DESC 
        LIMIT 5
    ''', (session['user_id'],)).fetchall()
    
    conn.close()
    return render_template('profile.html', user=user, recent_books=recent_books)

@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        name = request.form.get('name')
        location = request.form.get('location')
        email = request.form.get('email')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        profile_image = request.files.get('profile_image')
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM Users WHERE user_id = ?', (session['user_id'],)).fetchone()
        
        if new_password:
            if not check_password_hash(user['password'], current_password):
                flash('Current password is incorrect.', 'danger')
                conn.close()
                return redirect(url_for('edit_profile'))
            
            if new_password != confirm_password:
                flash('New passwords do not match.', 'danger')
                conn.close()
                return redirect(url_for('edit_profile'))
            
            hashed_password = generate_password_hash(new_password)
            conn.execute('UPDATE Users SET password = ? WHERE user_id = ?', 
                        (hashed_password, session['user_id']))
        
        if email != user['email']:
            existing_user = conn.execute('SELECT * FROM Users WHERE email = ? AND user_id != ?', 
                                       (email, session['user_id'])).fetchone()
            if existing_user:
                flash('Email is already taken.', 'danger')
                conn.close()
                return redirect(url_for('edit_profile'))
        
        # Handle profile image upload
        if profile_image and profile_image.filename:
            try:
                # Create images directory if it doesn't exist
                images_dir = os.path.join(app.root_path, 'static', 'images')
                os.makedirs(images_dir, exist_ok=True)
                
                # Generate unique filename
                filename = f"user_{session['user_id']}_{int(time.time())}.jpg"
                filepath = os.path.join(images_dir, filename)
                
                # Save the image
                profile_image.save(filepath)
                
                # Update profile image path
                profile_image_path = f"/static/images/{filename}"
            except Exception as e:
                flash('Error saving profile image. Please try again.', 'danger')
                conn.close()
                return redirect(url_for('edit_profile'))
        else:
            profile_image_path = user['profile_image']
        
        conn.execute('''
            UPDATE Users 
            SET name = ?, email = ?, location = ?, profile_image = ?
            WHERE user_id = ?
        ''', (name, email, location, profile_image_path, session['user_id']))
        
        conn.commit()
        conn.close()
        
        session['name'] = name
        
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM Users WHERE user_id = ?', (session['user_id'],)).fetchone()
    conn.close()
    
    return render_template('edit_profile.html', user=user)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        location = request.form.get('location', '')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))
        
        conn = get_db_connection()
        
        existing_user = conn.execute('SELECT * FROM Users WHERE email = ?', (email,)).fetchone()
        if existing_user:
            flash('Email already registered.', 'danger')
            conn.close()
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password)
        
        conn.execute('''
            INSERT INTO Users (name, email, password, location, profile_image)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, email, hashed_password, location, '/static/images/default.jpg'))
        
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

@app.route('/search')
@login_required
def search():
    query = request.args.get('query', '').strip()
    course_code = request.args.get('course_code', '').strip()
    subject = request.args.get('subject', '').strip()
    page = request.args.get('page', 1, type=int)
    
    books, total_count = search_books(
        query=query if query else None,
        course_code=course_code if course_code else None,
        subject=subject if subject else None,
        page=page
    )
    
    pagination = {
        'page': page,
        'per_page': 9,
        'total': total_count,
        'pages': (total_count + 8) // 9,
        'has_prev': page > 1,
        'has_next': page * 9 < total_count,
        'prev_num': page - 1,
        'next_num': page + 1,
        'iter_pages': lambda: range(1, ((total_count + 8) // 9) + 1)
    }
    
    return render_template(
        'search_results.html',
        books=books,
        query=query,
        course_code=course_code,
        subject=subject,
        pagination=pagination
    )

@app.route('/add_book', methods=['GET', 'POST'])
@login_required
def add_book():
    '''
    Display the add book page
    '''
    conn = get_db_connection()
    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        isbn = request.form.get('isbn')
        course_code = request.form.get('course_code')
        subject = request.form.get('subject')
        condition = request.form.get('condition')
        
        if not all([title, author, isbn, course_code, subject, condition]):
            flash('Please fill in all required fields', 'danger')
            conn.close()
            return redirect(url_for('add_book'))
        
        try:
            conn.execute('''
                INSERT INTO Books (user_id, title, author, isbn, course_code, subject, condition, availability, date_posted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (session['user_id'], title, author, isbn, course_code, subject, condition, 'available'))
            conn.commit()
            flash('Book updated successfully!', 'success')
            conn.close()
            return redirect(url_for('my_books'))
        
        except Exception as e:
            flash('An error occurred while adding the book. Please try again.', 'danger')
            return redirect(url_for('add_book'))
    
    return render_template('add_book.html')

@app.route('/edit_book/<int:book_id>', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    conn = get_db_connection()
    
    book = conn.execute('''
        SELECT * FROM Books 
        WHERE book_id = ? AND user_id = ?
    ''', (book_id, session['user_id'])).fetchone()
    
    if not book:
        flash('Book not found or you do not have permission to edit it.', 'danger')
        conn.close()
        return redirect(url_for('my_books'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        isbn = request.form.get('isbn')
        course_code = request.form.get('course_code')
        subject = request.form.get('subject')
        condition = request.form.get('condition')
        
        if not all([title, author, isbn, course_code, subject, condition]):
            flash('Please fill in all required fields', 'danger')
            conn.close()
            return redirect(url_for('edit_book', book_id=book_id))
        
        try:
            conn.execute('''
                UPDATE Books 
                SET title = ?, author = ?, isbn = ?, 
                    course_code = ?, subject = ?, condition = ?
                WHERE book_id = ? AND user_id = ?
            ''', (title, author, isbn, course_code, subject, 
                  condition, book_id, session['user_id']))
            
            conn.commit()
            flash('Book updated successfully!', 'success')
            conn.close()
            return redirect(url_for('my_books'))
            
        except Exception as e:
            flash('An error occurred while updating the book. Please try again.', 'danger')
            conn.close()
            return redirect(url_for('edit_book', book_id=book_id))
    
    conn.close()
    return render_template('edit_book.html', book=book)

@app.route('/delete_book/<int:book_id>', methods=['POST'])
@login_required
def delete_book(book_id):
    conn = get_db_connection()
    
    try:
        # Check if book exists and belongs to the user
        book = conn.execute('''
            SELECT * FROM Books 
            WHERE book_id = ? AND user_id = ?
        ''', (book_id, session['user_id'])).fetchone()
        
        if not book:
            flash('Book not found or you do not have permission to delete it.', 'danger')
            conn.close()
            return redirect(url_for('my_books'))

        # Check for pending borrow requests
        pending_requests = conn.execute('''
            SELECT br.*, u.user_id as requester_id, u.name as requester_name
            FROM BorrowRequests br
            JOIN Users u ON br.borrower_id = u.user_id
            WHERE br.book_id = ? AND br.status = 'pending'
        ''', (book_id,)).fetchall()

        # Notify requesters that the book has been deleted
        for request in pending_requests:
            message_content = f"The book '{book['title']}' you requested to borrow has been deleted by the owner."
            conn.execute('''
                INSERT INTO Messages (sender_id, recipient_id, content, timestamp)
                VALUES (?, ?, ?, datetime('now'))
            ''', (session['user_id'], request['requester_id'], message_content))

        # Delete the book and any related records
        conn.execute('DELETE FROM BorrowRequests WHERE book_id = ?', (book_id,))
        conn.execute('DELETE FROM Books WHERE book_id = ? AND user_id = ?', 
                    (book_id, session['user_id']))
        conn.commit()
        
        flash('Book deleted successfully!', 'success')
        
    except Exception as e:
        flash('An error occurred while deleting the book. Please try again.', 'danger')
    
    finally:
        conn.close()
    
    return redirect(url_for('my_books'))

@app.route('/view_profile/<int:user_id>')
@login_required
def view_profile(user_id):
    try:
        # Get the user's details
        user = get_db_connection().execute(
            'SELECT * FROM Users WHERE user_id = ?',
            (user_id,)
        ).fetchone()

        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('home'))

        # Get user's recent listings
        recent_listings = get_db_connection().execute(
            '''
            SELECT b.* 
            FROM Books b
            WHERE b.user_id = ?
            ORDER BY b.date_posted DESC
            LIMIT 5
            ''',
            (user_id,)
        ).fetchall()

        # Get user's average rating
        rating_result = get_db_connection().execute(
            '''
            SELECT AVG(rating) as avg_rating, COUNT(*) as review_count
            FROM Reviews
            WHERE user_id = ?
            ''',
            (user_id,)
        ).fetchone()

        avg_rating = rating_result['avg_rating'] if rating_result['avg_rating'] else 0
        review_count = rating_result['review_count'] if rating_result['review_count'] else 0

        return render_template('view_profile.html',
                             user=user,
                             recent_listings=recent_listings,
                             avg_rating=avg_rating,
                             review_count=review_count)
    except Exception as e:
        flash('An error occurred while loading the profile.', 'danger')
        return redirect(url_for('home'))

@app.route('/add_review/<int:user_id>', methods=['GET', 'POST'])
@login_required
def add_review(user_id):
    if request.method == 'POST':
        rating = request.form.get('rating')
        comment = request.form.get('comment')
        
        if not all([rating, comment]):
            flash('Please fill in all fields.', 'danger')
            return redirect(url_for('add_review', user_id=user_id))
        
        try:
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO Reviews (user_id, reviewer_id, rating, comment, timestamp)
                VALUES (?, ?, ?, ?, datetime('now'))
            ''', (user_id, session['user_id'], rating, comment))
            conn.commit()
            conn.close()
            
            flash('Review added successfully!', 'success')
            return redirect(url_for('view_profile', user_id=user_id))
            
        except Exception as e:
            flash('An error occurred while adding the review.', 'danger')
            return redirect(url_for('add_review', user_id=user_id))
    
    user = get_db_connection().execute(
        'SELECT * FROM Users WHERE user_id = ?',
        (user_id,)
    ).fetchone()
    
    return render_template('add_review.html', user=user)

@app.route('/my_reviews')
@login_required
def my_reviews():
    conn = get_db_connection()

    received_reviews = conn.execute('''
        SELECT r.*, u.name as reviewer_name
        FROM Reviews r
        JOIN Users u ON r.reviewer_id = u.user_id
        WHERE r.user_id = ?
        ORDER BY r.review_id DESC
    ''', (session['user_id'],)).fetchall()

    given_reviews = conn.execute('''
        SELECT r.*, u.name as reviewee_name
        FROM Reviews r
        JOIN Users u ON r.user_id = u.user_id
        WHERE r.reviewer_id = ?
        ORDER BY r.review_id DESC
    ''', (session['user_id'],)).fetchall()
    
    conn.close()
    
    return render_template('my_reviews.html',
                         received_reviews=received_reviews,
                         given_reviews=given_reviews)

@app.route('/edit_review/<int:review_id>', methods=['GET', 'POST'])
@login_required
def edit_review(review_id):
    conn = get_db_connection()
    review = conn.execute('''
        SELECT r.*, u.name as reviewee_name
        FROM Reviews r
        JOIN Users u ON r.user_id = u.user_id
        WHERE r.review_id = ? AND r.reviewer_id = ?
    ''', (review_id, session['user_id'])).fetchone()
    
    if not review:
        flash('Review not found or you do not have permission to edit it.', 'danger')
        conn.close()
        return redirect(url_for('my_reviews'))
    
    if request.method == 'POST':
        rating = request.form.get('rating')
        comment = request.form.get('comment')
        
        if not all([rating, comment]):
            flash('Please fill in all fields.', 'danger')
            conn.close()
            return redirect(url_for('edit_review', review_id=review_id))
        
        try:
            conn.execute('''
                UPDATE Reviews
                SET rating = ?, comment = ?
                WHERE review_id = ? AND reviewer_id = ?
            ''', (rating, comment, review_id, session['user_id']))
            conn.commit()
            conn.close()
            
            flash('Review updated successfully!', 'success')
            return redirect(url_for('my_reviews'))
            
        except Exception as e:
            flash('An error occurred while updating the review.', 'danger')
            conn.close()
            return redirect(url_for('edit_review', review_id=review_id))
    
    conn.close()
    return render_template('edit_review.html', review=review)

@app.route('/delete_review/<int:review_id>', methods=['POST'])
@login_required
def delete_review(review_id):
    conn = get_db_connection()
    
    try:
        review = conn.execute('''
            SELECT * FROM Reviews
            WHERE review_id = ? AND reviewer_id = ?
        ''', (review_id, session['user_id'])).fetchone()
        
        if not review:
            flash('Review not found or you do not have permission to delete it.', 'danger')
            conn.close()
            return redirect(url_for('my_reviews'))
        
        conn.execute('DELETE FROM Reviews WHERE review_id = ? AND reviewer_id = ?',
                    (review_id, session['user_id']))
        conn.commit()
        
        flash('Review deleted successfully!', 'success')
        
    except Exception as e:
        flash('An error occurred while deleting the review.', 'danger')
    
    finally:
        conn.close()
    
    return redirect(url_for('my_reviews'))

@app.route('/book/<int:book_id>')
@login_required
def view_book(book_id):
    try:
        conn = get_db_connection()
        
        # Get book details with owner information and ratings
        book = conn.execute('''
            SELECT b.*, u.name as owner_name, u.user_id as owner_id, u.location,
                   u.profile_image, 
                   COALESCE(AVG(r.rating), 0) as rating,
                   COUNT(r.review_id) as review_count
            FROM Books b
            JOIN Users u ON b.user_id = u.user_id
            LEFT JOIN Reviews r ON u.user_id = r.user_id
            WHERE b.book_id = ?
            GROUP BY b.book_id, u.user_id
        ''', (book_id,)).fetchone()
        
        if not book:
            flash('Book not found.', 'danger')
            return redirect(url_for('home'))
            
        # Get current borrowing status if any
        borrowing = conn.execute('''
            SELECT bb.*, u.name as borrower_name
            FROM BorrowedBooks bb
            JOIN Users u ON bb.borrower_id = u.user_id
            WHERE bb.book_id = ? AND bb.return_date IS NULL
        ''', (book_id,)).fetchone()
        
        conn.close()
        
        return render_template('view_book.html', 
                             book=book, 
                             borrowing=borrowing)
                             
    except Exception as e:
        flash('An error occurred while loading the book details.', 'danger')
        return redirect(url_for('home'))

@app.route('/borrow_book/<int:book_id>', methods=['POST'])
@login_required
def borrow_book(book_id):
    try:
        conn = get_db_connection()
        
        # Check if book exists and is available
        book = conn.execute('''
            SELECT * FROM Books 
            WHERE book_id = ? AND user_id != ? AND availability = 'available'
        ''', (book_id, session['user_id'])).fetchone()
        
        if not book:
            flash('Book not found or not available for borrowing.', 'danger')
            conn.close()
            return redirect(url_for('view_book', book_id=book_id))
            
        # Check if there's already a pending borrow request
        existing_request = conn.execute('''
            SELECT * FROM BorrowRequests 
            WHERE book_id = ? AND status = 'pending'
        ''', (book_id,)).fetchone()
        
        if existing_request:
            flash('There is already a pending borrow request for this book.', 'danger')
            conn.close()
            return redirect(url_for('view_book', book_id=book_id))
            
        # Create borrow request
        conn.execute('''
            INSERT INTO BorrowRequests (book_id, borrower_id, request_date, status)
            VALUES (?, ?, datetime('now'), 'pending')
        ''', (book_id, session['user_id']))
        
        # Update book availability to pending
        conn.execute('''
            UPDATE Books 
            SET availability = 'pending' 
            WHERE book_id = ?
        ''', (book_id,))
        
        # Send automatic message to book owner
        message_content = f"I would like to borrow your book '{book['title']}'. Please approve or decline my request."
        conn.execute('''
            INSERT INTO Messages (sender_id, receiver_id, content, timestamp)
            VALUES (?, ?, ?, datetime('now'))
        ''', (session['user_id'], book['user_id'], message_content))
        
        conn.commit()
        conn.close()
        
        flash('Borrow request sent successfully! The owner will review your request.', 'success')
        return redirect(url_for('my_books'))
        
    except Exception as e:
        print(f"Error in borrow_book: {str(e)}")  # Debug print
        flash('An error occurred while processing your borrow request.', 'danger')
        return redirect(url_for('view_book', book_id=book_id))

@app.route('/approve_borrow/<int:request_id>', methods=['POST'])
@login_required
def approve_borrow(request_id):
    try:
        conn = get_db_connection()
        
        # Get borrow request details
        request = conn.execute('''
            SELECT br.*, b.user_id as owner_id, b.title
            FROM BorrowRequests br
            JOIN Books b ON br.book_id = b.book_id
            WHERE br.request_id = ? AND br.status = 'pending'
        ''', (request_id,)).fetchone()
        
        if not request or request['owner_id'] != session['user_id']:
            flash('Invalid request or you do not have permission to approve it.', 'danger')
            conn.close()
            return redirect(url_for('my_books'))
            
        # Update borrow request status
        conn.execute('''
            UPDATE BorrowRequests 
            SET status = 'approved', 
                approval_date = datetime('now')
            WHERE request_id = ?
        ''', (request_id,))
        
        # Create borrowing record
        conn.execute('''
            INSERT INTO BorrowedBooks (book_id, borrower_id, borrow_date, expected_return_date)
            VALUES (?, ?, datetime('now'), datetime('now', '+14 days'))
        ''', (request['book_id'], request['borrower_id']))
        
        # Update book availability
        conn.execute('''
            UPDATE Books 
            SET availability = 'borrowed' 
            WHERE book_id = ?
        ''', (request['book_id'],))
        
        # Send confirmation message to borrower
        message_content = f"Your request to borrow '{request['title']}' has been approved! Please arrange pickup with the owner."
        conn.execute('''
            INSERT INTO Messages (sender_id, receiver_id, content, timestamp)
            VALUES (?, ?, ?, datetime('now'))
        ''', (session['user_id'], request['borrower_id'], message_content))
        
        conn.commit()
        conn.close()
        
        flash('Borrow request approved successfully!', 'success')
        return redirect(url_for('my_books'))
        
    except Exception as e:
        print(f"Error in approve_borrow: {str(e)}")  # Debug print
        flash('An error occurred while approving the borrow request.', 'danger')
        return redirect(url_for('my_books'))

@app.route('/decline_borrow/<int:request_id>', methods=['POST'])
@login_required
def decline_borrow(request_id):
    try:
        conn = get_db_connection()
        
        # Get borrow request details
        request = conn.execute('''
            SELECT br.*, b.user_id as owner_id, b.title
            FROM BorrowRequests br
            JOIN Books b ON br.book_id = b.book_id
            WHERE br.request_id = ? AND br.status = 'pending'
        ''', (request_id,)).fetchone()
        
        if not request or request['owner_id'] != session['user_id']:
            flash('Invalid request or you do not have permission to decline it.', 'danger')
            conn.close()
            return redirect(url_for('my_books'))
            
        # Update borrow request status
        conn.execute('''
            UPDATE BorrowRequests 
            SET status = 'declined', 
                approval_date = datetime('now')
            WHERE request_id = ?
        ''', (request_id,))
        
        # Update book availability back to available
        conn.execute('''
            UPDATE Books 
            SET availability = 'available' 
            WHERE book_id = ?
        ''', (request['book_id'],))
        
        # Send notification message to borrower
        message_content = f"Your request to borrow '{request['title']}' has been declined."
        conn.execute('''
            INSERT INTO Messages (sender_id, receiver_id, content, timestamp)
            VALUES (?, ?, ?, datetime('now'))
        ''', (session['user_id'], request['borrower_id'], message_content))
        
        conn.commit()
        conn.close()
        
        flash('Borrow request declined successfully!', 'success')
        return redirect(url_for('my_books'))
        
    except Exception as e:
        print(f"Error in decline_borrow: {str(e)}")  # Debug print
        flash('An error occurred while declining the borrow request.', 'danger')
        return redirect(url_for('my_books'))

@app.route('/message_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def message_user(user_id):
    if request.method == 'POST':
        content = request.form.get('content')
        if not content:
            flash('Message cannot be empty.', 'danger')
            return redirect(url_for('message_user', user_id=user_id))
            
        try:
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO Messages (sender_id, receiver_id, content, timestamp)
                VALUES (?, ?, ?, datetime('now'))
            ''', (session['user_id'], user_id, content))
            conn.commit()
            conn.close()
            
            flash('Message sent successfully!', 'success')
            return redirect(url_for('view_book', book_id=request.args.get('book_id')))
            
        except Exception as e:
            flash('An error occurred while sending the message.', 'danger')
            return redirect(url_for('message_user', user_id=user_id))
    
    # Get user details for the message form
    conn = get_db_connection()
    user = conn.execute('SELECT name FROM Users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('home'))
        
    return render_template('message_user.html', user=user, user_id=user_id)

@app.route('/reserve_book/<int:book_id>', methods=['POST'])
@login_required
def reserve_book(book_id):
    try:
        conn = get_db_connection()
        
        # Check if book exists and is available
        book = conn.execute('''
            SELECT * FROM Books 
            WHERE book_id = ? AND user_id != ?
        ''', (book_id, session['user_id'])).fetchone()
        
        if not book:
            flash('Book not found or not available for reservation.', 'danger')
            return redirect(url_for('home'))
            
        # Check if book is already borrowed
        existing_borrow = conn.execute('''
            SELECT * FROM BorrowedBooks 
            WHERE book_id = ? AND return_date IS NULL
        ''', (book_id,)).fetchone()
        
        if existing_borrow:
            flash('This book is currently borrowed by someone else.', 'danger')
            return redirect(url_for('view_book', book_id=book_id))
            
        # Add reservation record
        conn.execute('''
            INSERT INTO Reservations (book_id, user_id, reservation_date, return_due_date, status)
            VALUES (?, ?, datetime('now'), datetime('now', '+14 days'), 'pending')
        ''', (book_id, session['user_id']))
        
        conn.commit()
        conn.close()
        
        flash('Book reserved successfully! The owner will be notified.', 'success')
        return redirect(url_for('my_books'))
        
    except Exception as e:
        flash('An error occurred while reserving the book.', 'danger')
        return redirect(url_for('view_book', book_id=book_id))

@app.route('/view_message/<int:message_id>')
@login_required
def view_message(message_id):
    conn = get_db_connection()
    
    # Get message details with sender/receiver information
    message = conn.execute('''
        SELECT m.*, 
               sender.name as sender_name, sender.profile_image as sender_image,
               receiver.name as receiver_name, receiver.profile_image as receiver_image
        FROM Messages m
        JOIN Users sender ON m.sender_id = sender.user_id
        JOIN Users receiver ON m.receiver_id = receiver.user_id
        WHERE m.message_id = ? AND (m.sender_id = ? OR m.receiver_id = ?)
    ''', (message_id, session['user_id'], session['user_id'])).fetchone()
    
    if not message:
        flash('Message not found or you do not have permission to view it.', 'danger')
        conn.close()
        return redirect(url_for('messages'))
    
    conn.close()
    return render_template('view_message.html', message=message)

@app.route('/return_book/<int:book_id>', methods=['POST'])
@login_required
def return_book(book_id):
    try:
        conn = get_db_connection()
        
        # Check if the book is currently borrowed by the current user
        borrowing = conn.execute('''
            SELECT * FROM BorrowedBooks 
            WHERE book_id = ? AND borrower_id = ? AND return_date IS NULL
        ''', (book_id, session['user_id'])).fetchone()
        
        if not borrowing:
            flash('Book not found or not currently borrowed by you.', 'danger')
            conn.close()
            return redirect(url_for('my_books'))
            
        # Update the return date
        conn.execute('''
            UPDATE BorrowedBooks 
            SET return_date = datetime('now')
            WHERE book_id = ? AND borrower_id = ? AND return_date IS NULL
        ''', (book_id, session['user_id']))
        
        # Update book availability back to available
        conn.execute('''
            UPDATE Books 
            SET availability = 'available'
            WHERE book_id = ?
        ''', (book_id,))
        
        # Send notification to the book owner
        book = conn.execute('SELECT title, user_id FROM Books WHERE book_id = ?', (book_id,)).fetchone()
        message_content = f"Your book '{book['title']}' has been returned by the borrower."
        conn.execute('''
            INSERT INTO Messages (sender_id, receiver_id, content, timestamp)
            VALUES (?, ?, ?, datetime('now'))
        ''', (session['user_id'], book['user_id'], message_content))
        
        conn.commit()
        conn.close()
        
        flash('Book returned successfully!', 'success')
        return redirect(url_for('my_books'))
        
    except Exception as e:
        print(f"Error in return_book: {str(e)}")  # Debug print
        flash('An error occurred while returning the book.', 'danger')
        return redirect(url_for('my_books'))

if __name__ == '__main__':
    app.run(debug=True)
