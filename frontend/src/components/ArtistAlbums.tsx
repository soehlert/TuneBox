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

  // Derive artist name and unique connected servers across all albums
  const artistName = albums.length > 0 && (albums[0] as any).artist ? (albums[0] as any).artist : "Albums";

  const artistSourcesMap = new Map<string, string>();
  albums.forEach((alb) => {
    (alb.sources || []).forEach((s: any) => {
      if (s.server_name) {
        artistSourcesMap.set(s.server_id || s.server_name, s.server_name);
      }
    });
    if (alb.server_name) {
      artistSourcesMap.set(alb.server_name, alb.server_name);
    }
  });
  const uniqueArtistSources = Array.from(artistSourcesMap.values());
  const artistSourcesStr = uniqueArtistSources.join(" • ");

  return (
    <div className="album-list-wrapper">
      <div style={{ display: "flex", gap: "12px", marginBottom: "16px", flexWrap: "wrap", alignItems: "center" }}>
        <button className="back-button" style={{ marginBottom: 0 }} onClick={() => navigate("/?clear_search=true")}>
          <span className="material-symbols-outlined">groups</span>
          Back to Artists
        </button>

        {uniqueArtistSources.length > 1 ? (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "12px",
              background: "rgba(191, 9, 94, 0.15)",
              border: "1px solid rgba(191, 9, 94, 0.35)",
              color: "#ff4d94",
              padding: "6px 14px",
              borderRadius: "14px",
              fontWeight: 600,
            }}
            title={`Available on: ${artistSourcesStr}`}
          >
            🌐 Libraries - {artistSourcesStr}
          </span>
        ) : uniqueArtistSources.length === 1 ? (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "12px",
              background: "rgba(191, 9, 94, 0.15)",
              border: "1px solid rgba(191, 9, 94, 0.35)",
              color: "#ff4d94",
              padding: "4px 12px",
              borderRadius: "14px",
              fontWeight: 600,
            }}
          >
            📍 {uniqueArtistSources[0]}
          </span>
        ) : null}
      </div>
      <header className="page-header">
        <Typography variant="h1" className="gradient-text">{artistName}</Typography>
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
                  const uniqueAlbumMap = new Map<string, string>();
                  sources.forEach((s: any) => {
                    if (s.server_name) {
                      uniqueAlbumMap.set(s.server_id || s.server_name, s.server_name);
                    }
                  });
                  const uniqueAlbumNames = Array.from(uniqueAlbumMap.values());

                  if (uniqueAlbumNames.length > 1) {
                    return (
                      <span
                        style={{
                          fontSize: "9px",
                          background: "rgba(191, 9, 94, 0.15)",
                          border: "1px solid rgba(191, 9, 94, 0.35)",
                          color: "#ff4d94",
                          padding: "1px 6px",
                          borderRadius: "8px",
                          fontWeight: 700,
                          lineHeight: 1.2,
                          cursor: "pointer",
                        }}
                        title={`Found on ${uniqueAlbumNames.length} servers`}
                        onClick={(e) => {
                          e.stopPropagation();
                          const listStr = uniqueAlbumNames.map((s: string) => `• ${s}`).join("\n");
                          setDialogState({
                            open: true,
                            title: `Multi-Library Album`,
                            message: `"${album.title}" is available across ${uniqueAlbumNames.length} connected libraries:\n\n${listStr}`,
                          });
                        }}
                      >
                        🌐 {uniqueAlbumNames.length} libraries
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
