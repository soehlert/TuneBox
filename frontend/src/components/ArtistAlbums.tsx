import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { Grid, Card, CardContent, Typography, CardMedia } from "@mui/material"; // Added CardMedia for images
import "../App.css";
import "./ArtistAlbums.css"; // Updated import

interface Album {
  album_id: number;
  title: string;
  thumb: string | null; // Ensure thumb can be null
}

function ArtistAlbums() {
  const { artistId } = useParams<{ artistId: string }>();
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchAlbums = async () => {
      try {
        const response = await axios.get(
          `http://localhost:8000/api/music/artists/${artistId}/albums`
        );
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
    <div className="app-container">
      <div className="content-container">
        <h2>Albums</h2>
        {loading ? (
          <p>Loading...</p>
        ) : (
          <Grid
            container
            spacing={2}
            className={albums.length === 1 ? "artist-grid single-album" : "artist-grid"}
          >
            {albums.map((album) => (
              <Grid item key={album.album_id} xs={12} sm={6} md={4} lg={3}>
                <Card onClick={() => navigate(`/albums/${album.album_id}/tracks`)} className="album-card">
                  {/* Render album cover if available */}
                  {album.thumb && (
                    <CardMedia
                      component="img"
                      alt={album.title}
                      height="200"
                      image={album.thumb}
                      title={album.title}
                      className="album-cover"
                    />
                  )}
                  <CardContent>
                    <Typography
                      variant="h6"
                      className={album.title.length > 20 ? "long-title" : ""}
                      style={{ textAlign: "center", fontWeight: "bold", color: "#FFFFFF" }}
                    >
                      {album.title}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </div>

    </div>
  );
}

export default ArtistAlbums;
