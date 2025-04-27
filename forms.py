from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, SelectField, FileField, BooleanField, HiddenField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, ValidationError
import re

def validate_isbn_format(form, field):
    # Remove any hyphens or spaces from the ISBN
    isbn = re.sub(r'[-\s]', '', field.data)
    
    # Check if it's a valid ISBN-10 or ISBN-13
    if len(isbn) == 10:
        # ISBN-10 validation
        if not isbn[:-1].isdigit() or not (isbn[-1].isdigit() or isbn[-1].upper() == 'X'):
            raise ValidationError('Invalid ISBN-10 format')
    elif len(isbn) == 13:
        # ISBN-13 validation
        if not isbn.isdigit():
            raise ValidationError('Invalid ISBN-13 format')
    else:
        raise ValidationError('ISBN must be either 10 or 13 digits')

def validate_strong_password(form, field):
    password = field.data
    if len(password) < 8:
        raise ValidationError('Password must be at least 8 characters long')
    if not re.search(r'[A-Z]', password):
        raise ValidationError('Password must contain at least one uppercase letter')
    if not re.search(r'[a-z]', password):
        raise ValidationError('Password must contain at least one lowercase letter')
    if not re.search(r'\d', password):
        raise ValidationError('Password must contain at least one number')
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValidationError('Password must contain at least one special character')

class RegistrationForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[
        DataRequired(),
        validate_strong_password
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match.')
    ])
    location = StringField('Location', validators=[DataRequired(), Length(max=100)])
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class BookForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    author = StringField('Author', validators=[DataRequired(), Length(max=100)])
    isbn = StringField('ISBN', validators=[DataRequired(), validate_isbn_format])
    course_code = StringField('Course Code', validators=[DataRequired(), Length(max=20)])
    subject = SelectField('Subject', choices=[
        ('', 'Select a subject'),
        ('Computer Science', 'Computer Science'),
        ('Mathematics', 'Mathematics'),
        ('Physics', 'Physics'),
        ('Chemistry', 'Chemistry'),
        ('Biology', 'Biology'),
        ('Engineering', 'Engineering'),
        ('Business', 'Business'),
        ('Humanities', 'Humanities'),
    ], validators=[DataRequired()])
    condition = SelectField('Condition', choices=[
        ('', 'Select Condition'),
        ('New', 'New'),
        ('Like New', 'Like New'),
        ('Good', 'Good'),
        ('Fair', 'Fair'),
        ('Poor', 'Poor'),
    ], validators=[DataRequired()])
    submit = SubmitField('Add Book')

class ReviewForm(FlaskForm):
    rating = SelectField('Rating', choices=[
        ('', 'Select a rating'),
        ('5', '5 ★ - Excellent'),
        ('4', '4 ★ - Very Good'),
        ('3', '3 ★ - Good'),
        ('2', '2 ★ - Fair'),
        ('1', '1 ★ - Poor'),
    ], validators=[DataRequired()])
    comment = TextAreaField('Review Comment', validators=[DataRequired(), Length(max=1000)])
    submit = SubmitField('Submit Review')

class EditProfileForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=100)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    location = StringField('Location', validators=[DataRequired(), Length(max=100)])
    current_password = PasswordField('Current Password', validators=[Optional()])
    new_password = PasswordField('New Password', validators=[Optional(), validate_strong_password])
    confirm_password = PasswordField('Confirm New Password', validators=[Optional(), EqualTo('new_password', message='Passwords must match.')])
    profile_image = FileField('Profile Image', validators=[Optional()])
    submit = SubmitField('Update Profile')

class MessageForm(FlaskForm):
    recipient_id = HiddenField('Recipient', validators=[DataRequired()])
    content = StringField('Message', validators=[DataRequired(), Length(max=2000)])
    submit = SubmitField('Send')
