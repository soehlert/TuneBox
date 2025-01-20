# TuneBox

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

TuneBox is a web-based jukebox suite that allows you to manage and play music from your Plex server. The idea is to have
a central Jukebox, but still allow access to other devices. Meant for collective music listening at parties. It features 
a modern interface for interacting with your Plex music library, managing the queue, and controlling music playback.

#### Library View
![The Main Library Page](https://github.com/soehlert/TuneBox/blob/main/docs/images/Library.png?raw=true)

#### Artist View
![The Artist Album Page](https://github.com/soehlert/TuneBox/blob/main/docs/images/Artist.png?raw=true)

#### Album View
![The Album Detail Page](https://github.com/soehlert/TuneBox/blob/main/docs/images/Album.png?raw=true)


## Features
- **Plex Integration**: Seamlessly integrates with your Plex server to browse and play music.
- **Playback Queue**: Manage the queue of songs to be played and automatically update it in real-time.
- **Responsive Web Interface**: Control your music from any device with a modern web browser.

## Architecture

TuneBox is built with the following technologies:

- **FastAPI**: The backend is powered by FastAPI, providing a fast, efficient API for interacting with the Plex server 
  and managing the playback queue.
- **Redis**: Used for caching and managing the state of the playback queue, ensuring quick access and synchronization 
  across clients.
- **React**: The frontend is built with React, offering a dynamic and responsive interface for interacting with the 
  application.
- **WebSockets**: WebSockets are used for real-time communication, keeping the queue and playback state in sync across 
  all connected clients.

## Installation

### Prerequisites
- A running Plex server
- Docker
- Docker Compose
- A running Plex Client available for remote play (`NOTE:` Needs to be on the same subnet as your plex server or have the necessary broadcast traffic forwarded between subnets)

### Steps
1. Clone the repository:
   ```bash
   git clone https://github.com/soehlert/TuneBox.git
2. Enter the directory:
    ```bash
   cd TuneBox
3. Create a .env file in the root directory and configure it with your Plex server details. The .env file 
should look like this (where CLIENT_NAME is according to your Plex client):
    ```bash
    PLEX_USERNAME=usernamehere
    PLEX_PASSWORD=passwordhere
    PLEX_SERVER_NAME=plex-server
    CLIENT_NAME=Macbook Pro Personal
    REDIS_URL=redis://redis:6379
    TUNEBOX_URL=localhost:8000 # or DNS name or IP address of your Tunebox host
4. Create a frontend/.env file and configure it with. Unfortunately Vite requires us to use a separate .env file 
   inside the frontend directory
    ```bash
    VITE_TUNEBOX_URL=localhost # or DNS name or IP address of your Tunebox host
    ```
5. Build the Docker images and start the services:
    ```bash
   docker compose up -d --build
6. Access the webUI(s):
   1. main page: http://localhost
   2. fastAPI swagger page: http://0.0.0.0:8000/docs#/

## Contributing
Contributions are welcome! Feel free to open issues or submit pull requests if you encounter bugs or want to add new 
features.

## License
This project is open-source and available under the MIT License.
