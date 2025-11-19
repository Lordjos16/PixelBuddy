import streamlit as st
import psutil
import platform
import shutil
import os
import re
import requests
from bs4 import BeautifulSoup
import html

try:
    import GPUtil
except ImportError:
    GPUtil = None

# -------------------- CPU & GPU Scoring --------------------
CPU_SCORE = {
    "pentium": 15, "celeron": 10,
    "i3": 30, "i5": 50, "i7": 70, "i9": 90,
    "ryzen 3": 30, "ryzen 5": 50, "ryzen 7": 70, "ryzen 9": 90,
    "amd fx": 40, "amd a": 25
}

GPU_SCORE = {
    "gtx 650": 20, "gtx 750": 25, "gtx 950": 30,
    "gtx 1050": 35, "gtx 1060": 50, "gtx 1070": 60, "gtx 1080": 70,
    "rtx 2060": 70, "rtx 2070": 75, "rtx 2080": 80,
    "rtx 3060": 85, "rtx 3070": 90, "rtx 3080": 95, "rtx 3090": 100, "rtx 4070": 100,
    "rx 560": 30, "rx 570": 40, "rx 580": 50, "rx 590": 55,
    "rx 5500": 60, "rx 5600": 65, "rx 5700": 70,
    "rx 6600": 80, "rx 6700": 85, "rx 6800": 90, "rx 6900": 95, "rx 7900": 100
}

def get_cpu_score(cpu_name):
    cpu_name = cpu_name.lower()
    for key in CPU_SCORE:
        if key in cpu_name:
            return CPU_SCORE[key]
    return 40

def get_gpu_score(gpu_name):
    gpu_name = gpu_name.lower()
    for key in GPU_SCORE:
        if key in gpu_name:
            return GPU_SCORE[key]
    return 50

# -------------------- System Specs --------------------
@st.cache_data
def get_total_disk_size():
    total = 0
    if platform.system() == "Windows":
        for drive_letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = f"{drive_letter}:/"
            if os.path.exists(drive):
                try:
                    total += shutil.disk_usage(drive).total
                except:
                    pass
    else:
        total += shutil.disk_usage("/").total
    return round(total / (1024**3), 2)

@st.cache_data
def get_system_specs():
    specs = {}
    specs["OS"] = platform.system() + " " + platform.release()
    specs["CPU"] = platform.processor()
    specs["CPU Architecture"] = platform.machine()
    specs["RAM (GB)"] = round(psutil.virtual_memory().total / (1024 ** 3), 2)
    if GPUtil:
        gpus = GPUtil.getGPUs()
        if gpus:
            best = max(gpus, key=lambda g: g.memoryTotal)
            specs["GPU"] = best.name
            specs["VRAM (MB)"] = best.memoryTotal
        else:
            specs["GPU"] = "Unknown"
            specs["VRAM (MB)"] = 0
    else:
        specs["GPU"] = "Unknown"
        specs["VRAM (MB)"] = 0
    specs["Disk (GB)"] = get_total_disk_size()
    return specs

# -------------------- Steam Search --------------------
def search_steam(query, max_results=5):
    url = f'https://store.steampowered.com/search/?term={query}&l=english'
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    results = []
    rows = soup.select('a.search_result_row')[:max_results]
    for row in rows:
        title = row.select_one('.title').text.strip()
        href = row['href']
        appid_match = re.search(r'/app/(\d+)', href)
        if appid_match:
            appid = appid_match.group(1)
            results.append({'name': title, 'appid': appid, 'url': href})
    return results

def parse_requirements(html_text):
    if not html_text:
        return None
    soup = BeautifulSoup(html_text, "html.parser")
    categories = ["OS", "Processor", "Memory", "Graphics", "Storage", "Sound Card", "Additional Notes", "Other requirements"]
    data = {cat: "" for cat in categories}
    
    for li in soup.find_all("li"):
        text = li.get_text(" ", strip=True)
        for cat in categories:
            if re.match(fr"{cat}[:\s]", text, re.I):
                
                content = re.sub(fr"{cat}[:\s]*", "", text, flags=re.I).strip()
                data[cat] = content
                break
        else:
         
            if data["Additional Notes"]:
                data["Additional Notes"] += " | " + text
            else:
                data["Additional Notes"] = text
    
    
    if not any(data.values()):
        all_text = " ".join(soup.stripped_strings)
        data["Additional Notes"] = all_text
    
    return data

# -------------------- Fetch System Requirements --------------------
def fetch_steam_requirements(appid):
    min_text = rec_text = None
    try:
        api_url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=english"
        resp = requests.get(api_url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        app_data = data.get(str(appid), {}).get("data", {})
        pc_reqs = app_data.get("pc_requirements", {})
        min_html = pc_reqs.get("minimum", "")
        rec_html = pc_reqs.get("recommended", "")
        min_text = parse_requirements(html.unescape(min_html))
        rec_text = parse_requirements(html.unescape(rec_html))
        return {"minimum": min_text, "recommended": rec_text}
    except Exception as e:
        print("Steam API error:", e)
        return {"minimum": None, "recommended": None}

# -------------------- Compare Specs --------------------
def compare_specs(user_specs, req_text):
    if not req_text:
        return {'can_meet': False, 'notes': [], 'score': 0}
    txt = " ".join(req_text.values()).lower()
    notes, score, can_meet = [], 0, True

    ram_match = re.search(r'(\d+)\s*gb\s*ram', txt)
    if ram_match:
        req_ram = int(ram_match.group(1))
        ram_ratio = user_specs['RAM (GB)']/req_ram
        if ram_ratio <1:
            can_meet=False
            notes.append(f'RAM too low: {user_specs["RAM (GB)"]} GB < {req_ram} GB')
        score += min(ram_ratio,1)*25

    vram_match = re.search(r'(\d+)\s*gb\s*(?:vram|video memory|graphics)', txt)
    if vram_match:
        req_vram = int(vram_match.group(1))
        vram_ratio = user_specs['VRAM (MB)']/req_vram/1024
        if vram_ratio <1:
            can_meet=False
            notes.append(f'VRAM too low: {user_specs["VRAM (MB)"]} MB < {req_vram*1024} MB')
        score += min(vram_ratio,1)*25

    cpu_match = re.search(r'(intel|amd).*(i\d|ryzen\s\d|fx|pentium|celeron)', txt)
    if cpu_match:
        req_cpu = cpu_match.group()
        req_score = get_cpu_score(req_cpu)
        user_score = get_cpu_score(user_specs.get("CPU","i5"))
        cpu_ratio = user_score / req_score
        if cpu_ratio <1:
            can_meet=False
            notes.append(f'CPU may be insufficient: {user_specs.get("CPU")} < {req_cpu}')
        score += min(cpu_ratio,1)*25

    gpu_match = re.search(r'(gtx|rtx|rx).*(\d+)', txt)
    if gpu_match:
        req_gpu = gpu_match.group()
        req_score = get_gpu_score(req_gpu)
        user_score = get_gpu_score(user_specs.get("GPU","gtx 1050"))
        gpu_ratio = user_score / req_score
        if gpu_ratio <1:
            can_meet=False
            notes.append(f'GPU may be insufficient: {user_specs.get("GPU")} < {req_gpu}')
        score += min(gpu_ratio,1)*25

    return {'can_meet': can_meet, 'notes': notes, 'score': min(score,100)}

# -------------------- Graphics & FPS --------------------
def estimate_graphics_level(score):
    if score <= 25:
        return 'Cannot run', 0
    elif 26 <= score <= 50:
        return 'Low', 40
    elif 51 <= score <= 75:
        return 'Medium', 60
    elif 76 <= score <= 100:
        return 'High/Ultra', 90
    else:
        return 'Low', 40

def graphics_badge(level):
    return {'Cannot run':'❌ Cannot Run','Low':'🐢 Low','Medium':'⚡ Medium','High/Ultra':'🚀 High/Ultra'}.get(level,level)

# -------------------- Streamlit UI --------------------
st.set_page_config(page_title='PixelBuddy', layout='wide')
st.title('🎮 PixelBuddy — Steam PC Compatibility Checker')

user_specs = get_system_specs()
st.subheader('💻 Your System Specs')
cols = st.columns(3)
for i,(k,v) in enumerate(user_specs.items()):
    cols[i%3].metric(label=k,value=v)

query = st.text_input('Enter Steam game name:')
if query:
    steam_results = search_steam(query)
    if not steam_results:
        st.warning('No Steam results found.')
    else:
        st.subheader('🔍 Steam Top Results')
        for idx, app in enumerate(steam_results):
            st.write(f"{idx+1}. {app['name']}")

        choice = st.number_input('Select a game number:', min_value=1, max_value=len(steam_results), step=1)
        with st.form(key='check_form'):
            submit_button = st.form_submit_button('Check Compatibility')
            if submit_button:
                selected_app = steam_results[choice-1]
                reqs = fetch_steam_requirements(selected_app['appid'])
                if not reqs["minimum"] and not reqs["recommended"]:
                    st.write("⚠ System requirements not available.")
                else:
                    comp_min = compare_specs(user_specs, reqs["minimum"] or reqs["recommended"])
                    comp_rec = compare_specs(user_specs, reqs["recommended"] or reqs["minimum"])
                    score = (comp_min['score'] + comp_rec['score'])//2
                    graphics, fps = estimate_graphics_level(score)

                    st.subheader(f'📝 {selected_app["name"]} Compatibility')
                    st.write(f"**Can Run:** {'✅ Yes' if comp_min['can_meet'] else '❌ No'}")
                    st.write(f"**Estimated Graphics Level:** {graphics_badge(graphics)}")
                    st.write(f"**Estimated FPS:** ~{fps} FPS")
                    st.progress(min(fps/120,1.0))
                    if comp_min['notes']:
                        st.write("**⚠ Notes:**")
                        for note in comp_min['notes']:
                            st.write(f"- {note}")

                    st.subheader("📜 System Requirements from Steam (Table)")
                    if reqs["minimum"]:
                        st.write("**Minimum Requirements:**")
                        st.table(reqs["minimum"])
                    if reqs["recommended"]:
                        st.write("**Recommended Requirements:**")
                        st.table(reqs["recommended"])
