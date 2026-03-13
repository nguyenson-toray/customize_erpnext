#!/usr/bin/env python3
"""
Download @imgly/background-removal model files to serve locally.
Run once: python3 apps/customize_erpnext/customize_erpnext/scripts/download_imgly_models.py

After running, restart bench to publish assets:
  bench build --app customize_erpnext
  (or) bench --site <site> clear-cache
"""
import json, os, sys, urllib.request, time

VERSION   = '1.4.5'
SRC_BASE  = f'https://staticimgly.com/@imgly/background-removal-data/{VERSION}/dist/'
OUT_DIR   = os.path.join(os.path.dirname(__file__), '..', 'public', 'bg_removal')
OUT_DIR   = os.path.abspath(OUT_DIR)

os.makedirs(OUT_DIR, exist_ok=True)

def fetch_bytes(url, retries=3):
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
    }
    req = urllib.request.Request(url, headers=headers)
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            if i == retries - 1:
                raise
            print(f'  retry {i+1}: {e}')
            time.sleep(2)

# 1. Fetch resources.json
print('Fetching resources.json ...')
res_url  = SRC_BASE + 'resources.json'
res_data = fetch_bytes(res_url)
resources = json.loads(res_data)

# Save resources.json locally
with open(os.path.join(OUT_DIR, 'resources.json'), 'wb') as f:
    f.write(res_data)
print(f'Saved resources.json ({len(res_data)} bytes)')

# 2. Collect all unique chunk hashes
all_chunks = {}  # hash -> size (estimated)
for key, val in resources.items():
    for chunk in val.get('chunks', []):
        h    = chunk['hash']
        offs = chunk['offsets']
        size = offs[1] - offs[0] if len(offs) >= 2 else 0
        all_chunks[h] = size

print(f'\n{len(resources)} resources → {len(all_chunks)} unique chunks')
total_bytes = sum(all_chunks.values())
print(f'Estimated total: {total_bytes/1024/1024:.1f} MB\n')

# 3. Download each chunk
done = 0
skipped = 0
for i, (h, _) in enumerate(all_chunks.items(), 1):
    dest = os.path.join(OUT_DIR, h)
    if os.path.exists(dest):
        skipped += 1
        print(f'[{i:02d}/{len(all_chunks)}] skip (cached): {h[:16]}...')
        continue
    url  = SRC_BASE + h
    data = fetch_bytes(url)
    with open(dest, 'wb') as f:
        f.write(data)
    done += 1
    print(f'[{i:02d}/{len(all_chunks)}] downloaded {len(data)/1024/1024:.2f}MB: {h[:16]}...')

actual = sum(os.path.getsize(os.path.join(OUT_DIR, f))
             for f in os.listdir(OUT_DIR) if f != 'resources.json')
print(f'\nDone! {done} downloaded, {skipped} skipped.')
print(f'Total on disk: {actual/1024/1024:.1f} MB  →  {OUT_DIR}')
print()
print('Next step: rebuild assets so Frappe can serve them:')
print('  cd /home/frappe/frappe-bench && bench build --app customize_erpnext')
