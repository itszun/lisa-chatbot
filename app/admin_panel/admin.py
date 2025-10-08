import os
from flask_admin import Admin
from flask_pymongo import PyMongo

from flask_admin.contrib.pymongo import ModelView 



from wtforms import Form, StringField, TextAreaField
from wtforms.validators import DataRequired

class ChatHistoryForm(Form):
    SessionId = StringField('ID Sesi', validators=[DataRequired()])
    History = TextAreaField('Data History (JSON String)', validators=[DataRequired()])

class UserSessionForm(Form):
    chat_user_id = StringField('Chat User ID', validators=[DataRequired()])
    session_id = StringField('UUID Sesi', validators=[DataRequired()])
    SessionId = StringField('Session ID Gabungan', validators=[DataRequired()])
    title = StringField('Judul Sesi', validators=[DataRequired()])
    
from flask_admin.contrib.pymongo import ModelView 
class CustomChatHistoryView(ModelView):
    form = ChatHistoryForm 
    
    column_list = ('SessionId', 'History', '_id') 
    column_searchable_list = ('SessionId',)

    column_formatters = {
        'History': lambda v, c, m, n: f"[{m.get('SessionId', 'N/A')}]: {m.get('History', 'Tidak Ada Konten')[:50]}..."
    }

class UserSessionView(ModelView):
    form = UserSessionForm 
    
    column_list = (
        'title', 
        'SessionId', 
        'chat_user_id', 
        'created_at', 
        '_id'
    )
    
    column_labels = {
        'chat_user_id': 'User ID Chat',
        'session_id': 'UUID Sesi',
        'SessionId': 'ID Sesi Gabungan',
        'title': 'Judul Sesi',
        'created_at': 'Dibuat Pada'
    }
    
    column_searchable_list = ('SessionId', 'chat_user_id', 'title')
    
    form_excluded_columns = ('_id',) 

def init_admin(app):
    """Fungsi untuk inisialisasi dan registrasi Admin Panel."""

    app.config["MONGO_URI"] = os.environ.get("MONGO_URI") 
    print("INIT ADMIN")
    print(os.environ.get("MONGO_URI"))
    
    mongo = PyMongo(app) 

    print(mongo.db)
    
    admin = Admin(app, name='WIKA System Admin', template_mode='bootstrap4')

    
    admin.add_view(CustomChatHistoryView(
        mongo.db.chat_histories,
        name='Chat History'
    ))

    admin.add_view(UserSessionView(
        mongo.db.user_session,
        name='User Sessions'
    ))

    return mongo 
