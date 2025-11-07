import os
import smtplib
import uuid
import datetime
from email.message import EmailMessage
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_basicauth import BasicAuth

# --- SETUP: Hardcoded credentials ---
SENDER_EMAIL = "patilarchana1911@gmail.com"
SENDER_PASSWORD = "eavawktcnwolnvvd"

# --- App & Database Configuration ---
app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///queries.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Basic Auth (Password) Configuration ---
app.config['BASIC_AUTH_USERNAME'] = 'admin'
app.config['BASIC_AUTH_PASSWORD'] = 'password' # You can change this
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

# --- Email & Routing Logic ---
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
    'Finance': 'patilarchana1911@gmail.com',  # Changed for testing
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

# --- 1. User Query Submission Route ---
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
    ticket_id = f'TICKET-{str(uuid.uuid4())[:8]}'

    # Save to Database
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

    # Send Emails
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

# --- 2. Admin Dashboard Routes ---
@app.route('/admin')
@basic_auth.required  # <-- Password lock is ON
def admin_dashboard():
    return render_template('admin.html')

@app.route('/api/tickets')
# No password lock here, so JavaScript can fetch
def get_tickets():
    try:
        tickets = Ticket.query.order_by(Ticket.created_at.desc()).all()
        return jsonify([ticket.to_dict() for ticket in tickets])
    except Exception as e:
        print(f"🔴 ERROR: Could not fetch tickets. Reason: {e}")
        return jsonify({"error": "Failed to fetch tickets"}), 500

@app.route('/api/ticket/<int:ticket_db_id>/status', methods=['POST'])
# No password lock here, so JavaScript can fetch
@app.route('/api/ticket/<int:ticket_db_id>/status', methods=['POST'])
# No password lock here, so JavaScript can fetch
def update_ticket_status(ticket_db_id):
    try:
        data = request.json
        new_status = data.get('status')
        
        if not new_status or new_status not in ['New', 'In Progress', 'Resolved']:
            return jsonify({'error': 'Missing or invalid status'}), 400

        ticket = Ticket.query.get(ticket_db_id)
        
        if not ticket:
            return jsonify({'error': 'Ticket not found'}), 404
        
        # Don't send an email if the status isn't actually changing
        if ticket.status == new_status:
            return jsonify(ticket.to_dict())
            
        # Update the status in the database
        ticket.status = new_status
        db.session.commit()
        
        # --- NEW: Notify the user by email ---
        print(f"✅ Status changed. Sending notification to {ticket.user_email}...")
        
        user_subject = f"Update on your ticket: {ticket.ticket_id}"
        user_body = (
            f"Hello,\n\n"
            f"This is an update on your query (Ticket ID: {ticket.ticket_id}).\n"
            f"Your ticket status has been changed to: {new_status}\n\n"
        )
        
        if new_status == 'Resolved':
            user_body += "Your query is now considered resolved. If you have any further questions, please feel free to submit a new query.\n\n"
        
        user_body += "Best regards,\nAutomated Helpdesk"
        
        # Call the same email function we already built
        send_email(ticket.user_email, user_subject, user_body)
        # --- END OF NEW LOGIC ---

        return jsonify(ticket.to_dict())

    except Exception as e:
        db.session.rollback()
        print(f"🔴 ERROR: Could not update status. Reason: {e}")
        return jsonify({"error": "Failed to update status"}), 500

# --- 3. User Ticket Lookup Routes ---
@app.route('/check-ticket')
def check_ticket_page():
    return render_template('ticket.html')

@app.route('/api/ticket/status/<string:ticket_id_str>')
def get_ticket_status(ticket_id_str):
    try:
        ticket = Ticket.query.filter_by(ticket_id=ticket_id_str).first()
        
        if not ticket:
            return jsonify({'error': 'Ticket not found'}), 404
        
        return jsonify({
            'ticket_id': ticket.ticket_id,
            'subject': ticket.subject,
            'status': ticket.status,
            'created_at': ticket.created_at.isoformat()
        })
    except Exception as e:
        print(f"🔴 ERROR: Could not find ticket. Reason: {e}")
        return jsonify({"error": "Failed to find ticket"}), 500
# --- NEW: Route to Send a Reply to the User ---
@app.route('/api/ticket/<int:ticket_db_id>/reply', methods=['POST'])
def send_reply_to_user(ticket_db_id):
    try:
        data = request.json
        reply_text = data.get('reply_text')
        
        if not reply_text:
            return jsonify({'error': 'Reply text is missing'}), 400

        ticket = Ticket.query.get(ticket_db_id)
        if not ticket:
            return jsonify({'error': 'Ticket not found'}), 404
        
        # 1. Send the reply email to the user
        user_subject = f"Solution for your ticket: {ticket.ticket_id}"
        user_body = (
            f"Hello,\n\n"
            f"Here is the solution for your query regarding '{ticket.subject}':\n\n"
            f"--- Solution ---\n"
            f"{reply_text}\n"
            f"----------------\n\n"
            f"This query is now considered resolved.\n\n"
            f"Best regards,\nHelpdesk Team"
        )
        send_email(ticket.user_email, user_subject, user_body)

        # 2. Update the ticket status to 'Resolved'
        ticket.status = 'Resolved'
        db.session.commit()
        
        print(f"✅ Reply sent to {ticket.user_email} and ticket marked as Resolved.")
        
        return jsonify(ticket.to_dict())

    except Exception as e:
        db.session.rollback()
        print(f"🔴 ERROR: Could not send reply. Reason: {e}")
        return jsonify({"error": "Failed to send reply"}), 500
# --- Run the App ---
if __name__ == '__main__':
    with app.app_context():
        # This creates the 'queries.db' file and all tables
        db.create_all()
    app.run(debug=True, port=5000)
