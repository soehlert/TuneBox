import { useEffect, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { Card, Typography } from "@mui/material";
import { FallbackImage } from "./FallbackImage";
import { TuneBoxDialog } from "./TuneBoxDialog";
import "../App.css";
import "./ArtistAlbums.css";

interface Album {
  album_id: number;
  title: string;
  thumb: string | null;
  server_name?: string;
  sources?: any[];
}

function ArtistAlbums() {
  const { artistId } = useParams<{ artistId: string }>();
  const [searchParams] = useSearchParams();
  const serverId = searchParams.get("server_id");
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogState, setDialogState] = useState<{ open: boolean; title: string; message: string }>({
    open: false,
    title: "",
    message: "",
  });
  const navigate = useNavigate();
  const isDev = window.location.port === "5173";
  const apiBase = isDev ? `http://${window.location.hostname}:8000` : window.location.origin;

  useEffect(() => {
    const fetchAlbums = async () => {
      try {
        const sParam = serverId ? `?server_id=${serverId}` : "";
        const artistAlbumsUrl = `${apiBase}/api/music/artists/${artistId}/albums${sParam}`;
        const response = await axios.get(artistAlbumsUrl);
        setAlbums(response.data);
      } catch (error) {
        console.error("Error fetching albums:", error);
      } finally {
        setLoading(false);
      }
    };
    fetchAlbums();
  }, [artistId, serverId]);

  const sParam = serverId ? `?server_id=${serverId}` : "";

  return (
    <div className="album-list-wrapper">
      <div style={{ display: "flex", gap: "12px", marginBottom: "16px", flexWrap: "wrap" }}>
        <button className="back-button" style={{ marginBottom: 0 }} onClick={() => navigate("/?clear_search=true")}>
          <span className="material-symbols-outlined">groups</span>
          Back to Artists
        </button>
      </div>
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
              onClick={() => navigate(`/albums/${album.album_id}/tracks${sParam}`)}
              className="album-card"
            >
              <FallbackImage
                src={`${apiBase}/api/music/album-art/${album.album_id}${sParam}`}
                alt={album.title}
                type="album"
                className="album-cover"
              />
              <div className="album-card-overlay" style={{ flexDirection: "column", gap: "2px" }}>
                <Typography className="album-card-title">
                  {album.title}
                </Typography>
                {(() => {
                  const sources = album.sources || [];
                  if (sources.length > 1) {
                    return (
                      <span
                        style={{
                          fontSize: "9px",
                          background: "rgba(46, 204, 113, 0.2)",
                          border: "1px solid rgba(46, 204, 113, 0.5)",
                          color: "#2ecc71",
                          padding: "1px 5px",
                          borderRadius: "8px",
                          fontWeight: 700,
                          lineHeight: 1.2,
                          cursor: "pointer",
                        }}
                        title={`Found on ${sources.length} servers`}
                        onClick={(e) => {
                          e.stopPropagation();
                          const listStr = sources.map((s: any) => `• ${s.server_name || "Unknown Library"}`).join("\n");
                          setDialogState({
                            open: true,
                            title: `Multi-Library Album`,
                            message: `"${album.title}" is available across ${sources.length} connected libraries:\n\n${listStr}`,
                          });
                        }}
                      >
                        🌐 {sources.length} libraries
                      </span>
                    );
                  }
                  return null;
                })()}
              </div>
            </Card>
          ))}
        </div>
      )}

      <TuneBoxDialog
        open={dialogState.open}
        title={dialogState.title}
        message={dialogState.message}
        type="info"
        icon="dns"
        confirmText="Got It"
        onConfirm={() => setDialogState({ ...dialogState, open: false })}
      />
    </div>
  );
}

export default ArtistAlbums;
