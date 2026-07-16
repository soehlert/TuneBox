import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { Card, Typography } from "@mui/material";
import "../App.css";
import "./ArtistAlbums.css";

interface Album {
  album_id: number;
  title: string;
  thumb: string | null;
}

function ArtistAlbums() {
  const { artistId } = useParams<{ artistId: string }>();
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const isDev = window.location.port === "5173";
  const apiBase = isDev ? "http://localhost:8000" : window.location.origin;

  useEffect(() => {
    const fetchAlbums = async () => {
      try {
        const artistAlbumsUrl = `${apiBase}/api/music/artists/${artistId}/albums`;
        const response = await axios.get(artistAlbumsUrl);
        setAlbums(response.data);
      } catch (error) {
        console.error("Error fetching albums:", error);
      } finally {
        setLoading(false);
      }
    };
     fetchAlbums();
  }, [artistId]);

  return (
    <div className="album-list-wrapper">
      <header className="page-header">
        <Typography variant="h1" className="gradient-text">Albums</Typography>
        <Typography className="page-subtitle">Select an album to view tracks</Typography>
      </header>
      {loading ? (
        <Typography variant="h6">Loading...</Typography>
      ) : (
        <div className="album-grid">
          {albums.map((album) => (
            <Card
              key={album.album_id}
              onClick={() => navigate(`/albums/${album.album_id}/tracks`)}
              className="album-card"
            >
              <img
                src={`${apiBase}/api/music/album-art/${album.album_id}`}
                alt={album.title}
                className="album-cover"
              />
              <div className="album-card-overlay">
                <Typography className="album-card-title">
                  {album.title}
                </Typography>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export default ArtistAlbums;
