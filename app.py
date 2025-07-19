from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
socketio = SocketIO(app)

# Store active users and rooms
users = {}
rooms = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_rooms')
def get_rooms():
    return jsonify([
        {
            'name': room,
            'creator': info['creator'],
            'created_at': info['created_at'],
            'user_count': len(info['users']),
            'is_protected': bool(info.get('password'))
        }
        for room, info in rooms.items()
    ])

def remove_user_from_room(sid, room_name):
    if room_name in rooms:
        username = users.get(sid, 'Anonymous')
        # If the user is the creator, delete the room and notify all
        if username == rooms[room_name]['creator']:
            emit('room_deleted', {'room': room_name}, room=room_name)
            # Remove all users from the room
            for user_sid in list(rooms[room_name]['users']):
                leave_room(room_name, sid=user_sid)
            del rooms[room_name]
        else:
            rooms[room_name]['users'].remove(sid)
            emit('user_left', {'username': username}, room=room_name)
            # Remove room if empty
            if not rooms[room_name]['users']:
                del rooms[room_name]
                emit('room_deleted', {'room': room_name}, broadcast=True)

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    for room_name in list(rooms.keys()):
        if sid in rooms[room_name]['users']:
            remove_user_from_room(sid, room_name)
    users.pop(sid, None)
    print('Client disconnected')

@socketio.on('create_room')
def handle_create_room(data):
    username = data['username']
    room = data['room']
    password = data.get('password')

    if room in rooms:
        emit('error', {
            'message': 'Room already exists',
            'type': 'create_error'
        })
        return False

    rooms[room] = {
        'creator': username,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'users': {request.sid},
        'password': generate_password_hash(password) if password else None
    }

    join_room(room)
    users[request.sid] = username

    # Notify all clients about the new room
    emit('new_room_created', {
        'room': room,
        'creator': username,
        'created_at': rooms[room]['created_at'],
        'is_protected': bool(password)
    }, broadcast=True)

    emit('user_joined', {
        'username': username,
        'room': room,
        'creator': username,
        'user_count': 1
    }, room=room)
    return True

@socketio.on('join')
def handle_join(data):
    username = data['username']
    room = data['room']
    password = data.get('password')

    if room not in rooms:
        emit('error', {'message': 'Room does not exist', 'type': 'join_error'})
        return False

    room_info = rooms[room]
    if room_info.get('password'):
        if not password:
            emit('error', {'message': 'This room requires a password', 'type': 'password_required'})
            return False
        if not check_password_hash(room_info['password'], password):
            emit('error', {'message': 'Invalid password', 'type': 'invalid_password'})
            return False

    join_room(room)
    users[request.sid] = username
    room_info['users'].add(request.sid)
    
    emit('user_joined', {
        'username': username,
        'room': room,
        'creator': room_info['creator'],
        'user_count': len(room_info['users'])
    }, room=room)
    return True

@socketio.on('leave')
def handle_leave(data):
    room = data['room']
    leave_room(room)
    remove_user_from_room(request.sid, room)

@socketio.on('message')
def handle_message(data):
    emit('message', {
        'username': users.get(request.sid, 'Anonymous'),
        'message': data['message'],
        'timestamp': datetime.now().strftime('%H:%M:%S')
    }, room=data['room'])

if __name__ == '__main__':
    socketio.run(app, debug=True)