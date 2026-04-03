# Remote access (SSH tunnel)

Use this when JobRadar runs on your **Mac Studio** and you want the dashboard in a browser on another computer (e.g. Windows) on the **same network**, or when university Wi‑Fi blocks direct machine-to-machine traffic—in that case use **[Tailscale](https://tailscale.com/)** (or similar) on both machines first, then SSH to the Mac’s **Tailscale IP** instead of the campus Wi‑Fi IP.

The goal is: services stay bound to **`127.0.0.1` on the Mac** (not advertised to the whole network). You open an SSH tunnel from the client; the browser talks to **localhost on the client**, and SSH forwards traffic to the Mac.

---

## 1. One-time setup on the Mac (SSH server)

1. **System Settings → General → Sharing → Remote Login** — turn **on**.
2. Note the **username** shown there (your macOS account short name).
3. Connect with **SSH keys** (recommended): from the Windows PC, generate a key if needed and append your public key to `~/.ssh/authorized_keys` on the Mac. Password login works for testing but keys are better.

**Firewall:** If connections fail, System Settings → Network → Firewall — allow **incoming** for **sshd** / **Remote Login**.

---

## 2. Which ports to forward

| How you run the dashboard | Forward this from Mac `127.0.0.1` | Then open on the client |
|---------------------------|-----------------------------------|-------------------------|
| **`bash scripts/dev.sh`** (Vite + API) | **5173** only | `http://127.0.0.1:5173` |
| **Production-style API** (`uvicorn dashboard.api:app --port 8000` with built frontend) | **8000** | `http://127.0.0.1:8000` |
| **Streamlit** (if you use it) | **8501** | `http://127.0.0.1:8501` |

For **`dev.sh`**, you only need port **5173**: the Vite dev server proxies `/api` to the FastAPI backend on the Mac, so the browser never has to reach port 8000 directly.

---

## 3. Start the dashboard on the Mac (localhost)

From the repo root, with venv active:

```bash
cd /path/to/JobRadar
source .venv/bin/activate
bash scripts/dev.sh
```

Leave this running. The stack listens on the Mac’s loopback interface suitable for tunneling.

---

## 4. Open the tunnel from Windows

Replace **`macuser`** with your Mac login name and **`MAC_HOST`** with an address the **Windows PC can actually resolve and reach**.

### Finding `MAC_HOST` (use an IP if `.local` fails)

**On the Mac**, in Terminal:

```bash
ipconfig getifaddr en0
```

That prints the **Wi‑Fi IPv4** (e.g. `192.168.1.42`). Use that as `MAC_HOST`:

```text
ssh -N -L 5173:127.0.0.1:5173 macuser@192.168.1.42
```

(Ethernet is often `en1` or another `en*` — check **System Settings → Network** for the active interface and IP.)

**Why not `Something.local`?** Names ending in **`.local`** use **mDNS (Bonjour)**. **Windows often cannot resolve them**, and many **university networks block** machine-to-machine discovery. Prefer **the numeric IP** or **[Tailscale](https://tailscale.com/)**’s `100.x.x.x` address for the Mac.

Optional: on Windows you can map a stable name by editing `C:\Windows\System32\drivers\etc\hosts` (run editor as Administrator) and adding a line like `192.168.1.42 macstudio`.

**PowerShell or Command Prompt** (OpenSSH client, included on recent Windows):

```text
ssh -N -L 5173:127.0.0.1:5173 macuser@MAC_HOST
```

- **`-N`** — do not open a remote shell; only forward ports (keeps the window “hung” while the tunnel is up — that is normal).
- **`-L 5173:127.0.0.1:5173`** — “on this PC, TCP port 5173 → through SSH → Mac’s localhost:5173”.

Keep that window open. In the browser on Windows: **http://127.0.0.1:5173**

**Port already in use on Windows?** Map a different local port, e.g.:

```text
ssh -N -L 9000:127.0.0.1:5173 macuser@MAC_HOST
```

Then open **http://127.0.0.1:9000**

**Git Bash / WSL** uses the same `ssh -N -L ...` line.

---

## 5. Production-style dashboard (single port 8000)

If you serve the built UI via uvicorn on the Mac:

```text
ssh -N -L 8000:127.0.0.1:8000 macuser@MAC_HOST
```

Browser: **http://127.0.0.1:8000**

---

## 6. Streamlit (optional)

If you run `streamlit run dashboard/app.py` on the Mac:

```text
ssh -N -L 8501:127.0.0.1:8501 macuser@MAC_HOST
```

Browser: **http://127.0.0.1:8501**

---

## 7. Troubleshooting

| Symptom | What to check |
|--------|----------------|
| `Could not resolve hostname` / `No such host is known` | Do not rely on `*.local` from Windows — use the Mac’s **IPv4** (`ipconfig getifaddr en0`) or **Tailscale IP** |
| `channel N: open failed: connect failed: Connection refused` | **`dev.sh` not running**, wrong port, or (older setups) Vite listened only on IPv6 — repo `vite.config.ts` binds Vite to **`127.0.0.1`** so `127.0.0.1:5173` forwarding works; **restart** `dev.sh` after pulling |
| `Connection refused` on SSH | Remote Login on Mac, correct `MAC_HOST`, same VPN/Tailscale if on university Wi‑Fi |
| `Connection timed out` | Campus **client isolation** — use **Tailscale** on both machines, then SSH to the Mac’s Tailscale address |
| Browser spins / empty | Tunnel command still running; dashboard actually running on Mac; correct local URL and port |
| `bind: Address already in use` on Windows | Another app uses that port — use a different local port in `-L` |

---

## 8. Security notes

- Prefer **SSH keys** and keep the Mac patched.
- Tunnels do **not** replace authentication on the dashboard itself; anyone who can SSH as you can forward ports. Lock down SSH appropriately.
- Do not expose the dashboard to **`0.0.0.0`** on untrusted networks unless you understand who can reach your machine.
