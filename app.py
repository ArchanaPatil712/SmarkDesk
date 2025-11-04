import os
import smtplib
from flask_basicauth import BasicAuth
from email.message import EmailMessage
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import datetime

# --- SETUP: Hardcoded credentials ---
SENDER_EMAIL = "patilarchana1911@gmail.com"
SENDER_PASSWORD = "eavawktcnwolnvvd"  # PASTE YOUR 16-LETTER CODE

# --- App & Database Configuration ---
app = Flask(__name__)
CORS(app)

# Database Config: This creates a file named 'queries.db' in your project folder
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///queries.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
# --- Basic Auth (Password) Configuration ---
app.config['BASIC_AUTH_USERNAME'] = 'admin'
app.config['BASIC_AUTH_PASSWORD'] = 'password'  # You can change this
basic_auth = BasicAuth(app)


# --- Database Model ---
class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(20), unique=True, nullable=False)
    user_email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    department = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='New')
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f'<Ticket {self.ticket_id}>'
    
    # Helper function to turn a ticket into a dictionary (for JSON)
    def to_dict(self):
        return {
            'id': self.id,
            'ticket_id': self.ticket_id,
            'user_email': self.user_email,
            'subject': self.subject,
            'body': self.body,
            'department': self.department,
            'status': self.status,
            'created_at': self.created_at.isoformat()
        }


# --- Email & Routing Logic (same as before) ---
DEPARTMENT_ROUTING_RULES = {
    'Admissions': ['admission', 'apply', 'application', 'enrollment', 'prospectus'],
    'Finance': ['fees', 'payment', 'scholarship', 'invoice', 'billing', 'refund', 'finance'],
    'Academics': ['exam', 'grades', 'transcript', 'courses', 'classes', 'syllabus'],
    'IT Support': ['wifi', 'password', 'login', 'email', 'software', 'computer'],
    'Library': ['books', 'journal', 'borrow', 'return', 'library card']
}
DEFAULT_DEPARTMENT = 'General Inquiries'
DEPARTMENT_EMAILS = {
    'Admissions': 'admissions@yourcollege.com',
    'Finance': 'patilarchana1911@gmail.com',  # We'll keep this for testing
    'Academics': 'academics@yourcollege.com',
    'IT Support': 'it.support@yourcollege.com',
    'Library': 'library@yourcollege.com',
    'General Inquiries': 'help@yourcollege.com'
}

def categorize_query(query_text):
    if query_text:
        query_text = query_text.lower()
        for department, keywords in DEPARTMENT_ROUTING_RULES.items():
            if any(keyword in query_text for keyword in keywords):
                return department
    return DEFAULT_DEPARTMENT

def send_email(recipient_email, subject, body):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient_email
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
            smtp.send_message(msg)
    except Exception as e:
        print(f"🔴 ERROR: Failed to send email to {recipient_email}. Reason: {e}")


# --- UPDATED Query Submission Route ---
@app.route('/submit-query', methods=['POST'])
def handle_query():
    data = request.json
    user_email = data.get('email')
    subject = data.get('subject')
    body = data.get('body')

    if not all([user_email, subject, body]):
        return jsonify({'error': 'Missing required fields'}), 400

    target_department = categorize_query(body)
    target_email = DEPARTMENT_EMAILS[target_department]
    ticket_id = f'TICKET-{hex(hash(body))[-8:]}'

    # --- NEW: Save to Database ---
    try:
        new_ticket = Ticket(
            ticket_id=ticket_id,
            user_email=user_email,
            subject=subject,
            body=body,
            department=target_department
        )
        db.session.add(new_ticket)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"🔴 ERROR: Database save failed. Reason: {e}")
        return jsonify({'error': 'Failed to save ticket.'}), 500
    # --- End of New DB Code ---

    # --- Send Emails (same as before) ---
    dept_subject = f"New Query from {user_email}: {subject} [{ticket_id}]"
    dept_body = f"A new query has been routed to your department.\n\nFrom: {user_email}\nSubject: {subject}\n\nQuery:\n---\n{body}\n---"
    send_email(target_email, dept_subject, dept_body)

    user_subject = f"Query Received: Your Ticket ID is {ticket_id}"
    user_body = f"Hello,\n\nThank you for contacting us. We have received your query and routed it to the {target_department}.\n\nYour Ticket ID is: {ticket_id}"
    send_email(user_email, user_subject, user_body)
    
    response_data = {
        'message': 'Your query has been received and routed successfully!',
        'ticket_id': ticket_id,
        'routed_to': target_department
    }
    return jsonify(response_data), 200


# --- NEW: Admin Dashboard Routes ---

# This route serves the HTML page for the admin dashboard

@app.route('/admin')
@basic_auth.required
def admin_dashboard():
    # Renders an HTML file we will create called 'admin.html'
    return render_template('admin.html')

# This route provides the ticket data (as JSON) to the dashboard's JavaScript
@app.route('/api/tickets')
def get_tickets():
    try:
        tickets = Ticket.query.order_by(Ticket.created_at.desc()).all()
        # Convert all ticket objects to dictionaries
        return jsonify([ticket.to_dict() for ticket in tickets])
    except Exception as e:
        print(f"🔴 ERROR: Could not fetch tickets. Reason: {e}")
        return jsonify({"error": "Failed to fetch tickets"}), 500

# --- NEW: Route to Update Ticket Status ---
@app.route('/api/ticket/<int:ticket_db_id>/status', methods=['POST'])
def update_ticket_status(ticket_db_id):
    try:
        # Get the new status from the request
        data = request.json
        new_status = data.get('status')
        
        if not new_status or new_status not in ['New', 'In Progress', 'Resolved']:
            return jsonify({'error': 'Missing or invalid status'}), 400

        # Find the ticket in the database by its primary key (id)
        ticket = Ticket.query.get(ticket_db_id)
        
        if not ticket:
            return jsonify({'error': 'Ticket not found'}), 404
        
        # Update the status and save to the database
        ticket.status = new_status
        db.session.commit()
        
        # Return the updated ticket data
        return jsonify(ticket.to_dict())

    except Exception as e:
        db.session.rollback()
        print(f"🔴 ERROR: Could not update status. Reason: {e}")
        return jsonify({"error": "Failed to update status"}), 500
    
# --- NEW: User Ticket Lookup Routes ---

# 1. This route serves the HTML page for users to check their ticket
@app.route('/check-ticket')
def check_ticket_page():
    # This will render a new file we are about to create
    return render_template('ticket.html')

# 2. This API route finds the ticket in the database and returns its status
@app.route('/api/ticket/status/<string:ticket_id_str>')
def get_ticket_status(ticket_id_str):
    try:
        # Find the ticket by its public-facing TICKET-ID
        ticket = Ticket.query.filter_by(ticket_id=ticket_id_str).first()
        
        if not ticket:
            # If not found, return a 404 error
            return jsonify({'error': 'Ticket not found'}), 404
        
        # If found, return the relevant, safe information
        return jsonify({
            'ticket_id': ticket.ticket_id,
            'subject': ticket.subject,
            'status': ticket.status,
            'created_at': ticket.created_at.isoformat()
        })

    except Exception as e:
        print(f"🔴 ERROR: Could not find ticket. Reason: {e}")
        return jsonify({"error": "Failed to find ticket"}), 500
# To run the app
if __name__ == '__main__':
    # This block will run only once when you start the app
    with app.app_context():
        # This command creates the 'queries.db' file and all the tables
        db.create_all()
    app.run(debug=True, port=5000)