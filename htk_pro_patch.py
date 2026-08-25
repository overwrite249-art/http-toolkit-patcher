r"""
HTTP Toolkit patcher.

Run without arguments. Locates the installation, applies the patch,
relaunches the application. Original files are backed up next to the
installation (.clean.bak). To revert, delete the patched files and
rename the backups back.
"""
import struct, json, hashlib, os, sys, shutil, subprocess, time

SEARCH_DIRS = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "HTTP Toolkit"),
    os.path.join(os.environ.get("PROGRAMFILES", ""), "HTTP Toolkit"),
    os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "HTTP Toolkit"),
]

PRELOAD_PATCHED = r'''"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function (o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
const electron = __importStar(require("electron"));
const { contextBridge, ipcRenderer: { invoke: ipcInvoke }, webUtils, webFrame } = electron;

/**
 * Local shell enhancement layer.
 * Evaluates in the main world before any remote page script runs.
 */
const PRO_HOOK = `(function(){
  if (window.__htkProHooked) return;
  window.__htkProHooked = true;
  var B64U = {
    enc: function(obj){
      return btoa(JSON.stringify(obj)).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,'');
    },
    dec: function(s){
      s = s.replace(/-/g,'+').replace(/_/g,'/');
      while (s.length % 4) s += '=';
      return JSON.parse(atob(s));
    }
  };
  try {
    var subtle = window.crypto.subtle;
    if (subtle && !subtle.__sig) {
      subtle.verify = function(){ return Promise.resolve(true); };
      subtle.__sig = true;
    }
  } catch (e) {}
  var YEAR = 365*24*3600*1000;
  var PRO_FIELDS = {
    subscription_sku: 'pro-annual',
    subscription_status: 'active',
    subscription_expiry: new Date(Date.now() + 10*YEAR).toISOString(),
    subscription_quantity: 1,
    can_manage_subscription: false
  };
  function forge(){
    var head = B64U.enc({alg:'RS256', typ:'JWT', kid:'httptoolkey-1'});
    var body = B64U.enc(Object.assign({
      iss: 'https://httptoolkit.tech/',
      aud: 'https://httptoolkit.tech/app_data',
      iat: Math.floor(Date.now()/1000) - 60,
      exp: Math.floor((Date.now() + 10*YEAR)/1000),
      user_id: 'email|pro-local',
      email: 'pro@localhost.local',
      feature_flags: [],
      banned: false
    }, PRO_FIELDS));
    return head + '.' + body + '.' + 'c2lnbmF0dXJl';
  }
  var origGet = localStorage.getItem.bind(localStorage);
  localStorage.getItem = function(k){
    if (k === 'last_jwt') return origGet('last_jwt') || forge();
    return origGet(k);
  };
  function rewrite(token){
    try {
      var parts = token.split('.');
      if (parts.length !== 3) return token;
      var payload = B64U.dec(parts[1]);
      if (!payload || typeof payload !== 'object') return token;
      Object.assign(payload, PRO_FIELDS);
      delete payload.team_subscription;
      parts[1] = B64U.enc(payload);
      return parts.join('.');
    } catch (e) { return token; }
  }
  var origFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = function(input, init){
    return Promise.resolve(origFetch(input, init)).then(function(resp){
      try {
        var url = typeof input === 'string' ? input : (input && input.url) || '';
        if (/get-(app|billing)-data/.test(url) && resp.ok) {
          return resp.clone().text().then(function(text){
            var t = text.trim();
            if (/^[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]*$/.test(t)) {
              var headers = new Headers(resp.headers);
              return new Response(rewrite(t), {status: resp.status, statusText: resp.statusText, headers: headers});
            }
            return resp;
          });
        }
      } catch (e) {}
      return resp;
    });
  };
})();`;

try {
    if (webFrame && webFrame.executeJavaScript) {
        [0, 50, 250, 1000].forEach((delay) => {
            setTimeout(() => {
                webFrame.executeJavaScript(PRO_HOOK).catch(() => { });
            }, delay);
        });
    }
} catch (e) { }

// --- Original HTTP Toolkit Logic ---
let desktopVersion;
let authToken;
let deviceInfo;
const preloadPromise = Promise.all([
    ipcInvoke('get-desktop-version').then(result => { desktopVersion = result; }),
    ipcInvoke('get-server-auth-token').then(result => { authToken = result; }),
    Promise.race([
        ipcInvoke('get-device-info').then(result => { deviceInfo = result; }),
        new Promise((resolve) => setTimeout(resolve, 500))
    ])
]);

contextBridge.exposeInMainWorld('desktopApi', {
    waitUntilDesktopApiReady: () => preloadPromise.then(() => { }),
    getDesktopVersion: () => desktopVersion,
    getServerAuthToken: () => authToken,
    getDeviceInfo: () => deviceInfo,
    selectApplication: () => ipcInvoke('select-application'),
    selectFilePath: () => ipcInvoke('select-file-path'),
    selectSaveFilePath: () => ipcInvoke('select-save-file-path'),
    openContextMenu: (options) => ipcInvoke('open-context-menu', options),
    restartApp: () => ipcInvoke('restart-app'),
    getPathForFile: (file) => webUtils.getPathForFile(file) || null
});
'''

HOOK_JS = r'''
(function(){
  if (window.__htkProHooked) return;
  window.__htkProHooked = true;
  var B64U = {
    enc: function(obj){
      return btoa(JSON.stringify(obj)).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,'');
    },
    dec: function(s){
      s = s.replace(/-/g,'+').replace(/_/g,'/');
      while (s.length % 4) s += '=';
      return JSON.parse(atob(s));
    }
  };
  try {
    var subtle = window.crypto.subtle;
    if (subtle && !subtle.__sig) {
      subtle.verify = function(){ return Promise.resolve(true); };
      subtle.__sig = true;
    }
  } catch (e) {}
  var YEAR = 365*24*3600*1000;
  var PRO_FIELDS = {
    subscription_sku: 'pro-annual',
    subscription_status: 'active',
    subscription_expiry: new Date(Date.now() + 10*YEAR).toISOString(),
    subscription_quantity: 1,
    can_manage_subscription: false
  };
  function forge(){
    var head = B64U.enc({alg:'RS256', typ:'JWT', kid:'httptoolkey-1'});
    var body = B64U.enc(Object.assign({
      iss: 'https://httptoolkit.tech/',
      aud: 'https://httptoolkit.tech/app_data',
      iat: Math.floor(Date.now()/1000) - 60,
      exp: Math.floor((Date.now() + 10*YEAR)/1000),
      user_id: 'email|pro-local',
      email: 'pro@localhost.local',
      feature_flags: [],
      banned: false
    }, PRO_FIELDS));
    return head + '.' + body + '.' + 'c2lnbmF0dXJl';
  }
  var origGet = localStorage.getItem.bind(localStorage);
  localStorage.getItem = function(k){
    if (k === 'last_jwt') { var real = origGet('last_jwt'); return real || forge(); }
    return origGet(k);
  };
  function rewrite(token){
    try {
      var parts = token.split('.');
      if (parts.length !== 3) return token;
      var payload = B64U.dec(parts[1]);
      if (!payload || typeof payload !== 'object') return token;
      Object.assign(payload, PRO_FIELDS);
      delete payload.team_subscription;
      parts[1] = B64U.enc(payload);
      return parts.join('.');
    } catch (e) { return token; }
  }
  var origFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = function(input, init){
    var p = origFetch ? origFetch(input, init) : Promise.reject(new Error('no fetch'));
    return p.then(function(resp){
      try {
        var url = typeof input === 'string' ? input : (input && input.url) || '';
        if (/get-(app|billing)-data/.test(url) && resp.ok) {
          return resp.clone().text().then(function(text){
            var t = text.trim();
            if (/^[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]*$/.test(t)) {
              var headers = new Headers(resp.headers);
              return new Response(rewrite(t), {status: resp.status, statusText: resp.statusText, headers: headers});
            }
            return resp;
          });
        }
      } catch (e) {}
      return resp;
    });
  };
})();'''

ANCHOR_CREATEWINDOW = "const createWindow = (logStream) => {"
ANCHOR_AUTHTOKEN = "            injectValue('httpToolkitAuthToken', AUTH_TOKEN);"


def find_install():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    candidates = []
    for a in args:
        p = a.strip('"')
        if os.path.exists(os.path.join(p, "HTTP Toolkit.exe")):
            candidates.append(p)
        elif os.path.basename(p) == "HTTP Toolkit.exe":
            candidates.append(os.path.dirname(p))
    for d in SEARCH_DIRS:
        if d and os.path.exists(os.path.join(d, "HTTP Toolkit.exe")):
            candidates.append(d)
    return candidates[0] if candidates else None


def kill_all():
    subprocess.run(["taskkill", "/F", "/IM", "HTTP Toolkit.exe"],
                   capture_output=True, timeout=20)
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-NetTCPConnection -LocalPort 45457 -ErrorAction SilentlyContinue "
             "| Select-Object -ExpandProperty OwningProcess -Unique) -join ' '"],
            capture_output=True, text=True, timeout=25)
        for pid_s in out.stdout.split():
            if pid_s.strip().isdigit():
                subprocess.run(["taskkill", "/F", "/PID", pid_s.strip()],
                               capture_output=True, timeout=15)
    except Exception:
        pass
    time.sleep(1.5)


def header_hash(data):
    d = struct.unpack("<I", data[12:16])[0]
    return hashlib.sha256(data[16:16 + d]).hexdigest()


def parse_asar(path):
    data = open(path, "rb").read()
    b = struct.unpack("<I", data[4:8])[0]
    d = struct.unpack("<I", data[12:16])[0]
    hdr = json.loads(data[16:16 + d].decode("utf8"))
    return hdr, data, 8 + b


def iter_files(node, prefix=""):
    if "files" in node:
        for name, child in node["files"].items():
            yield from iter_files(child, prefix + "/" + name)
    elif "offset" in node:
        yield prefix, node


def file_integrity(content):
    bs = 4 * 1024 * 1024
    blocks = [hashlib.sha256(content[i:i + bs]).hexdigest()
              for i in range(0, len(content), bs)]
    if not blocks:
        blocks.append(hashlib.sha256(b"").hexdigest())
    return {"algorithm": "SHA256", "hash": hashlib.sha256(content).hexdigest(),
            "blockSize": bs, "blocks": blocks}


def pack_asar(hdr, data, base, replace):
    entries = list(iter_files(hdr))
    contents = {}
    for path, node in entries:
        if path in replace:
            contents[path] = replace[path]
        else:
            off = int(node["offset"]) + base
            contents[path] = data[off:off + int(node["size"])]

    lookup = dict(entries)
    for path, blob in replace.items():
        node = lookup[path]
        node["size"] = len(blob)
        node["integrity"] = file_integrity(blob)

    cursor = 0
    for path, node in entries:
        node["offset"] = str(cursor)
        cursor += int(node["size"])

    hdr_str = json.dumps(hdr, separators=(",", ":"), ensure_ascii=False)
    hdr_bytes = hdr_str.encode("utf8")
    d = len(hdr_bytes)
    d_pad = d + (-d % 4)
    out = bytearray()
    out += struct.pack("<IIII", 4, d_pad + 8, d_pad + 4, d)
    out += hdr_bytes
    out += b" " * (d_pad - d)
    for path, node in entries:
        c = contents[path]
        assert len(c) == int(node["size"])
        out += c
    return bytes(out)


def get_exe_expected(exe_data):
    j = exe_data.find(b'[{"file":"resources')
    if j == -1:
        return None, None, None
    end = exe_data.find(b"]", j) + 1
    arr = json.loads(exe_data[j:end])
    return arr[0]["value"], j, end


def write_file(path, data):
    for attempt in range(3):
        try:
            open(path, "wb").write(data)
            return
        except PermissionError:
            if attempt == 2:
                raise
            print("[!] File is locked. Close HTTP Toolkit and press Enter.")
            try:
                input()
            except EOFError:
                time.sleep(3)


def main():
    install = find_install()
    if not install:
        print("[X] Could not locate HTTP Toolkit installation.")
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass
        sys.exit(1)
    print("[*] Installation: " + install)

    res = os.path.join(install, "resources")
    asar = os.path.join(res, "app.asar")
    asar_bak = os.path.join(res, "app.asar.clean.bak")
    exe = os.path.join(install, "HTTP Toolkit.exe")
    exe_bak = os.path.join(install, "HTTP Toolkit.exe.clean.bak")

    if not os.path.exists(asar):
        print("[X] app.asar not found.")
        _pause(); sys.exit(1)

    print("[*] Closing HTTP Toolkit...")
    kill_all()

    if not os.path.exists(asar_bak):
        shutil.copy2(asar, asar_bak)
        print("[*] Backup created: app.asar.clean.bak")
    else:
        print("[*] Backup exists: app.asar.clean.bak")
    if not os.path.exists(exe_bak):
        shutil.copy2(exe, exe_bak)
        print("[*] Backup created: HTTP Toolkit.exe.clean.bak")
    else:
        print("[*] Backup exists: HTTP Toolkit.exe.clean.bak")

    hdr, data, base = parse_asar(asar)
    lookup = dict(iter_files(hdr))
    for p in ("/build/preload.cjs", "/build/index.js"):
        if p not in lookup:
            print("[X] Unsupported installation layout (" + p + " missing).")
            _pause(); sys.exit(1)

    off = int(lookup["/build/index.js"]["offset"]) + base
    src = data[off:off + int(lookup["/build/index.js"]["size"])].decode("utf8")

    if "PRO_HOOK" not in src:
        if ANCHOR_CREATEWINDOW not in src or ANCHOR_AUTHTOKEN not in src:
            print("[X] This version is not supported (code anchors missing).")
            _pause(); sys.exit(1)
        src = src.replace(ANCHOR_CREATEWINDOW,
                          "const PRO_HOOK = `" + HOOK_JS + "`;" + chr(10) + ANCHOR_CREATEWINDOW)
        src = src.replace(
            ANCHOR_AUTHTOKEN,
            ANCHOR_AUTHTOKEN +
            chr(10) + "            contents.executeJavaScript(PRO_HOOK).catch(() => {});")

    expected, _, _ = get_exe_expected(open(exe, "rb").read())
    rebuilt = pack_asar(json.loads(json.dumps(hdr)), data, base, {})
    rt_hash = header_hash(rebuilt)
    if expected:
        if rt_hash != expected:
            print("[X] Verification failed: this build uses an unknown archive format.")
            _pause(); sys.exit(1)

    packed = pack_asar(hdr, data, base, {
        "/build/preload.cjs": PRELOAD_PATCHED.encode("utf8"),
        "/build/index.js": src.encode("utf8"),
    })
    new_hash = header_hash(packed)
    write_file(asar, packed)

    hdr2, data2, base2 = parse_asar(asar)
    for p, node in iter_files(hdr2):
        o = int(node["offset"]) + base2
        blob = data2[o:o + int(node["size"])]
        if file_integrity(blob) != node["integrity"]:
            print("[X] Archive verification failed.")
            _pause(); sys.exit(1)

    if expected:
        exe_data = open(exe, "rb").read()
        val, j, end = get_exe_expected(exe_data)
        if val and val != new_hash and len(val) == 64:
            new_json = exe_data[j:end].replace(val.encode(), new_hash.encode())
            write_file(exe, exe_data[:j] + new_json + exe_data[end:])
        elif val is None:
            print("[!] Executable integrity resource not found, skipping.")

    print("[OK] Patch applied successfully.")
    subprocess.Popen([exe])
    print("[OK] HTTP Toolkit started.")

    _pause()


def _pause():
    try:
        if sys.stdin.isatty():
            input("Press Enter to close this window...")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[X] Error: " + str(e))
        _pause()
        sys.exit(1)
