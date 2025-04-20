# Campus BookShare

Campus BookShare is a web application for university students to share, borrow, and review textbooks.

## Features

- User registration and authentication
- Browse, add, edit, and delete book listings
- Borrowing requests with notifications
- User profiles with ratings and reviews
- Messaging system for communication between users

## Getting Started

### Installation

1. Clone the repository:
2. Create and activate a virtual environment:
3. Install dependencies:
   pip install -r requirements.txt

### Environment Variables

Create a `.env` file in the root directory and set the following:

```env
SECRET_KEY=your_secret_key_here
```

### Database Setup

Database is provided.

### Running the Application

Start the Flask development server:

```bash
python app.py
```

## Usage

- Register a new account or log in
- Browse available books
- Add your own listings under "My Books"
- Send borrow requests and manage active loans
- Rate and review other users
- Chat with other members through the messaging interface