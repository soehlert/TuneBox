import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Typography } from "@mui/material";
import axios from "axios";
import "./Stats.css";

interface StatItem {
  username: string;
  count: number;
}

interface StatsData {
  session: {
    adds: StatItem[];
    skips_cast: StatItem[];
    skips_received: StatItem[];
  };
  all_time: {
    adds: StatItem[];
    skips_cast: StatItem[];
    skips_received: StatItem[];
  };
}

export default function Stats({ apiBase }: { apiBase: string }) {
  const navigate = useNavigate();
  const [data, setData] = useState<StatsData | null>(null);
  const [mode, setMode] = useState<"session" | "all_time">("session");
  const [loading, setLoading] = useState(true);
  const [hideStaff, setHideStaff] = useState(true);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${apiBase}/api/stats`);
      setData(res.data);
    } catch (err) {
      console.error("Failed to fetch stats:", err);
    } finally {
      setLoading(false);
    }
  };

  const getActiveList = (type: "adds" | "skips_cast" | "skips_received") => {
    if (!data) return [];
    const list = mode === "session" ? data.session[type] : data.all_time[type];
    if (!hideStaff) return list;

    const adminName = localStorage.getItem("tunebox_admin_name") || "Admin";
    const instanceName = localStorage.getItem("tunebox_instance_name") || "TuneBox";

    return list.filter(item => {
      const nameLower = item.username.toLowerCase();
      return (
        nameLower !== "tunebox screen" &&
        nameLower !== "display" &&
        nameLower !== "admin" &&
        nameLower !== adminName.toLowerCase() &&
        nameLower !== instanceName.toLowerCase()
      );
    });
  };

  const renderTable = (title: string, list: StatItem[], metricName: string, icon: string) => {
    return (
      <div className="stats-card">
        <div className="stats-card-header">
          <span className="material-symbols-outlined stats-icon">{icon}</span>
          <Typography className="stats-card-title">{title}</Typography>
        </div>
        <div className="stats-table-wrapper">
          {list.length === 0 ? (
            <div className="stats-empty">No stats recorded yet.</div>
          ) : (
            <table className="stats-table">
              <thead>
                <tr>
                  <th style={{ width: "60px", textAlign: "center" }}>Rank</th>
                  <th>User</th>
                  <th style={{ textAlign: "right" }}>{metricName}</th>
                </tr>
              </thead>
              <tbody>
                {list.map((item, index) => {
                  let medal = "";
                  if (index === 0) medal = "🥇";
                  else if (index === 1) medal = "🥈";
                  else if (index === 2) medal = "🥉";
                  
                  return (
                    <tr key={index} className={`rank-row rank-${index}`}>
                      <td style={{ textAlign: "center", fontWeight: "bold" }}>
                        {medal || `${index + 1}`}
                      </td>
                      <td className="username-cell">{item.username}</td>
                      <td style={{ textAlign: "right", fontWeight: "bold", color: "var(--color-primary)" }}>
                        {item.count}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="stats-page">
      <div className="stats-container">
        {/* Top Header Row */}
        <div className="stats-header">
          <button className="back-button" onClick={() => navigate("/")}>
            <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>arrow_back</span>
            Back to Jukebox
          </button>
          
          <Typography variant="h4" className="stats-title">
            🏆 TuneBox Leaderboards
          </Typography>

          <div style={{ display: "flex", alignItems: "center", gap: "20px", flexWrap: "wrap" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer", fontSize: "13px", color: "rgba(255, 255, 255, 0.7)" }}>
              <input
                type="checkbox"
                checked={hideStaff}
                onChange={(e) => setHideStaff(e.target.checked)}
                style={{ cursor: "pointer" }}
              />
              Hide Host & Shared Display
            </label>
            <div className="toggle-container">
              <button 
                className={`toggle-btn ${mode === "session" ? "active" : ""}`}
                onClick={() => setMode("session")}
              >
                This Party
              </button>
              <button 
                className={`toggle-btn ${mode === "all_time" ? "active" : ""}`}
                onClick={() => setMode("all_time")}
              >
                All Time
              </button>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="stats-loading">Loading leaderboards...</div>
        ) : (
          <div className="stats-grids">
            {renderTable("Top Requestors", getActiveList("adds"), "Tracks Added", "library_music")}
            {renderTable("Skip Happy", getActiveList("skips_cast"), "Skips Cast", "skip_next")}
            {renderTable("Vibe Killers", getActiveList("skips_received"), "Songs Skipped", "heart_broken")}
          </div>
        )}
      </div>
    </div>
  );
}
