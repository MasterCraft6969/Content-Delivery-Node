# Content-Delivery-Node

A self-hosted content delivery node designed to run entirely in Docker for security reasons, serving local content over HTTP with optional Discord bot integration.

---

## Features

- Dockerized content delivery server
- Simple CDN-style file serving
- Optional Discord bot integration

---

## Requirements

- Docker
- Docker Compose (recommended)
- Git

No local Python installation is required.

---

## One-Liner setups

### Windows (PowerShell)

```git clone https://github.com/MasterCraft6969/Content-Delivery-Node.git; cd Content-Delivery-Node; docker compose up -d --build```

### Linux

```git clone https://github.com/MasterCraft6969/Content-Delivery-Node.git && cd Content-Delivery-Node && docker compose up -d --build```

### MacOS 

Figure it out yourself lmao

---

## Configuration

All configuration is handled through `config.json` within the container filesystem.

---

## 🌐 Accessing the Server

Once running, access the node at:

`http://localhost:8000`

(or whatever port is defined in `config.json` / `docker-compose.yml`)

---

## Footnotes

- Intended for local or controlled environments
- Do not expose publicly without authentication or a reverse proxy, recommended to be paired with something like NGINX, Traefik, or a Cloudflare Tunnel.